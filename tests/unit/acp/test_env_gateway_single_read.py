"""#686: one launch, one `.env.gateway` revision. The launch gate and `optimus-trust run-gateway` each read the file once,
after its permission check, and take the Gateway tool settings, the provider credential and the shared secret from that
one reading. The tests replace the file atomically right after its first read; a second read would see the new revision.
Provenance (environment, `.env.gateway`, keyring) is the same whether the file or its parsed mapping is given. Fake
keyrings and synthetic values only; nothing starts."""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from optimus.acp import launch_approval_cli, launch_gate
from optimus.acp.launch_gate import LaunchEnvironmentSnapshot, resolve_launch_candidate
from optimus.acp.local_gateway_secrets import (
    CredentialLayer,
    _parse_env_gateway_file,
    resolve_provider_credentials,
    resolve_shared_secret_with_provenance,
)
from optimus.acp.trusted_paths import TrustedOperatorRoots
from optimus_model_policy.binding import APPROVAL_LITERAL_NAME, trusted_approval_literal
from tests.unit.acp.conftest import FakeKeyring
from tests.unit.acp.test_launch_gate import _HMAC_KEY, _REQUIRED_LAUNCH_ENV, _sample_operator_paths, _sample_workspace_identity

_CAP = "OPTIMUS_GATEWAY_TOOL_MAX_CALLS_PER_TOOL"
_NAMES = ("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
          "OPTIMUS_LOCAL_GATEWAY_BASE_URL", _CAP)


def _revision(tag: str, cap: str) -> dict[str, str]:
    return {"key": "synthkey" + tag * 16, "secret": "synthsecret" + tag * 16, "cap": cap}  # pragma: allowlist secret - synthetic test value


A, B = _revision("a", "2"), _revision("b", "3")


def _text(rev: dict[str, str]) -> str:
    return (f"OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\nOPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY={rev['key']}\n"
            f"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET={rev['secret']}\n{_CAP}={rev['cap']}\n")


