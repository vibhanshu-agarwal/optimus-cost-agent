"""#669: an API key pasted into the provider variable never reaches the refusal that agent start prints to stderr (kept
in the IDE's log). Fake keyring only; synthetic values."""

from __future__ import annotations

from pathlib import Path

import pytest

from optimus.acp.launch_gate import LaunchEnvironmentSnapshot, LaunchGateError, resolve_launch_candidate
from tests.unit.acp.test_launch_gate import (
    _HMAC_KEY,
    _REQUIRED_LAUNCH_ENV,
    _sample_operator_paths,
    _sample_workspace_identity,
)

_PASTED_KEY = "sk-or-v1-" + "a" * 24  # key-shaped, synthetic
_PROVIDER_VAR = "OPTIMUS_LOCAL_GATEWAY_PROVIDER"


class _Store:
    def __init__(self, entries: dict[str, str]) -> None:
        self.entries = entries

    def get_password(self, _service: str, key: str) -> str | None:
        return self.entries.get(key)


@pytest.mark.parametrize("layer", ["environment", "config_file", "keyring"])
def test_a_key_in_the_provider_variable_is_never_echoed(tmp_path: Path, layer: str) -> None:
    paths = _sample_operator_paths(tmp_path)
    env = dict(_REQUIRED_LAUNCH_ENV)
    store = _Store({})
    if layer == "environment":
        env[_PROVIDER_VAR] = _PASTED_KEY
    elif layer == "config_file":
        paths.config_root.mkdir(parents=True)
        (paths.config_root / ".env.gateway").write_text(f"{_PROVIDER_VAR}={_PASTED_KEY}\n", encoding="utf-8")
    else:
        store = _Store({"model_provider": _PASTED_KEY})

    with pytest.raises(LaunchGateError) as caught:
        resolve_launch_candidate(
            snapshot=LaunchEnvironmentSnapshot.capture(env),
            workspace_identity=_sample_workspace_identity(),
            operator_paths=paths,
            hmac_key=_HMAC_KEY,
            credential_keyring_backend=store,
        )
    exc = caught.value
    assert exc.code == "GATEWAY_PROVIDER_UNSUPPORTED"
    # What __main__ prints (code and detail), and the resolver message run-gateway and preflight print.
    for surface in (exc.detail, str(exc), str(exc.__cause__)):
        assert _PASTED_KEY not in surface and _PASTED_KEY[:12] not in surface
    assert _PROVIDER_VAR in exc.detail and "openrouter" in exc.detail
