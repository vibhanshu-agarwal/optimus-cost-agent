"""#671: a credential-bearing URL the launch gate shows or hashes never reaches stderr, the approval display or the
run-gateway summary with its credential. Three mechanisms: a parser ValueError that carries the netloc, a bare value
shown verbatim (and query tokens), and a tab that defeats the redaction slice. Fake keyring only; synthetic values."""

from __future__ import annotations

from pathlib import Path

import pytest

from optimus.acp.launch_gate import LaunchEnvironmentSnapshot, LaunchGateError, resolve_launch_candidate
from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES
from tests.unit.acp.test_launch_gate import (
    _HMAC_KEY,
    _REQUIRED_LAUNCH_ENV,
    _sample_operator_paths,
    _sample_workspace_identity,
)

_PW = "synthpw" + "q" * 14  # synthetic credential
_KEY = "sk-or-v1-" + "b" * 24  # key-shaped, synthetic
_BASE = "OPTIMUS_LOCAL_GATEWAY_BASE_URL"
_API_KEY = "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"  # pragma: allowlist secret - a variable name, not a value
_SYNTH_PROVIDER_KEY = "sk-or-v1-" + "c" * 24  # synthetic provider key so the base URL is used

# 1: U+FF03 NFKC-normalizes to "#", so urllib.parse raises a ValueError whose text is the whole netloc.
# 2: a key pasted into a URL field has no scheme or host.  3: urllib.parse drops a tab before parsing.
MALFORMED = {
    "nfkc-netloc": "https://user:" + _PW + chr(0xFF03) + "@gw.example/v1",
    "bare-value": _KEY,
    "tab-in-authority": "https://user:" + _PW + "@gw" + chr(9) + ".example/v1",
}
URI_VARIABLES = sorted(name for name, policy in LAUNCH_VARIABLE_POLICIES.items() if policy.uri_userinfo)


class _Store:
    def get_password(self, _service: str, _key: str) -> str | None:
        return None


def _chain(exc: BaseException | None) -> list[BaseException]:
    seen: list[BaseException] = []
    while exc is not None and exc not in seen:
        seen.append(exc)
        exc = exc.__cause__ or exc.__context__
    return seen


def _assert_no_value(text: str) -> None:
    assert _PW not in text and _KEY not in text and _KEY[:12] not in text, text


def _resolve(tmp_path: Path, env: dict[str, str], env_gateway: str | None = None):
    paths = _sample_operator_paths(tmp_path)
    if env_gateway is not None:
        paths.config_root.mkdir(parents=True)
        path = paths.config_root / ".env.gateway"
        path.write_text(env_gateway, encoding="utf-8")
        path.chmod(0o600)  # owner-only, or POSIX refuses on permissions first
    return resolve_launch_candidate(
        snapshot=LaunchEnvironmentSnapshot.capture(env),
        workspace_identity=_sample_workspace_identity(),
        operator_paths=paths,
        hmac_key=_HMAC_KEY,
        credential_keyring_backend=_Store(),
    )


def _assert_refusal(exc: LaunchGateError, name: str, source: str) -> None:
    assert exc.code == "CREDENTIAL_URI_INVALID"
    assert f"{name} from {source} " in exc.detail, exc.detail
    for link in _chain(exc):  # what __main__ prints, and every exception it keeps
        _assert_no_value(str(link))
        assert link is exc or not isinstance(link, ValueError) or type(link).__module__ != "urllib.parse"


@pytest.mark.parametrize("mechanism", sorted(MALFORMED))
@pytest.mark.parametrize("name", URI_VARIABLES)
def test_a_malformed_url_in_the_environment_is_refused_without_its_value(tmp_path: Path, name: str, mechanism: str) -> None:
    env = {**_REQUIRED_LAUNCH_ENV, _API_KEY: _SYNTH_PROVIDER_KEY, name: MALFORMED[mechanism]}
    with pytest.raises(LaunchGateError) as caught:
        _resolve(tmp_path, env)
    _assert_refusal(caught.value, name, "the environment")


@pytest.mark.parametrize("mechanism", sorted(MALFORMED))
def test_a_malformed_base_url_in_env_gateway_is_refused_without_its_value(tmp_path: Path, mechanism: str) -> None:
    content = f"{_API_KEY}={_SYNTH_PROVIDER_KEY}\n{_BASE}={MALFORMED[mechanism]}\n"
    with pytest.raises(LaunchGateError) as caught:
        _resolve(tmp_path, dict(_REQUIRED_LAUNCH_ENV), env_gateway=content)
    _assert_refusal(caught.value, _BASE, ".env.gateway")