def _write(path: Path, rev: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(".env.gateway.next")
    staged.write_bytes(_text(rev).encode())
    staged.chmod(0o600)  # the permission check refuses anything wider on POSIX
    os.replace(staged, path)  # atomic, as an editor or a setup tool would write it


def _replace_after_first_read(monkeypatch, path: Path) -> list[str]:
    """Write revision A, then swap in revision B as soon as the file has been read once. Returns the readings."""
    _write(path, A)
    original = Path.read_text
    checked_read = launch_gate.read_config_file_checked
    reads: list[str] = []

    def seen(text: str) -> str:
        reads.append(text)
        if len(reads) == 1:
            _write(path, B)
        return text

    def read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        text = original(self, *args, **kwargs)
        return seen(text) if self.name == ".env.gateway" else text

    def read_checked(file_path: Path, **kwargs: Any) -> str:
        return seen(checked_read(file_path, **kwargs))  # #693: the launch's reading, through its checked handle

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(launch_gate, "read_config_file_checked", read_checked)
    monkeypatch.setattr(launch_approval_cli, "read_config_file_checked", read_checked)
    return reads


def test_the_launch_gate_takes_tools_and_credentials_from_one_revision(monkeypatch, tmp_path: Path) -> None:
    paths = _sample_operator_paths(tmp_path)
    reads = _replace_after_first_read(monkeypatch, paths.config_root / ".env.gateway")

    candidate = resolve_launch_candidate(
        snapshot=LaunchEnvironmentSnapshot.capture(_REQUIRED_LAUNCH_ENV), workspace_identity=_sample_workspace_identity(),
        operator_paths=paths, hmac_key=_HMAC_KEY, credential_keyring_backend=FakeKeyring(),
    )

    assert len(reads) == 1
    assert candidate.gateway_tool_environ[_CAP] == A["cap"]
    assert candidate.provider_credentials is not None and candidate.provider_credentials.secrets is not None
    assert candidate.provider_credentials.secrets.model_provider_api_key == A["key"]
    assert candidate.shared_secret == A["secret"]
    assert candidate.provider_credentials.api_key_provenance.layer is CredentialLayer.CONFIG_FILE


def test_run_gateway_takes_tools_and_credentials_from_one_revision(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    reads = _replace_after_first_read(monkeypatch, workspace / ".env.gateway")
    for name in _NAMES:
        monkeypatch.delenv(name, raising=False)
    approved = SimpleNamespace(security_literals={APPROVAL_LITERAL_NAME: trusted_approval_literal()})
    monkeypatch.setattr(launch_approval_cli.KeyringApprovalStore, "read_durable", lambda self, digest: approved)
    roots = TrustedOperatorRoots(default_config_root=tmp_path / "config", approval_runtime_root=tmp_path / "runtime")
    spawned: dict[str, Any] = {}

    def run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        spawned.update(env=kwargs["env"])
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(launch_approval_cli.subprocess, "run", run)
    monkeypatch.setattr(launch_approval_cli, "_require_tty", lambda: None)
    assert launch_approval_cli._cmd_run_gateway(workspace, bind_host="127.0.0.1", bind_port=8765, trusted_roots=roots,
                                                credential_keyring_backend=FakeKeyring()) == 0

    assert len(reads) == 1
    assert spawned["env"][_CAP] == A["cap"]
    assert spawned["env"]["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] == A["key"]
    assert spawned["env"]["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] == A["secret"]


def _swap_right_after_the_check(monkeypatch, path: Path) -> list[str]:
    """#693: revision A is the one checked; revision B replaces it the moment this platform's real check returns.
    Returns what each swap did: on Windows an open handle refuses the replace, on POSIX it succeeds."""
    _write(path, A)
    name = "_validate_windows_permissions" if sys.platform == "win32" else "_validate_posix_permissions"
    real = getattr(launch_gate, name)
    swaps: list[str] = []

    def check_then_swap(*args: Any, **kwargs: Any) -> None:
        real(*args, **kwargs)
        try:
            _write(path, B)
            swaps.append("replaced")
        except PermissionError:
            swaps.append("refused")

    monkeypatch.setattr(launch_gate, name, check_then_swap)
    return swaps


def test_the_launch_gate_parses_the_file_it_checked(monkeypatch, tmp_path: Path) -> None:
    paths = _sample_operator_paths(tmp_path)
    swaps = _swap_right_after_the_check(monkeypatch, paths.config_root / ".env.gateway")

    candidate = resolve_launch_candidate(
        snapshot=LaunchEnvironmentSnapshot.capture(_REQUIRED_LAUNCH_ENV), workspace_identity=_sample_workspace_identity(),
        operator_paths=paths, hmac_key=_HMAC_KEY, credential_keyring_backend=FakeKeyring(),
    )

    assert len(swaps) == 1
    assert candidate.gateway_tool_environ[_CAP] == A["cap"]
    assert candidate.provider_credentials is not None and candidate.provider_credentials.secrets is not None
    assert candidate.provider_credentials.secrets.model_provider_api_key == A["key"]
    assert candidate.shared_secret == A["secret"]


def test_run_gateway_parses_the_file_it_checked(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    swaps = _swap_right_after_the_check(monkeypatch, workspace / ".env.gateway")
    for name in _NAMES:
        monkeypatch.delenv(name, raising=False)
    approved = SimpleNamespace(security_literals={APPROVAL_LITERAL_NAME: trusted_approval_literal()})
    monkeypatch.setattr(launch_approval_cli.KeyringApprovalStore, "read_durable", lambda self, digest: approved)
    roots = TrustedOperatorRoots(default_config_root=tmp_path / "config", approval_runtime_root=tmp_path / "runtime")
    spawned: dict[str, Any] = {}

    def run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        spawned.update(env=kwargs["env"])
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(launch_approval_cli.subprocess, "run", run)
    monkeypatch.setattr(launch_approval_cli, "_require_tty", lambda: None)
    assert launch_approval_cli._cmd_run_gateway(workspace, bind_host="127.0.0.1", bind_port=8765, trusted_roots=roots,
                                                credential_keyring_backend=FakeKeyring()) == 0

    assert len(swaps) == 1
    assert spawned["env"][_CAP] == A["cap"]
    assert spawned["env"]["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] == A["key"]
    assert spawned["env"]["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] == A["secret"]


class _SwappingWindowsAdapter:
    """Stands in for the Windows DACL check on any platform: it passes, then swaps the file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def check_file_permissions(self, _path: Path) -> bool:
        with contextlib.suppress(PermissionError):  # Windows: the open handle refuses the replace
            _write(self.path, B)
        return True


@pytest.mark.parametrize("branch", ["posix", "win32"])
def test_each_platform_branch_reads_through_the_handle_it_checked(monkeypatch, tmp_path: Path, branch: str) -> None:
    """#693, both branches on every platform: the check sees the opened file, and the text comes from that same handle."""
    path = tmp_path / ".env.gateway"
    _write(path, A)
    checked: list[int] = []
    adapter = None
    if branch == "posix":
        def posix_stand_in(fd: int) -> None:  # the real one needs a POSIX uid; this keeps its input, the opened file
            checked.append(os.fstat(fd).st_size)
            with contextlib.suppress(PermissionError):
                _write(path, B)

        monkeypatch.setattr(launch_gate, "_validate_posix_permissions", posix_stand_in)
    else:
        adapter = _SwappingWindowsAdapter(path)
    text = launch_gate.read_config_file_checked(path, platform_name=branch, win32_security_adapter=adapter)
    assert text == _text(A)
    assert checked == ([len(_text(A).encode())] if branch == "posix" else [])


@pytest.mark.parametrize("layer", [CredentialLayer.ENVIRONMENT, CredentialLayer.CONFIG_FILE, CredentialLayer.KEYRING])
def test_a_parsed_mapping_reports_the_same_values_and_provenance_as_the_file(tmp_path: Path, layer: CredentialLayer) -> None:
    environ: dict[str, str] = {}
    keyring = FakeKeyring()
    if layer is CredentialLayer.ENVIRONMENT:
        environ = {"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "envkey" + "e" * 16,  # pragma: allowlist secret - synthetic test value
                   "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "envsecret" + "e" * 16}  # pragma: allowlist secret - synthetic test value
    if layer is not CredentialLayer.KEYRING:
        _write(tmp_path / ".env.gateway", A)  # below the environment, above the keyring
    keyring.set_password("optimus-cost-agent", "model_provider_api_key", "ringkey" + "k" * 16)
    keyring.set_password("optimus-cost-agent", "local_gateway_shared_secret", "ringsecret" + "k" * 16)
    mapping = _parse_env_gateway_file(tmp_path / ".env.gateway")
    elsewhere = tmp_path / "no-config-here"  # with a mapping given, the file is not read

    from_file = resolve_provider_credentials(environ, config_root=tmp_path, keyring_backend=keyring)
    from_mapping = resolve_provider_credentials(environ, config_root=elsewhere, keyring_backend=keyring, dotenv_values=mapping)
    assert from_mapping == from_file
    assert from_mapping.api_key_provenance.layer is layer

    secret_from_file = resolve_shared_secret_with_provenance(environ, config_root=tmp_path, keyring_backend=keyring)
    secret_from_mapping = resolve_shared_secret_with_provenance(
        environ, config_root=elsewhere, keyring_backend=keyring, dotenv_values=mapping,
    )
    assert secret_from_mapping == secret_from_file
    assert secret_from_mapping[1].layer is layer
