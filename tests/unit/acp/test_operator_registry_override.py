"""ADR-025 (ADR-004 option C; Plan 12.4 v7 decision N1(a)): the operator's registry override.

One file, ``model-registry.yaml`` in the trusted operator config root, is composed over the shipped defaults by the
launch gate and by the Gateway independently. It counts only through the effective hash the operator approves: the
launch approval binds that hash, the Gateway refuses a manifest that names another, and ``optimus-trust run-gateway``
signs only a hash the workspace's durable approval already binds. Test profiles never read it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from optimus.acp import launch_approval_cli, operator_paths
from optimus.acp.trusted_paths import TrustedOperatorRoots
from optimus_gateway import __main__ as gateway_main
from optimus_model_policy import Role, select_eligible_models
from optimus_model_policy.binding import (
    APPROVAL_LITERAL_NAME,
    OPERATOR_OVERRIDE_FILENAME,
    BindingError,
    approval_literal,
    operator_override,
    packaged_defaults,
    trusted_approval_literal,
    trusted_snapshot,
    use_operator_override,
)
from optimus_model_policy.registry import load_registry
from tests.unit.acp.conftest import FakeKeyring
from tests.unit.acp.test_launch_gate_model_registry import _candidate
from tests.unit.acp.test_local_infra_model_registry import _spawned_args
from tests.unit.optimus_gateway.test_main_model_registry import _manifest, _run, started  # noqa: F401 - fixture

LUNA = "openai/gpt-6-luna"
# Luna in easy, with its route facts, the conservative estimator and its admission evidence: a model added in YAML.
LUNA_OVERRIDE = """
models:
  openai/gpt-6-luna:
    route:
      estimator: conservative-utf8
      endpoints:
        - {provider: openai, quantization: unknown, context_window_tokens: 1050000, max_output_tokens: 128000, verified: true, observed_on: "2026-10-25"}
    admission:
      empirical_estimate:
        evidence: ["a test fixture"]
        assumptions: ["text-only input"]
        limitations: ["a first call can exceed its estimate"]
      provider_family:
        provider: openai
        provider_name: OpenAI
        evidence: ["a test fixture"]
        limitations: ["the base slug can reach any OpenAI variant"]
roles:
  easy: [anthropic/claude-haiku-5.5, openai/gpt-6-luna]
