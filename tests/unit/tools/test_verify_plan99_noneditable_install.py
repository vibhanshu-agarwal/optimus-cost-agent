from __future__ import annotations

from pathlib import Path

import pytest

import tools.verify_plan99_noneditable_install as verifier
from tools.verify_plan99_noneditable_install import (
    HOSTILE_PROVIDER_KEY,
    HOSTILE_SHARED_SECRET,
    VerificationError,
    assert_no_secret_values,
    build_offline_commands,
    installed_script_path,
    parse_live_output,
    select_wheel,
    validate_live_prerequisites,
)


def test_select_wheel_requires_exactly_one_wheel(tmp_path):
    with pytest.raises(VerificationError, match="exactly one wheel"):
        select_wheel(tmp_path)
    first = tmp_path / "optimus_cost_agent-0.1.0-py3-none-any.whl"
    first.write_bytes(b"wheel-one")
    assert select_wheel(tmp_path) == first.resolve()
    (tmp_path / "second-0.1.0-py3-none-any.whl").write_bytes(b"wheel-two")
    with pytest.raises(VerificationError, match="exactly one wheel"):
        select_wheel(tmp_path)


def test_installed_script_path_uses_scripts_on_windows_and_bin_on_posix(tmp_path):
    assert installed_script_path(tmp_path / "venv", "optimus-agent", windows=True) == (
        tmp_path / "venv" / "Scripts" / "optimus-agent.exe"
    )
    assert installed_script_path(tmp_path / "venv", "optimus-agent", windows=False) == (
        tmp_path / "venv" / "bin" / "optimus-agent"
    )


def test_offline_commands_build_isolated_environment_without_editable_install(tmp_path):
    wheel = tmp_path / "optimus_cost_agent-0.1.0-py3-none-any.whl"
    venv = tmp_path / "venv"
    commands = build_offline_commands(
        uv_executable="uv",
        venv_root=venv,
        wheel_path=wheel,
        windows=True,
    )
    rendered = "\n".join(" ".join(command) for command in commands)
    assert "--editable" not in rendered
    assert " -e " not in f" {rendered} "
    assert commands[0] == ["uv", "venv", str(venv), "--python", "3.14", "--clear"]
    assert commands[1] == [
        "uv",
        "pip",
        "install",
        "--python",
        str(venv / "Scripts" / "python.exe"),
        str(wheel),
    ]


def test_live_mode_requires_real_acpx_and_explicit_report(tmp_path):
    with pytest.raises(VerificationError, match="--report"):
        validate_live_prerequisites(acpx_executable="acpx", report_path=None)
    with pytest.raises(VerificationError, match="acpx"):
        validate_live_prerequisites(
            acpx_executable=None,
            report_path=tmp_path / "plan99-evidence.md",
        )


def test_sanitized_evidence_rejects_secret_values():
    with pytest.raises(VerificationError, match="secret value"):
        assert_no_secret_values(
            f"gateway startup accidentally included {HOSTILE_PROVIDER_KEY}",
            secret_values=(HOSTILE_PROVIDER_KEY, HOSTILE_SHARED_SECRET),
        )


def test_live_prerequisites_check_acpx_redis_and_credentials(
    tmp_path, monkeypatch
):
    (tmp_path / ".env.gateway").write_text("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=omitted\n")

    class ReachableSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(verifier.shutil, "which", lambda _: "acpx")
    monkeypatch.setattr(
        verifier.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stdout": "acpx 0.12.0\n", "stderr": ""})(),
    )
    monkeypatch.setattr(verifier.socket, "create_connection", lambda *args, **kwargs: ReachableSocket())

    verifier.validate_live_prerequisites(
        acpx_executable="acpx",
        report_path=tmp_path / "report.md",
        config_root=tmp_path,
        environ={"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379"},
    )


def test_parse_live_output_requires_end_turn_and_permission_evidence():
    records = parse_live_output(
        '{"event":"permission_request"}\n{"stop_reason":"end_turn"}\n'
    )
    assert len(records) == 2
    with pytest.raises(VerificationError, match="end-turn"):
        parse_live_output('{"event":"permission_request"}\n')


def test_script_delegates_acp_protocol_to_acpx():
    source = Path("tools/verify_plan99_noneditable_install.py").read_text(encoding="utf-8")
    for required in ('"--format"', '"--approve-all"', '"--cwd"', '"--agent"', '"exec"'):
        assert required in source
    for forbidden in ('"initialize"', '"session/new"', '"session/prompt"', "Content-Length"):
        assert forbidden not in source


def test_hostile_env_gateway_fixture_uses_resolver_readable_variable_names():
    """Regression guard: wrong var names make 'ignored' probes vacuously true."""
    contents = verifier.HOSTILE_ENV_GATEWAY_CONTENTS
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=" in contents
    assert "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=" in contents
    assert HOSTILE_PROVIDER_KEY in contents
    assert HOSTILE_SHARED_SECRET in contents
    # These names are NEVER read by resolve_provider_credentials / resolve_shared_secret.
    assert "OPENAI_API_KEY=" not in contents
    assert contents.count("OPTIMUS_API_KEY=") == 0


def test_live_gateway_log_status_uses_live_workspace_path():
    source = Path("tools/verify_plan99_noneditable_install.py").read_text(encoding="utf-8")
    assert 'gateway_log = workspace / ".optimus" / "local-gateway.log"' in source
    assert 'gateway_log = Path(str(paths["gateway_log"]))' not in source
