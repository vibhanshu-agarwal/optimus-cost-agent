"""#654: an unreadable credential store is never read as "nothing stored", and a setup that stops part-way says which
entries it wrote, without any value or the store's own error text. Fake stores only; synthetic values."""

from __future__ import annotations

from pathlib import Path

import pytest
from keyring.errors import NoKeyringError

from optimus.acp.launch_gate import LaunchEnvironmentSnapshot, LaunchGateError, resolve_launch_candidate
from optimus.acp.local_gateway_secrets import (
    CredentialStoreUnavailable,
    resolve_provider_credentials,
    resolve_shared_secret_with_provenance,
    run_setup_wizard,
)
from tests.unit.acp.test_launch_gate import (
    _HMAC_KEY,
    _REQUIRED_LAUNCH_ENV,
    _sample_operator_paths,
    _sample_workspace_identity,
)

_SERVICE = "optimus-cost-agent"
_LEAK = "store-said-" + "x" * 10  # what a backend's exception text might carry
_KEY = "synthetic-" + "k" * 16
_SHARED = "synthetic-" + "s" * 16
_PROVIDER_LINE = "OPTIMUS_LOCAL_GATEWAY_PROVIDER=" + "openrouter"


class _Store:
    """A fake keyring: ``unreadable`` makes every read raise; ``fail_on`` makes that write raise."""

    def __init__(self, *, unreadable: bool = False, fail_on: str | None = None, error: type[Exception] = RuntimeError) -> None:
        self.entries: dict[tuple[str, str], str] = {}
        self.unreadable, self.fail_on, self.error = unreadable, fail_on, error
        self.deleted: list[str] = []

    def get_password(self, service: str, key: str) -> str | None:
        if self.unreadable:
            raise self.error(_LEAK)
        return self.entries.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        if key == self.fail_on:
            raise self.error(_LEAK)
        self.entries[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self.deleted.append(key)


def _env_gateway(root: Path, *lines: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".env.gateway").write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return root


def test_an_unreadable_store_refuses_instead_of_defaulting_the_provider(tmp_path: Path) -> None:
    root = _env_gateway(tmp_path, f"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY={_KEY}",
                        f"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET={_SHARED}")
    with pytest.raises(CredentialStoreUnavailable) as caught:
        resolve_provider_credentials({}, config_root=root, keyring_backend=_Store(unreadable=True))

    message = caught.value.user_message
    assert caught.value.__cause__ is None and caught.value.__context__ is None  # the backend's text is not even chained
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER" in message and ".env.gateway" in message and "RuntimeError" in message
    assert _LEAK not in message and _KEY not in message


def test_an_unreadable_store_refuses_a_missing_key_and_shared_secret(tmp_path: Path) -> None:
    root = _env_gateway(tmp_path, _PROVIDER_LINE)
    with pytest.raises(CredentialStoreUnavailable):
        resolve_provider_credentials({}, config_root=root, keyring_backend=_Store(unreadable=True))
    with pytest.raises(CredentialStoreUnavailable) as caught:
        resolve_shared_secret_with_provenance({}, config_root=root, keyring_backend=_Store(unreadable=True))
    assert _LEAK not in caught.value.user_message


def test_an_absent_entry_keeps_todays_defaults_and_a_complete_file_never_reads_the_store(tmp_path: Path) -> None:
    empty = resolve_provider_credentials({}, config_root=tmp_path, keyring_backend=_Store())
    assert empty.secrets is None and empty.provider_provenance.layer.value == "default"

    root = _env_gateway(tmp_path / "full", _PROVIDER_LINE,
                        f"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY={_KEY}", f"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET={_SHARED}")
    resolved = resolve_provider_credentials({}, config_root=root, keyring_backend=_Store(unreadable=True))
    shared, _ = resolve_shared_secret_with_provenance({}, config_root=root, keyring_backend=_Store(unreadable=True))
    assert resolved.secrets is not None and resolved.secrets.model_provider_api_key == _KEY and shared == _SHARED


def test_the_launch_gate_refuses_with_its_own_code(tmp_path: Path) -> None:
    with pytest.raises(LaunchGateError) as caught:
        resolve_launch_candidate(
            snapshot=LaunchEnvironmentSnapshot.capture(dict(_REQUIRED_LAUNCH_ENV)),
            workspace_identity=_sample_workspace_identity(),
            operator_paths=_sample_operator_paths(tmp_path),
            hmac_key=_HMAC_KEY,
            credential_keyring_backend=_Store(unreadable=True),
        )
    assert caught.value.code == "GATEWAY_CREDENTIAL_STORE_UNAVAILABLE"
    assert _LEAK not in str(caught.value)


def _wizard(store: _Store, tmp_path: Path) -> tuple[int, list[str], list[str]]:
    printed: list[str] = []
    asked: list[str] = []

    def secret_prompt(prompt: str) -> str:
        asked.append(prompt)
        return _KEY

    code = run_setup_wizard(config_root=tmp_path, keyring_backend=store, input_fn=lambda _prompt: "y",
                            getpass_fn=secret_prompt, print_fn=lambda *args, **_k: printed.append(" ".join(map(str, args))))
    return code, printed, asked


def test_the_wizard_refuses_before_asking_when_it_cannot_read_the_store(tmp_path: Path) -> None:
    store = _Store(unreadable=True)
    code, printed, asked = _wizard(store, tmp_path)

    assert code == 2 and asked == [] and store.entries == {}
    text = "\n".join(printed)
    assert ".env.gateway" in text and _LEAK not in text


def test_a_partial_setup_names_what_it_wrote_and_deletes_nothing(tmp_path: Path) -> None:
    store = _Store(fail_on="model_provider_api_key")
    code, printed, _ = _wizard(store, tmp_path)

    assert code == 2
    assert store.entries == {(_SERVICE, "model_provider"): "openrouter"} and store.deleted == []
    text = "\n".join(printed)
    assert "incomplete" in text and "written, not verified: model_provider;" in text
    assert "unconfirmed: model_provider_api_key (RuntimeError;" in text and "not written: local_gateway_shared_secret" in text
    assert _LEAK not in text and _KEY not in text


def test_no_keyring_backend_at_all_is_absent_not_unknown(tmp_path: Path) -> None:
    """keyring's fail backend (no backend on this machine) can hold nothing, so today's fallback stands."""
    root = _env_gateway(tmp_path, f"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY={_KEY}",
                        f"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET={_SHARED}")
    resolved = resolve_provider_credentials({}, config_root=root, keyring_backend=_Store(unreadable=True, error=NoKeyringError))
    assert resolved.secrets is not None and resolved.provider_provenance.layer.value == "default"

    code, printed, _ = _wizard(_Store(unreadable=True, fail_on="model_provider", error=NoKeyringError), tmp_path)
    text = chr(10).join(printed)
    assert code == 2 and "not verified: none;" in text and "unconfirmed: model_provider (NoKeyringError;" in text
    assert _LEAK not in text


class _NullStore(_Store):
    """Like keyring's null backend: accepts every write and keeps nothing."""

    def set_password(self, service: str, key: str, value: str) -> None:
        return None


def test_a_store_that_keeps_nothing_is_not_reported_as_set_up(tmp_path: Path) -> None:
    code, printed, _ = _wizard(_NullStore(), tmp_path)
    text = chr(10).join(printed)
    assert code == 2 and "incomplete" in text and "unconfirmed: model_provider (did not read back)" in text
    assert "Stored local gateway credentials" not in text and _KEY not in text


class _UnreadableAfterWrites(_Store):
    """Accepts every write, then cannot be read back."""

    def get_password(self, service: str, key: str) -> str | None:
        if self.entries:
            raise RuntimeError(_LEAK)
        return None


def test_a_read_back_that_raises_is_reported_value_free(tmp_path: Path) -> None:
    code, printed, _ = _wizard(_UnreadableAfterWrites(), tmp_path)
    text = chr(10).join(printed)
    assert code == 2 and "confirmed: none; unconfirmed: model_provider (RuntimeError)" in text
    assert "not checked: model_provider_api_key, local_gateway_shared_secret" in text
    assert _LEAK not in text and _KEY not in text
