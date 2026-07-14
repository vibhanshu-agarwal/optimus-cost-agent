"""Verify the checked-in wheel can run from an isolated, non-editable install."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse


class VerificationError(RuntimeError):
    """Raised when the packaging or operator safety gate fails."""


HOSTILE_PROVIDER_KEY = "fake-provider-key"
HOSTILE_SHARED_SECRET = "fake-shared-secret"
HOSTILE_FIXTURE_SECRETS = (HOSTILE_PROVIDER_KEY, HOSTILE_SHARED_SECRET)
_PROVIDER_KEY_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "TAVILY_API_KEY",
    "GLM_API_KEY",
    "OPTIMUS_API_KEY",
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER",
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",
    "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
)

# Variable names the Task 2 resolver actually reads. Using other names would make an
# "ignored hostile .env.gateway" probe vacuously True regardless of directory.
HOSTILE_ENV_GATEWAY_CONTENTS = (
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
    f"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY={HOSTILE_PROVIDER_KEY}\n"
    f"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET={HOSTILE_SHARED_SECRET}\n"
)


def select_wheel(wheel_dir: Path) -> Path:
    wheels = sorted(wheel_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise VerificationError(f"expected exactly one wheel in {wheel_dir}, found {len(wheels)}")
    return wheels[0].resolve()


def installed_script_path(venv_root: Path, script_name: str, *, windows: bool) -> Path:
    directory = "Scripts" if windows else "bin"
    suffix = ".exe" if windows else ""
    return venv_root / directory / f"{script_name}{suffix}"


def build_offline_commands(
    *,
    uv_executable: str,
    venv_root: Path,
    wheel_path: Path,
    windows: bool,
) -> list[list[str]]:
    python_path = venv_root / ("Scripts" if windows else "bin") / "python"
    if windows:
        python_path = python_path.with_suffix(".exe")
    return [
        [uv_executable, "venv", str(venv_root), "--python", "3.14", "--clear"],
        [uv_executable, "pip", "install", "--python", str(python_path), str(wheel_path)],
    ]


def _resolve_executable(executable: str) -> str:
    """Resolve shell shims (e.g. npm's acpx.CMD) to an absolute path for shell=False."""
    resolved = shutil.which(executable)
    if resolved:
        return resolved
    candidate = Path(executable)
    if candidate.exists():
        return str(candidate.resolve())
    raise VerificationError(f"executable not found: {executable}")


def validate_live_prerequisites(
    *,
    acpx_executable: str | None,
    report_path: Path | None,
    config_root: Path | None = None,
    environ: dict[str, str] | None = None,
) -> None:
    if report_path is None:
        raise VerificationError("live mode requires --report")
    if not acpx_executable:
        raise VerificationError("live mode requires an acpx executable")
    resolved_acpx = _resolve_executable(acpx_executable)
    environment = dict(os.environ if environ is None else environ)
    version = subprocess.run(
        [resolved_acpx, "--version"],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if version.returncode != 0 or re.search(r"\b0\.12\.\d+\b", version.stdout + version.stderr) is None:
        raise VerificationError("acpx must report version 0.12.x")
    redis_url = environment.get("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379")
    parsed = urlparse(redis_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError as exc:
        raise VerificationError(f"Redis is not reachable at {host}:{port}") from exc
    resolved_config_root = (config_root or Path.cwd()).resolve()
    if not (resolved_config_root / ".env.gateway").is_file():
        try:
            import keyring

            shared_secret = keyring.get_password("optimus-cost-agent", "local_gateway_shared_secret")
        except Exception:
            shared_secret = None
        if not shared_secret:
            raise VerificationError(
                "live mode requires a keyring shared secret or config_root/.env.gateway"
            )


def assert_no_secret_values(text: str, *, secret_values: Sequence[str]) -> None:
    for secret in secret_values:
        if secret and secret in text:
            raise VerificationError("sanitized evidence contains a secret value")


def _run(command: Sequence[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise VerificationError(
            f"command failed with exit code {result.returncode}: {command[0]} "
            f"{' '.join(command[1:])}; {detail[0] if detail else 'no output'}"
        )
    return result


def _safe_env(*, config_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    for name in (*_PROVIDER_KEY_NAMES, "PYTHONPATH"):
        env.pop(name, None)
    env["OPTIMUS_CONFIG_ROOT"] = str(config_root)
    if not env.get("OPTIMUS_REDIS_URL", "").strip():
        env["OPTIMUS_REDIS_URL"] = "redis://127.0.0.1:6379/0"
    if not env.get("OPTIMUS_GATEWAY_URL", "").strip():
        env["OPTIMUS_GATEWAY_URL"] = "http://127.0.0.1:8765"
    return env


def _probe(
    *,
    python: Path,
    workspace: Path,
    env: dict[str, str],
    repo_root: Path,
    config_root: Path,
    secret_values: Sequence[str],
) -> dict[str, str]:
    code = (
        "import json, optimus, optimus_gateway; "
        "from optimus.acp.operator_paths import resolve_operator_paths; "
        "from pathlib import Path; "
        "p=resolve_operator_paths(workspace_root=Path.cwd(), environ=__import__('os').environ); "
        "from optimus.acp.local_gateway_secrets import resolve_provider_credentials, resolve_shared_secret; "
        "empty_keyring=type('EmptyKeyring', (), {'get_password': lambda self, service, key: None})(); "
        "credentials=resolve_provider_credentials(__import__('os').environ, config_root=Path(__import__('os').environ['OPTIMUS_CONFIG_ROOT']), keyring_backend=empty_keyring); "
        "shared=resolve_shared_secret(__import__('os').environ, config_root=Path(__import__('os').environ['OPTIMUS_CONFIG_ROOT']), keyring_backend=empty_keyring); "
        "print(json.dumps({'optimus': optimus.__file__, 'gateway': optimus_gateway.__file__, "
        "'config': str(p.config_root), 'runtime': str(p.runtime_root), "
        "'debug': str(p.debug_log_path), 'gateway_log': str(p.gateway_log_path), "
        "'provider_secrets': credentials.secrets is not None, 'shared_secret': shared is not None}))"
    )
    result = _run([str(python), "-c", code], cwd=workspace, env=env)
    _assert_output_clean(result.stdout + result.stderr, env, secret_values=secret_values)
    try:
        values = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VerificationError("isolated path probe returned invalid evidence") from exc
    for package_name in ("optimus", "gateway"):
        package_path = Path(values[package_name]).resolve()
        if package_path.is_relative_to(repo_root):
            raise VerificationError(f"{package_name} package resolved inside repository checkout")
        if not package_path.is_relative_to(python.parent.parent.resolve()):
            raise VerificationError(f"{package_name} package resolved outside isolated venv")
    if Path(values["config"]).resolve() != config_root.resolve():
        raise VerificationError("config root did not honor OPTIMUS_CONFIG_ROOT")
    for key in ("runtime", "debug", "gateway_log"):
        if not Path(values[key]).resolve().is_relative_to(workspace.resolve()):
            raise VerificationError(f"{key} escaped workspace runtime root")
    if values.get("provider_secrets") or values.get("shared_secret"):
        raise VerificationError("hostile workspace credentials were resolved as usable secrets")
    return {key: str(value) for key, value in values.items()}


def _ambient_secret_values(env: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        value
        for key, value in env.items()
        if ("KEY" in key or "SECRET" in key) and value
    )


def _assert_output_clean(
    output: str,
    env: dict[str, str],
    *,
    secret_values: Sequence[str] = HOSTILE_FIXTURE_SECRETS,
) -> None:
    assert_no_secret_values(
        output,
        secret_values=(*HOSTILE_FIXTURE_SECRETS, *secret_values, *_ambient_secret_values(env)),
    )
    if "PYTHONPATH" in output:
        raise VerificationError("offline evidence exposed PYTHONPATH")


def _offline(args: argparse.Namespace) -> dict[str, object]:
    wheel = select_wheel(args.wheel_dir)
    scratch = args.scratch_root.resolve()
    venv = scratch / "venv"
    workspace = scratch / "outside-repo" / "workspace"
    config_root = scratch / "operator-config"
    workspace.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)
    (workspace / ".optimus").mkdir(exist_ok=True)
    (workspace / ".env.gateway").write_text(HOSTILE_ENV_GATEWAY_CONTENTS, encoding="utf-8")
    env = _safe_env(config_root=config_root)
    commands = build_offline_commands(
        uv_executable=args.uv,
        venv_root=venv,
        wheel_path=wheel,
        windows=sys.platform == "win32",
    )
    for command in commands:
        _run(command, cwd=workspace, env=env)
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    script_results: dict[str, int] = {}
    for script in ("optimus-agent", "optimus-local-gateway"):
        executable = installed_script_path(venv, script, windows=sys.platform == "win32")
        result = _run([str(executable), "--help"], cwd=workspace, env=env)
        _assert_output_clean(result.stdout + result.stderr, env)
        script_results[script] = result.returncode
    paths = _probe(
        python=python,
        workspace=workspace,
        env=env,
        repo_root=Path(__file__).resolve().parents[1],
        config_root=config_root,
        secret_values=HOSTILE_FIXTURE_SECRETS,
    )
    return {
        "wheel": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "installed_script_path": {
            name: str(installed_script_path(venv, name, windows=sys.platform == "win32"))
            for name in ("optimus-agent", "optimus-local-gateway")
        },
        "build_offline_commands": commands,
        "script_exit_codes": script_results,
        "paths": paths,
        "hostile_env_gateway": "not read; content omitted",
    }


def _write_agent_wrapper(agent: Path, workspace: Path, *, windows: bool) -> Path:
    if windows:
        wrapper = workspace / "run-isolated-optimus-agent.cmd"
        provider_clears = "\n".join(f"set {name}=" for name in _PROVIDER_KEY_NAMES)
        wrapper.write_text(
            "@echo off\n"
            f"{provider_clears}\n"
            f"call \"{agent}\" %*\n",
            encoding="utf-8",
        )
    else:
        wrapper = workspace / "run-isolated-optimus-agent.sh"
        unset_names = " ".join(_PROVIDER_KEY_NAMES)
        wrapper.write_text(
            "#!/bin/sh\n"
            f"unset {unset_names}\n"
            f"exec \"{agent}\" \"$@\"\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
    return wrapper


def parse_live_output(output: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in output.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    if not records:
        raise VerificationError("acpx returned no usable JSON evidence")
    rendered = json.dumps(records, sort_keys=True).casefold()
    if "end_turn" not in rendered and "end-turn" not in rendered:
        raise VerificationError("acpx evidence has no end-turn reason")
    if "permission" not in rendered and "approval" not in rendered and "approved" not in rendered:
        raise VerificationError("acpx evidence has no permission approval evidence")
    return records


def _live(args: argparse.Namespace) -> dict[str, object]:
    offline_evidence = _offline(args)
    config_root = args.scratch_root.resolve() / "operator-config"
    validate_live_prerequisites(
        acpx_executable=args.acpx,
        report_path=args.report,
        config_root=config_root,
    )
    acpx = _resolve_executable(args.acpx)
    version_result = subprocess.run(
        [acpx, "--version"],
        cwd=Path.cwd(),
        env=_safe_env(config_root=config_root),
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    version = version_result.stdout + version_result.stderr
    workspace = args.scratch_root.resolve() / "live-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    agent = installed_script_path(
        args.scratch_root.resolve() / "venv", "optimus-agent", windows=sys.platform == "win32"
    )
    if not agent.is_file():
        raise VerificationError("offline install did not produce the isolated optimus-agent")
    wrapper = _write_agent_wrapper(agent, workspace, windows=sys.platform == "win32")
    fixture = workspace / "example.py"
    fixture.write_text("value = 1\n", encoding="utf-8")
    before = fixture.read_bytes()
    env = _safe_env(config_root=config_root)
    if args.model:
        env["OPTIMUS_AGENT_MODEL"] = args.model
    command = [
        acpx,
        "--format",
        "json",
        "--approve-all",
        "--cwd",
        workspace.as_posix(),
        "--agent",
        wrapper.as_posix(),
        "exec",
        "Add a module docstring to example.py. Modify only example.py.",
    ]
    result = _run(command, cwd=workspace, env=env)
    _assert_output_clean(result.stdout + result.stderr, env)
    parse_live_output(result.stdout)
    if fixture.read_bytes() == before:
        raise VerificationError("live ACP run did not mutate example.py")
    paths = offline_evidence["paths"]
    if Path(str(paths["config"])).resolve() != config_root.resolve():
        raise VerificationError("live config root is not the external operator-config root")
    # Use the live acpx workspace, not the offline probe workspace — R5 log ownership.
    gateway_log = workspace / ".optimus" / "local-gateway.log"
    gateway_status = (
        f"gateway started; logging to {gateway_log}"
        if gateway_log.exists()
        else "gateway reused; no new log"
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        "# Plan 9.9 operator packaging evidence\n\n"
        f"- acpx version: {version.strip()}\n"
        "- predicates: passed\n"
        f"- workspace: {workspace}\n"
        f"- gateway log: {gateway_status}\n",
        encoding="utf-8",
    )
    report_text = args.report.read_text(encoding="utf-8")
    _assert_output_clean(report_text, env)
    return {"live": "predicates_passed", "report": str(args.report)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--acpx", default="acpx")
    args = parser.parse_args(argv)
    try:
        evidence = _live(args) if args.live else _offline(args)
        if not args.live:
            rendered = json.dumps(evidence, sort_keys=True)
            assert_no_secret_values(
                rendered,
                secret_values=(*HOSTILE_FIXTURE_SECRETS, *_ambient_secret_values(_safe_env(
                    config_root=args.scratch_root.resolve() / "operator-config"
                ))),
            )
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(rendered + "\n", encoding="utf-8")
        print(json.dumps(evidence, sort_keys=True))
        return 0
    except (OSError, VerificationError, subprocess.SubprocessError) as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