@pytest.mark.parametrize("layer", ["environment", "config_file"])
def test_query_and_fragment_values_never_reach_the_approval_display(tmp_path: Path, layer: str) -> None:
    url = "https://user:" + _PW + "@gw.example/v1?api_key=" + _PW + "&" + _KEY + "#" + _PW
    env = dict(_REQUIRED_LAUNCH_ENV)
    content = f"{_API_KEY}={_SYNTH_PROVIDER_KEY}\n"
    if layer == "environment":
        env[_BASE] = url
    else:
        content += f"{_BASE}={url}\n"
    candidate = _resolve(tmp_path, env, env_gateway=content)
    rows = [row for row in candidate.display_rows if row.name == _BASE]
    assert rows, candidate.display_rows
    for row in candidate.display_rows:
        _assert_no_value(row.display_value)
    assert rows[0].display_value == "https://**********@gw.example/v1?**********#**********"


@pytest.mark.parametrize(
    "value",
    [*MALFORMED.values(), "https://gw.example:99999/", "ftp://gw.example/", "https://[::1/", "https:/gw.example/"],
)
def test_the_sanitizer_refuses_without_the_value_or_a_parser_exception(value: str) -> None:
    from optimus_security.sanitization import CredentialUriError, canonicalize_credential_uri

    with pytest.raises(CredentialUriError) as caught:
        canonicalize_credential_uri(value)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    _assert_no_value(str(caught.value))


def test_the_digest_input_of_a_valid_url_is_unchanged() -> None:
    """Approval identity: only the userinfo is cut from the original text, as before #671; the query stays."""
    from optimus_security.sanitization import canonicalize_credential_uri

    result = canonicalize_credential_uri("  https://user:" + _PW + "@GW.example:8443/v1;p?x=1#top ")
    assert result.normalized_uri == "https://GW.example:8443/v1;p?x=1#top"
    assert result.display_uri == "https://**********@GW.example:8443/v1;p?**********#**********"
    assert canonicalize_credential_uri("").normalized_uri == ""


def test_agent_start_prints_the_refusal_without_a_traceback(monkeypatch, tmp_path: Path, capsys) -> None:
    """The real stderr surface: __main__'s handler (what the IDE keeps in its log)."""
    from optimus.acp import __main__ as acp_main
    from tests.unit.acp.conftest import FakeKeyring
    from tests.unit.acp.test_main_wiring import _base_env

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(tmp_path / "config"))
    for name, value in {**_base_env(), _BASE: MALFORMED["nfkc-netloc"]}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(acp_main, "keyring", FakeKeyring())
    started: list[str] = []
    for starter in ("ensure_local_redis", "ensure_local_gateway", "build_configured_server"):
        monkeypatch.setattr(acp_main, starter, lambda *_a, _n=starter, **_k: started.append(_n))

    assert acp_main.main(["--workspace-root", str(workspace)]) == 2
    err = capsys.readouterr().err
    assert "CREDENTIAL_URI_INVALID" in err and _BASE in err, err
    _assert_no_value(err)
    assert started == []


def _run_gateway(monkeypatch, tmp_path: Path, base_url: str) -> int:
    from optimus.acp import launch_approval_cli
    from optimus.acp.launch_approval_cli import _cmd_run_gateway
    from optimus.acp.trusted_paths import TrustedOperatorRoots

    env_gateway = tmp_path / ".env.gateway"
    env_gateway.write_text(
        f"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET={'d' * 32}\n{_API_KEY}={_SYNTH_PROVIDER_KEY}\n{_BASE}={base_url}\n",
        encoding="utf-8",
    )
    env_gateway.chmod(0o600)
    monkeypatch.setattr(launch_approval_cli, "_require_tty", lambda: None)
    monkeypatch.delenv(_BASE, raising=False)

    def _stop(**_kwargs: object) -> object:
        raise RuntimeError("stopped after the configuration summary")

    monkeypatch.setattr(launch_approval_cli, "resolve_authorized_operator_paths", _stop)
    return _cmd_run_gateway(
        tmp_path,
        bind_host="127.0.0.1",
        bind_port=8765,
        trusted_roots=TrustedOperatorRoots(
            default_config_root=tmp_path.parent / (tmp_path.name + "-config"), approval_runtime_root=tmp_path / "runtime"
        ),
        credential_keyring_backend=_Store(),
    )


@pytest.mark.parametrize("mechanism", sorted(MALFORMED))
def test_run_gateway_refuses_a_malformed_base_url_without_its_value(monkeypatch, tmp_path: Path, capsys, mechanism: str) -> None:
    assert _run_gateway(monkeypatch, tmp_path, MALFORMED[mechanism]) == 2
    captured = capsys.readouterr()
    assert f"{_BASE} from .env.gateway " in captured.err, captured.err
    _assert_no_value(captured.out + captured.err)


def test_run_gateway_summary_hides_userinfo_query_and_fragment(monkeypatch, tmp_path: Path, capsys) -> None:
    url = "https://user:" + _PW + "@gw.example/v1?api_key=" + _PW + "#" + _PW
    with pytest.raises(RuntimeError, match="stopped after"):
        _run_gateway(monkeypatch, tmp_path, url)
    captured = capsys.readouterr()
    assert "Base URL: https://**********@gw.example/v1?**********#**********" in captured.out, captured.out
    _assert_no_value(captured.out + captured.err)
