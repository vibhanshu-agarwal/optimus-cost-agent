"""Plan 12.2 Task 13 (Stage C): Gateway startup composes the shared test envelope and opens its guard.

A Stage C Gateway is started with a test profile and the resolved ledger path. It composes the envelope
itself from that path and its own source, and starts only if the signed manifest binds exactly that
envelope beside the profile's registry literal, the ledger was initialized for it, and no other Gateway
holds it. It never creates or resets a ledger. Without the ledger argument startup is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from optimus_gateway import __main__ as gateway_main
from optimus_model_policy import stage_c
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import approval_literal
from optimus_model_policy.stage_c import StageCGuard
from optimus_security.launch_manifest import build_gateway_child_manifest, serialize_gateway_child_manifest
from tests.unit.optimus_gateway.test_main_model_registry import _API_KEY, _KEY, _SECRET, _Keyring, _Server

ATTACHED = approval_literal(profiles.compose_test_profile_snapshot("attached"))


@pytest.fixture(autouse=True)
def _release_pinned_to_the_current_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise the Gateway's Stage C startup, which needs a release whose pins are the current profiles'.
    The real r9 release pins the pre-migration snapshots and refuses the migrated profiles (test_stage_c_envelope.py)."""
    current = {name: profiles.compose_test_profile_snapshot(name).effective_hash for name in stage_c.STAGE_C_PROFILES}
    monkeypatch.setattr(stage_c, "STAGE_C_PROFILE_HASHES", current)


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list:
    """The configs `serve_gateway` was started with (no socket is opened)."""
    for name in ("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "OPTIMUS_LOCAL_GATEWAY_PORT", "OPTIMUS_LOCAL_GATEWAY_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", _SECRET)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", _API_KEY)
    monkeypatch.setattr(gateway_main, "_keyring_module", _Keyring())
    configs: list = []
    monkeypatch.setattr(gateway_main, "serve_gateway", lambda *, config: configs.append(config) or _Server())
    return configs


def _manifest(model_registry: str | None, stage_c_envelope: str | None) -> str:
    return serialize_gateway_child_manifest(
        build_gateway_child_manifest(
            workspace_digest="a" * 64,
            security_snapshot_digest="b" * 64,
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            bind_host="127.0.0.1",
            bind_port=8765,
            provider_api_key=_API_KEY,
            shared_secret=_SECRET,
            hmac_key=_KEY,
            policy_version="P9.99-v1",
            model_registry=model_registry,
            stage_c_envelope=stage_c_envelope,
        )
    )


def _run(manifest: str, *extra: str) -> int:
    return gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", manifest, *extra])


@pytest.fixture
def ledger(tmp_path: Path) -> tuple[Path, str]:
    path = stage_c.stage_c_ledger_path(tmp_path)
    envelope = stage_c.compose_stage_c_envelope(ledger=path)
    stage_c.initialize_stage_c_ledger(path, envelope)
    return path, envelope.literal


def test_a_stage_c_gateway_guards_the_envelope_the_manifest_binds(started: list, ledger) -> None:
    path, envelope = ledger

    assert _run(_manifest(ATTACHED, envelope), "--plan12-test-profile", "attached", "--plan12-stage-c-ledger", str(path)) == 0

    [config] = started
    guard = config.stage_c_guard
    assert guard is not None and guard.envelope.literal == envelope and guard.state.deadline is not None
    assert guard.closed  # released when the Gateway stopped


@pytest.mark.parametrize(
    ("signed", "argv_ledger"),
    [(None, True), ("envelope", False), ("other", True)],
    ids=["ledger-but-unsigned", "signed-but-no-ledger", "another-envelope"],
)
def test_a_manifest_that_does_not_bind_this_envelope_refuses_to_start(started: list, ledger, capsys, signed: str | None, argv_ledger: bool) -> None:
    path, envelope = ledger
    literal = {"envelope": envelope, "other": "optimus-stage-c-envelope-v1:" + "e" * 64, None: None}[signed]
    extra = ["--plan12-test-profile", "attached"] + (["--plan12-stage-c-ledger", str(path)] if argv_ledger else [])

    assert _run(_manifest(ATTACHED, literal), *extra) == 2
    assert "MANIFEST_STAGE_C_ENVELOPE_MISMATCH" in capsys.readouterr().err and started == []


def test_an_uninitialized_ledger_is_never_created_by_a_start(started: list, tmp_path: Path, capsys) -> None:
    path = stage_c.stage_c_ledger_path(tmp_path)
    envelope = stage_c.compose_stage_c_envelope(ledger=path).literal

    assert _run(_manifest(ATTACHED, envelope), "--plan12-test-profile", "attached", "--plan12-stage-c-ledger", str(path)) == 2
    assert "STAGE_C_LEDGER_MISSING" in capsys.readouterr().err and started == [] and not path.exists()


def test_a_second_gateway_cannot_hold_the_same_ledger(started: list, ledger, capsys) -> None:
    path, envelope = ledger
    holder = StageCGuard.open(path, stage_c.compose_stage_c_envelope(ledger=path))
    try:
        assert _run(_manifest(ATTACHED, envelope), "--plan12-test-profile", "attached", "--plan12-stage-c-ledger", str(path)) == 2
    finally:
        holder.close()
    assert "STAGE_C_LEDGER_LOCKED" in capsys.readouterr().err and started == []


def test_a_relative_ledger_path_is_refused(started: list, capsys) -> None:
    assert _run(_manifest(ATTACHED, None), "--plan12-test-profile", "attached", "--plan12-stage-c-ledger", "relative.jsonl") == 2
    assert "STAGE_C_LEDGER_NOT_ABSOLUTE" in capsys.readouterr().err and started == []


def test_a_ledger_needs_a_test_profile(capsys, ledger) -> None:
    path, _ = ledger
    with pytest.raises(SystemExit) as caught:
        gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", "{}", "--plan12-stage-c-ledger", str(path)])
    assert caught.value.code == 2 and "--plan12-stage-c-ledger needs --plan12-test-profile" in capsys.readouterr().err


def test_a_profile_gateway_without_a_ledger_starts_unguarded(started: list) -> None:
    assert _run(_manifest(ATTACHED, None), "--plan12-test-profile", "attached") == 0
    [config] = started
    assert config.stage_c_guard is None and config.model_policy.approved_hash == profiles.TEST_PROFILES["attached"].effective_hash