"""


def _write_override(config_root: Path, text: str = LUNA_OVERRIDE) -> Path:
    config_root.mkdir(parents=True, exist_ok=True)
    path = config_root / OPERATOR_OVERRIDE_FILENAME
    path.write_text(text, encoding="utf-8")
    return path


def _override_literal(path: Path) -> str:
    return approval_literal(load_registry(packaged_defaults(), path))


def test_the_override_is_one_regular_file_in_the_config_root(tmp_path: Path) -> None:
    assert operator_override(tmp_path) is None
    path = _write_override(tmp_path)
    assert operator_override(tmp_path) == path

    other = tmp_path / "other"
    (other / OPERATOR_OVERRIDE_FILENAME).mkdir(parents=True)
    with pytest.raises(BindingError) as caught:
        operator_override(other)
    assert caught.value.code == "OPERATOR_OVERRIDE_UNSAFE"


def test_a_symlinked_override_is_refused_not_followed(tmp_path: Path) -> None:
    target = _write_override(tmp_path / "elsewhere")
    root = tmp_path / "config"
    root.mkdir()
    try:
        (root / OPERATOR_OVERRIDE_FILENAME).symlink_to(target)
    except OSError:
        pytest.skip("this host cannot create symlinks")
    with pytest.raises(BindingError) as caught:
        operator_override(root)
    assert caught.value.code == "OPERATOR_OVERRIDE_UNSAFE"


def test_the_process_override_composes_over_the_shipped_defaults(tmp_path: Path) -> None:
    shipped = trusted_snapshot()
    path = _write_override(tmp_path)
    use_operator_override(path)
    composed = trusted_snapshot()

    assert shipped is not None and composed is not None and composed.effective_hash != shipped.effective_hash
    assert select_eligible_models(composed, Role.EASY) == (LUNA, "anthropic/claude-haiku-5.5")
    assert trusted_approval_literal() == _override_literal(path)
    use_operator_override(None)
    assert trusted_snapshot() == shipped


def test_the_launch_approval_binds_the_composed_override_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The run guard redirects the OS roots on Windows only; on POSIX the resolved root is the real home, and an override
    # written there would reach every later launch in the process (PR #428's Linux CI). Pin the roots here on every OS.
    roots = TrustedOperatorRoots(
        default_config_root=tmp_path.parent / (tmp_path.name + "-config"), approval_runtime_root=tmp_path / "runtime"
    )
    monkeypatch.setattr(operator_paths, "resolve_trusted_operator_roots", lambda **_: roots)
    keyring = FakeKeyring()
    plain, _ = _candidate(tmp_path, keyring)
    config_root = _candidate(tmp_path, keyring)[0].operator_paths.config_root
    assert config_root.is_relative_to(roots.default_config_root.resolve())
    path = _write_override(config_root)

    with_override, _ = _candidate(tmp_path, keyring)

    assert plain.security_literals[APPROVAL_LITERAL_NAME] == approval_literal(load_registry(packaged_defaults()))
    assert with_override.security_literals[APPROVAL_LITERAL_NAME] == _override_literal(path)
    assert with_override.security_snapshot_digest != plain.security_snapshot_digest  # a changed override re-approves


def test_the_gateway_child_gets_the_override_by_path_and_a_profile_never_does(tmp_path: Path, monkeypatch) -> None:
    path = _write_override(tmp_path / "config")
    args = _spawned_args(tmp_path, monkeypatch, model_registry=_override_literal(path), config_root=tmp_path / "config")
    assert args[args.index("--registry-override") + 1] == str(path)

    profiled = _spawned_args(tmp_path, monkeypatch, model_registry="x", config_root=tmp_path / "config", test_profile="qualification")
    assert "--registry-override" not in profiled
    assert "--registry-override" not in _spawned_args(tmp_path, monkeypatch, config_root=tmp_path / "empty")


def test_the_gateway_composes_the_override_and_refuses_another_hash(tmp_path: Path, started: list) -> None:  # noqa: F811
    path = _write_override(tmp_path)
    shipped_literal = approval_literal(load_registry(packaged_defaults()))
    argv = ["--bind-host", "127.0.0.1", "--port", "8765", "--registry-override", str(path)]

    assert gateway_main.main([*argv, "--manifest", _manifest(_override_literal(path))]) == 0
    assert started[0].model_policy.snapshot.effective_hash == load_registry(packaged_defaults(), path).effective_hash
    started.clear()
    assert gateway_main.main([*argv, "--manifest", _manifest(shipped_literal)]) == 2
    assert started == []


def test_the_gateway_refuses_a_path_that_is_not_the_override_or_a_profile_with_one(tmp_path: Path, started: list, capsys) -> None:  # noqa: F811
    stray = tmp_path / "stray.yaml"
    stray.write_text(LUNA_OVERRIDE, encoding="utf-8")
    argv = ["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", _manifest(None)]

    assert gateway_main.main([*argv, "--registry-override", str(stray)]) == 2
    assert "OPERATOR_OVERRIDE_UNSAFE" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        gateway_main.main([*argv, "--registry-override", str(_write_override(tmp_path)), "--plan12-test-profile", "attached"])
    assert started == []


def _run_gateway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, approval: object, *, auto: bool = False) -> tuple[int, list, str]:
    """``optimus-trust run-gateway`` for the workspace ``tmp_path/workspace``, whose operator config root is the
    separate ``tmp_path/config`` (a config root inside the workspace is refused)."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    env_gateway = workspace / ".env.gateway"
    env_gateway.write_text(
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"  # pragma: allowlist secret - synthetic test fixture
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-or-test\n"  # pragma: allowlist secret - synthetic test fixture
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=shared-secret\n",  # pragma: allowlist secret - synthetic test fixture
        encoding="utf-8",
    )
    if os.name != "nt":
        env_gateway.chmod(0o600)
    spawned: list = []

    def fake_run(args, **kwargs):
        spawned.append(args)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(launch_approval_cli.KeyringApprovalStore, "read_durable", lambda self, digest: approval)
    with patch("sys.stdin") as stdin, patch("sys.stdout") as stdout, patch("sys.stderr") as stderr:
        stdin.isatty.return_value = stdout.isatty.return_value = True
        code = launch_approval_cli._cmd_run_gateway(
            workspace,
            bind_host="127.0.0.1",
            bind_port=8765,
            trusted_roots=TrustedOperatorRoots(default_config_root=tmp_path / "config", approval_runtime_root=tmp_path / "runtime"),
            credential_keyring_backend=FakeKeyring(),
            auto=auto,
        )
        written = "".join(call.args[0] for call in stderr.write.call_args_list)
    return code, spawned, written


def test_run_gateway_refuses_a_registry_no_durable_approval_binds(tmp_path: Path, monkeypatch) -> None:
    code, spawned, err = _run_gateway(tmp_path, monkeypatch, approval=None)
    assert (code, spawned) == (2, []) and "MODEL_REGISTRY_NOT_APPROVED" in err

    other = SimpleNamespace(security_literals={APPROVAL_LITERAL_NAME: "optimus-model-registry-v1:" + "d" * 64})
    code, spawned, err = _run_gateway(tmp_path, monkeypatch, approval=other)
    assert (code, spawned) == (2, []) and "MODEL_REGISTRY_NOT_APPROVED" in err


def test_run_gateway_signs_an_approved_override_and_passes_it_by_path(tmp_path: Path, monkeypatch) -> None:
    path = _write_override(tmp_path / "config")
    approved = SimpleNamespace(security_literals={APPROVAL_LITERAL_NAME: _override_literal(path)})

    code, spawned, _ = _run_gateway(tmp_path, monkeypatch, approval=approved)

    assert code == 0
    [args] = spawned
    assert args[args.index("--registry-override") + 1] == str(path)
    assert sys.executable in args
