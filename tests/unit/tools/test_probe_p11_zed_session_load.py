"""Unit contracts for the version-agnostic P11 Zed session/load re-probe."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.probe_p11_zed_session_load import (
    ALLOWED_PROBE_SEMANTICS,
    AcpxBaselineEvidence,
    CommandResult,
    Finding,
    IsolationEvidence,
    ProbeError,
    ProbePatchPlan,
    RelayExchange,
    ZedInvocation,
    build_acpx_command,
    build_cleanup_remediation,
    build_opaque_relay_command,
    build_real_zed_launch_argv,
    build_trust_command,
    capture_acpx_evidence,
    classify_indeterminate_context,
    classify_live_zed_observation,
    classify_real_zed_result,
    discover_hermetic_zed_invocation,
    evaluate_session_load_exchange,
    exchange_from_relay_extract,
    extract_acpx_archive_capability_payload,
    extract_session_load_from_messages,
    hermetic_appdata_environment_bind,
    iter_acp_messages,
    main,
    materialize_sanitized_zed_evidence,
    normal_workspace_source_digest,
    prepare_real_zed_probe,
    reconstruct_sanitized_relay_bytes,
    record_probe_command_failure,
    seed_hermetic_zed_settings,
    throwaway_tree_digest,
    validate_acpx_baseline,
    validate_isolation_evidence,
    validate_probe_patch_plan,
    validate_zed_invocation,
    verify_normal_operation_isolation,
    write_isolated_agent_launcher,
    zed_target_already_running,
)
from tools.verify_plan1119_zed_reprobe_evidence import verify_manifest


def test_reachable_requires_advertised_capability_and_real_result() -> None:
    """Catches a false positive when a successful response lacks load capability."""
    capability_payload = {"loadSession": True, "sessionCapabilities": {"resume": False}}
    load_exchange = {
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "saved-1"}},
        "response": {"jsonrpc": "2.0", "id": 7, "result": {"sessionId": "saved-1"}},
    }

    result = evaluate_session_load_exchange(capability_payload, load_exchange)

    assert result.finding is Finding.REACHABLE
    assert result.capability_payload == capability_payload
    assert result.load_exchange == load_exchange


def test_unreachable_preserves_method_not_found_payload() -> None:
    """Catches a classifier that loses the exact live rejection needed for review."""
    capability_payload = {"loadSession": False, "sessionCapabilities": {}}
    load_exchange = {
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "saved-1"}},
        "response": {"jsonrpc": "2.0", "id": 7, "error": {"code": -32601, "message": "Method not found"}},
    }

    result = evaluate_session_load_exchange(capability_payload, load_exchange)

    assert result.finding is Finding.UNREACHABLE
    assert result.load_exchange["response"]["error"] == {"code": -32601, "message": "Method not found"}


def test_incomplete_exchange_is_indeterminate_even_when_advertised() -> None:
    """Catches a claim based solely on initialize when acpx did not invoke load."""
    capability_payload = {"loadSession": True, "sessionCapabilities": {}}

    result = evaluate_session_load_exchange(capability_payload, None)

    assert result.finding is Finding.INDETERMINATE
    assert result.load_exchange is None


def test_unadvertised_agent_load_capability_is_internal_indeterminate_without_a_forced_call() -> None:
    """Catches turning the agent's own gate into a claim about Zed."""
    capability_payload = {"sessionCapabilities": {"resume": False}}

    result = evaluate_session_load_exchange(capability_payload, None)

    assert result.finding is Finding.INDETERMINATE
    assert result.capability_payload == capability_payload
    assert result.load_exchange is None

    context = classify_indeterminate_context({"capability_payload": capability_payload})

    assert context == {"indeterminate_reason": "INTERNAL_CAPABILITY_UNAVAILABLE", "precondition": None}


def test_acpx_exported_session_capabilities_are_retained_as_live_evidence(tmp_path: Path) -> None:
    """Catches losing the initialized capabilities that acpx itself persisted."""
    archive = tmp_path / "session.json"
    archive.write_text(
        json.dumps(
            {
                "session": {
                    "state": {
                        "agent_capabilities": {"loadSession": False, "sessionCapabilities": {"resume": False}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert extract_acpx_archive_capability_payload(archive) == {
        "loadSession": False,
        "sessionCapabilities": {"resume": False},
    }


def test_raw_acpx_agent_command_uses_slash_normalized_windows_paths() -> None:
    """Catches acpx treating Windows backslashes in a raw agent command as escapes."""
    command = build_acpx_command(
        Path(r"C:\Tools\acpx.cmd"),
        workspace=Path(r"C:\probe workspace"),
        agent=Path(r"D:\agent path\optimus-agent.exe"),
    )

    assert command[-2] == "--agent"
    assert command[-1] == '"D:/agent path/optimus-agent.exe" --workspace-root "C:/probe workspace" --no-auto-start'
    assert command[command.index("--ttl") + 1] == "60"


def test_raw_acpx_agent_command_prefixes_python_for_py_launcher(tmp_path: Path) -> None:
    """Windows acpx cannot spawn a .py agent directly; that fails as spawn EFTYPE."""
    launcher = tmp_path / "isolated_optimus_agent.py"
    launcher.write_text("raise SystemExit(0)\n", encoding="utf-8")
    command = build_acpx_command(
        Path(r"C:\Tools\acpx.cmd"),
        workspace=tmp_path / "workspace",
        agent=launcher,
    )
    agent_argv = command[-1]
    assert agent_argv.startswith('"') or "python" in agent_argv.casefold()
    assert "isolated_optimus_agent.py" in agent_argv
    assert "--workspace-root" in agent_argv
    assert not agent_argv.lstrip('"').startswith(str(launcher).replace("\\", "/"))

def test_temporary_workspace_approval_uses_the_trust_cli_and_has_a_matching_revoke() -> None:
    """Catches a live probe that could create approval state without its paired cleanup command."""
    workspace = Path(r"C:\probe workspace")

    approve = build_trust_command(Path(r"C:\Tools\optimus-trust.exe"), workspace, "approve")
    revoke = build_trust_command(Path(r"C:\Tools\optimus-trust.exe"), workspace, "revoke")

    assert approve[-3:] == ["approve", "--mode", "durable"]
    assert revoke[-1:] == ["revoke"]
    assert approve[:3] == [r"C:\Tools\optimus-trust.exe", "--workspace-root", r"C:\probe workspace"]
    assert approve[:3] == revoke[:3]


def test_acpx_evidence_keeps_protocol_records_but_redacts_secret_aliases_and_free_text() -> None:
    """Catches unsafe persistence of tool streams from the independently authored client."""
    result = CommandResult(
        command=["acpx", "sessions", "new"],
        returncode=1,
        stdout=(
            '{"jsonrpc":"2.0","result":{"agentCapabilities":'
            '{"loadSession":false,"apiKey":"json-secret","credential":"credential-secret"}}}'
        ),
        stderr="OPTIMUS_API_KEY=env-secret Bearer bearer-secret",
    )

    evidence = capture_acpx_evidence(result)

    serialized = json.dumps(evidence)
    assert "json-secret" not in serialized
    assert "credential-secret" not in serialized
    assert "env-secret" not in serialized
    assert "bearer-secret" not in serialized
    assert evidence["capability_payload"] == {
        "loadSession": False,
        "apiKey": "**********",
        "credential": "**********",
    }


def test_cleanup_remediation_is_workspace_scoped_and_contains_no_approval_identifier() -> None:
    """Catches a cleanup-failure path that cannot tell the operator exactly what to undo."""
    remediation = build_cleanup_remediation(
        Path(r"C:\Tools\optimus-trust.exe"), Path(r"C:\probe workspace")
    )

    assert str(remediation[0]).endswith("optimus-trust.exe")
    assert remediation[1:4] == ["--workspace-root", r"C:\probe workspace", "revoke"]
    assert all("approval" not in part.casefold() for part in remediation)


def test_redis_startup_failure_is_a_precondition_with_the_runbook_remediation() -> None:
    """Catches treating a missing Redis dependency as an observation about Zed."""
    context = classify_indeterminate_context(
        {
            "stderr": "optimus-agent: Redis is not reachable. Start Redis or fix OPTIMUS_REDIS_URL."
        }
    )

    assert context["indeterminate_reason"] == "PRECONDITION_UNMET"
    assert context["precondition"] == {
        "name": "redis",
        "remediation": {
            "runbook": "docs/runbooks/local-live-dependencies.md#5-bounded-session-bound-smoke-redis--gateway-optional-phoenix",
            "command": "optimus-agent --workspace-root <throwaway-workspace> --check-config --strict",
        },
    }


def test_missing_load_exchange_is_an_incomplete_observation_not_a_precondition() -> None:
    """Catches collapsing a clean ACP exchange gap into an infrastructure to-do."""
    context = classify_indeterminate_context({"stderr": "", "stdout_records": []})

    assert context == {"indeterminate_reason": "OBSERVATION_INCOMPLETE", "precondition": None}


REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_SPEC = REPO_ROOT / "src" / "optimus" / "acp" / "spec.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_normal_tree(root: Path) -> None:
    spec = root / "src" / "optimus" / "acp" / "spec.py"
    spec.parent.mkdir(parents=True)
    spec.write_text(REAL_SPEC.read_text(encoding="utf-8"), encoding="utf-8")
    _git(root, "init")
    _git(root, "config", "user.email", "probe@example.test")
    _git(root, "config", "user.name", "Probe")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")


def _isolation_evidence(**overrides: object) -> IsolationEvidence:
    payload = {
        "normal_agent_load_session_advertised": False,
        "isolated_probe_load_session_advertised": True,
        "normal_source_sha256_before": "a" * 64,
        "normal_source_sha256_after": "a" * 64,
        "isolated_source_root": r"C:\scratch\src",
        "isolated_build_root": r"C:\scratch\build",
        "hermetic_zed_root": r"C:\scratch\zed-home",
        "cleanup_dry_run_verified": True,
        "cleanup_verified": True,
    }
    payload.update(overrides)
    return IsolationEvidence(**payload)  # type: ignore[arg-type]


def _session_load_exchange(
    *,
    result: dict[str, object] | None = None,
    error: dict[str, object] | None = None,
    method: str = "session/load",
) -> RelayExchange:
    response: dict[str, object] = {"jsonrpc": "2.0", "id": 7}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = {} if result is None else result
    return RelayExchange(
        request={"jsonrpc": "2.0", "id": 7, "method": method, "params": {"sessionId": "saved-1"}},
        response=response,
    )


def test_prepare_probe_rejects_normal_workspace_and_extra_patch_surface(tmp_path: Path) -> None:
    normal_root = tmp_path / "normal"
    normal_root.mkdir()
    with pytest.raises(ProbeError, match="outside the normal workspace"):
        prepare_real_zed_probe(normal_root, normal_root=normal_root, scratch_parent=tmp_path)

    nested = normal_root / "nested"
    nested.mkdir()
    with pytest.raises(ProbeError, match="outside the normal workspace"):
        prepare_real_zed_probe(nested, normal_root=normal_root, scratch_parent=tmp_path)

    with pytest.raises(ProbeError, match="outside the normal workspace"):
        prepare_real_zed_probe(tmp_path, normal_root=normal_root, scratch_parent=tmp_path)

    plan = ProbePatchPlan(
        changed_paths=("src/optimus/acp/spec.py", "README.md"),
        capability_patch={"loadSession": True},
        load_response={},
    )
    with pytest.raises(ProbeError, match="unexpected patch surface"):
        validate_probe_patch_plan(plan)


def test_validate_probe_patch_plan_accepts_only_allowlisted_semantics() -> None:
    validate_probe_patch_plan(
        ProbePatchPlan(
            changed_paths=("src/optimus/acp/spec.py",),
            capability_patch={"loadSession": True},
            load_response={},
        )
    )
    assert ALLOWED_PROBE_SEMANTICS == {
        "initialize.agentCapabilities.loadSession": True,
        "request.session/load.response.result": {},
    }


def test_isolation_rejects_normal_capability_payload_containing_load_session() -> None:
    evidence = _isolation_evidence(normal_agent_load_session_advertised=True)
    with pytest.raises(ProbeError, match="normal capability payload"):
        validate_isolation_evidence(evidence)
    assert evidence.prelaunch_predicates_pass is False
    assert classify_real_zed_result(_session_load_exchange(), evidence) is Finding.INDETERMINATE


def test_isolation_rejects_missing_before_after_source_digest() -> None:
    evidence = _isolation_evidence(normal_source_sha256_before="", normal_source_sha256_after="")
    with pytest.raises(ProbeError, match="source digest"):
        validate_isolation_evidence(evidence)
    assert evidence.prelaunch_predicates_pass is False


def test_isolation_rejects_unremoved_scratch_roots() -> None:
    evidence = _isolation_evidence(cleanup_verified=False)
    with pytest.raises(ProbeError, match="unremoved scratch"):
        validate_isolation_evidence(evidence)
    assert evidence.all_four_predicates_pass is False
    assert classify_real_zed_result(_session_load_exchange(), evidence) is Finding.INDETERMINATE


def test_source_digest_changes_when_untracked_file_appears(tmp_path: Path) -> None:
    """Paired with the tracked-source digest so a stray untracked file cannot hide."""
    _init_normal_tree(tmp_path)
    before = normal_workspace_source_digest(tmp_path)
    (tmp_path / "stray-untracked.txt").write_text("leak", encoding="utf-8")
    after = normal_workspace_source_digest(tmp_path)
    assert before != after


def test_throwaway_tree_digest_does_not_require_git(tmp_path: Path) -> None:
    """Isolated probe copies have no .git; identity recording must not call git ls-files there."""
    tree = tmp_path / "probe-source"
    (tree / "src").mkdir(parents=True)
    (tree / "src" / "a.py").write_text("print(1)\n", encoding="utf-8")
    digest = throwaway_tree_digest(tree)
    assert len(digest) == 64
    (tree / "src" / "a.py").write_text("print(2)\n", encoding="utf-8")
    assert throwaway_tree_digest(tree) != digest


def test_prepare_probe_excludes_gitignored_secret_like_files(tmp_path: Path) -> None:
    """Catches a blanket copytree that would leak .env/credentials into the isolated probe tree."""
    normal_root = tmp_path / "normal"
    scratch_parent = tmp_path / "scratch"
    scratch_parent.mkdir()
    _init_normal_tree(normal_root)
    (normal_root / ".gitignore").write_text(".env\ncredentials.json\n", encoding="utf-8")
    _git(normal_root, "add", ".gitignore")
    _git(normal_root, "commit", "-m", "ignore secrets")
    (normal_root / ".env").write_text("OPTIMUS_API_KEY=live-secret\n", encoding="utf-8")
    (normal_root / "credentials.json").write_text('{"token": "live-secret"}\n', encoding="utf-8")
    isolated_root = scratch_parent / "probe-src"

    prepare_real_zed_probe(isolated_root, normal_root=normal_root, scratch_parent=scratch_parent)

    listed = {
        item.replace("\\", "/")
        for item in subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=normal_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split("\0")
        if item
    }
    copied = {path.relative_to(isolated_root).as_posix() for path in isolated_root.rglob("*") if path.is_file()}

    assert (isolated_root / ".env").exists() is False
    assert (isolated_root / "credentials.json").exists() is False
    assert (isolated_root / ".gitignore").exists() is True
    assert copied == listed
    assert ".env" not in listed
    assert "credentials.json" not in listed


def test_prepare_probe_patches_only_isolated_spec_and_records_isolation(tmp_path: Path) -> None:
    normal_root = tmp_path / "normal"
    scratch_parent = tmp_path / "scratch"
    scratch_parent.mkdir()
    _init_normal_tree(normal_root)
    isolated_root = scratch_parent / "probe-src"
    before = normal_workspace_source_digest(normal_root)

    preparation = prepare_real_zed_probe(
        isolated_root,
        normal_root=normal_root,
        scratch_parent=scratch_parent,
    )
    isolation = verify_normal_operation_isolation(preparation)

    isolated_spec = Path(preparation.isolated_source_root) / "src" / "optimus" / "acp" / "spec.py"
    normal_spec = normal_root / "src" / "optimus" / "acp" / "spec.py"
    isolated_text = isolated_spec.read_text(encoding="utf-8")
    normal_text = normal_spec.read_text(encoding="utf-8")

    assert isolated_root.resolve() == Path(preparation.isolated_source_root).resolve()
    assert isolated_root.is_relative_to(scratch_parent.resolve())
    assert '"loadSession": True' in isolated_text
    assert "session/load" in isolated_text
    assert '"loadSession": True' not in normal_text
    assert isolation.normal_agent_load_session_advertised is False
    assert isolation.isolated_probe_load_session_advertised is True
    assert isolation.normal_source_sha256_before == before
    assert isolation.normal_source_sha256_after == before
    assert isolation.cleanup_dry_run_verified is True
    assert isolation.prelaunch_predicates_pass is True
    assert isolation.cleanup_verified is False
    validate_isolation_evidence(isolation, require_cleanup=False)


def test_classify_real_zed_result_requires_session_load_request_for_reachable() -> None:
    isolation = _isolation_evidence()
    assert classify_real_zed_result(_session_load_exchange(result={}), isolation) is Finding.REACHABLE
    assert (
        classify_real_zed_result(
            _session_load_exchange(error={"code": -32601, "message": "Method not found"}),
            isolation,
        )
        is Finding.UNREACHABLE
    )
    assert classify_real_zed_result(None, isolation) is Finding.INDETERMINATE
    assert (
        classify_real_zed_result(_session_load_exchange(result={}, method="session/new"), isolation)
        is Finding.INDETERMINATE
    )


HERMETIC_ROOT = Path(r"C:\scratch\zed-home")


def _valid_invocation() -> ZedInvocation:
    return ZedInvocation(
        argv=("C:\\Tools\\Zed.exe", "--isolated-user-data", str(HERMETIC_ROOT)),
        user_data_root=str(HERMETIC_ROOT),
        discovered_from="zed --help",
    )


def test_real_zed_launch_rejects_ambient_profile_and_missing_discovery() -> None:
    invocation = ZedInvocation(argv=("Zed.exe",), user_data_root=None, discovered_from="")
    with pytest.raises(ProbeError, match="current-version hermetic invocation"):
        validate_zed_invocation(invocation, hermetic_root=Path(r"C:\scratch\zed-home"))


def test_user_data_path_outside_hermetic_root_is_rejected() -> None:
    invocation = ZedInvocation(
        argv=("Zed.exe", "--isolated-user-data", r"C:\other\profile"),
        user_data_root=r"C:\other\profile",
        discovered_from="zed --help",
    )
    with pytest.raises(ProbeError, match="hermetic root"):
        validate_zed_invocation(invocation, hermetic_root=HERMETIC_ROOT)


def test_ambient_profile_user_data_is_rejected() -> None:
    ambient = Path(r"C:\Users\me\AppData\Roaming")
    invocation = ZedInvocation(
        argv=("Zed.exe", "--isolated-user-data", str(ambient)),
        user_data_root=str(ambient),
        discovered_from="zed --help",
    )
    with pytest.raises(ProbeError, match="current-version hermetic invocation"):
        validate_zed_invocation(
            invocation,
            hermetic_root=ambient,
            ambient_profile_roots=(ambient,),
        )


def test_hermetic_root_under_temp_is_not_treated_as_ambient_profile(tmp_path: Path) -> None:
    hermetic = tmp_path / "zed-home"
    hermetic.mkdir()
    invocation = ZedInvocation(
        argv=("Zed.exe", "--user-data-dir", str(hermetic)),
        user_data_root=str(hermetic),
        discovered_from="zed --help",
    )
    validate_zed_invocation(
        invocation,
        hermetic_root=hermetic,
        ambient_profile_roots=(tmp_path.parent, tmp_path.parent / "AppData" / "Roaming"),
    )


@pytest.mark.skipif(sys.platform != "win32", reason="default Zed data directory layout is Windows-specific")
def test_default_zed_data_directory_is_rejected_even_when_nested() -> None:
    zed_default = Path(r"C:\Users\me\AppData\Local\Zed")
    nested = zed_default / "probe-home"
    invocation = ZedInvocation(
        argv=("Zed.exe", "--user-data-dir", str(nested)),
        user_data_root=str(nested),
        discovered_from="zed --help",
    )
    with pytest.raises(ProbeError, match="ambient profile"):
        validate_zed_invocation(
            invocation,
            hermetic_root=nested,
            ambient_profile_roots=(zed_default,),
        )


def test_discovery_uses_help_text_flag_not_historical_default() -> None:
    invocation = discover_hermetic_zed_invocation(
        executable=Path(r"C:\Tools\Zed.exe"),
        version_output="Zed 1.99.0",
        help_output="  --isolated-user-data <path>  Bind editor user data to this directory\n",
        executable_sha256="a" * 64,
        hermetic_root=HERMETIC_ROOT,
    )
    assert invocation.discovered_from == "zed --help"
    assert "--isolated-user-data" in invocation.argv
    assert "--user-data-dir" not in invocation.argv
    assert invocation.user_data_root == str(HERMETIC_ROOT.resolve())
    assert invocation.environment_bind == ()
    validate_zed_invocation(invocation, hermetic_root=HERMETIC_ROOT)


def test_discovery_prefers_app_binary_from_version_path(tmp_path: Path) -> None:
    app = tmp_path / "Zed.exe"
    cli = tmp_path / "bin" / "Zed.exe"
    cli.parent.mkdir(parents=True)
    app.write_bytes(b"app")
    cli.write_bytes(b"cli")
    invocation = discover_hermetic_zed_invocation(
        executable=cli,
        version_output=f"Zed 1.15.0 deadbeef  – \\\\?\\{app}",
        help_output="  --user-data-dir <path>\n",
        executable_sha256="b" * 64,
        hermetic_root=HERMETIC_ROOT,
    )
    assert invocation.argv[0] == str(app)
    assert invocation.environment_bind == ()
    assert "--user-data-dir" in invocation.argv


def test_discovery_selects_sibling_app_when_version_omits_path(tmp_path: Path) -> None:
    """Force the ``_sibling_zed_app_binary`` tier: no path in version_output."""
    install = tmp_path / "Programs" / "Zed"
    app = install / "Zed.exe"
    cli = install / "bin" / "Zed.exe"
    cli.parent.mkdir(parents=True)
    app.write_bytes(b"app")
    cli.write_bytes(b"cli")
    invocation = discover_hermetic_zed_invocation(
        executable=cli,
        version_output="Zed 1.15.0 e17dc4f9d50db73a458b64dcce50ecd4878b98a3",
        help_output="  --user-data-dir <path>\n",
        executable_sha256="c" * 64,
        hermetic_root=HERMETIC_ROOT,
    )
    assert invocation.argv[0] == str(app.resolve())
    assert invocation.environment_bind == ()
    assert "--user-data-dir" in invocation.argv


def test_launch_argv_omits_cli_only_flags_absent_from_app_help() -> None:
    """App ``Zed.exe`` help omits ``--new``/``--wait``/``--foreground``; CLI help includes them.

    Shot 2 passed CLI-only flags to the app binary and exited 2 with no window.
    """
    invocation = ZedInvocation(
        argv=(r"C:\Programs\Zed\Zed.exe", "--user-data-dir", str(HERMETIC_ROOT)),
        user_data_root=str(HERMETIC_ROOT),
        discovered_from="zed --help",
    )
    app_help = (
        "Usage: Zed.exe [OPTIONS] [PATHS_OR_URLS]...\n"
        "      --user-data-dir <DIR>\n"
        "  -h, --help\n"
    )
    workspace = Path(r"C:\scratch\zed-workspace")
    argv = build_real_zed_launch_argv(invocation, workspace=workspace, launch_help=app_help)
    assert argv == (
        r"C:\Programs\Zed\Zed.exe",
        "--user-data-dir",
        str(HERMETIC_ROOT),
        str(workspace),
    )
    assert "--new" not in argv
    assert "--wait" not in argv
    assert "--foreground" not in argv


def test_launch_argv_keeps_cli_flags_when_launch_help_lists_them() -> None:
    invocation = ZedInvocation(
        argv=(r"C:\Programs\Zed\bin\Zed.exe", "--user-data-dir", str(HERMETIC_ROOT)),
        user_data_root=str(HERMETIC_ROOT),
        discovered_from="zed --help",
    )
    cli_help = "  --foreground\n  -n, --new\n  -w, --wait\n  --user-data-dir <DIR>\n"
    workspace = Path(r"C:\scratch\zed-workspace")
    argv = build_real_zed_launch_argv(invocation, workspace=workspace, launch_help=cli_help)
    assert "--foreground" in argv
    assert "--new" in argv
    assert "--wait" in argv
    assert argv[-1] == str(workspace)


def test_launch_log_excerpt_runs_through_evidence_sanitizer(tmp_path: Path) -> None:
    from tools.probe_p11_zed_session_load import _launch_log_excerpt

    canary = "sk-" + ("a" * 16)
    log_path = tmp_path / "zed-launch.log"
    log_path.write_text(f"startup wire-dump {canary} trailing\n", encoding="utf-8", newline="\n")
    excerpt = _launch_log_excerpt(log_path)
    assert canary not in excerpt
    assert "wire-dump" in excerpt
    assert "trailing" in excerpt


def test_discovery_fails_closed_when_help_omits_user_data_binding() -> None:
    with pytest.raises(ProbeError, match="current-version hermetic invocation"):
        discover_hermetic_zed_invocation(
            executable=Path(r"C:\Tools\Zed.exe"),
            version_output="Zed 1.99.0",
            help_output="  --foreground\n  --version\n",
            executable_sha256="a" * 64,
            hermetic_root=HERMETIC_ROOT,
        )


def test_classification_consumes_sanitized_relay_extract_not_project_client() -> None:
    extract = {
        "source": "opaque-relay-post-run",
        "zed_to_agent_sha256": "a" * 64,
        "agent_to_zed_sha256": "b" * 64,
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "saved-1"}},
        "response": {"jsonrpc": "2.0", "id": 7, "result": {}},
    }
    exchange = exchange_from_relay_extract(extract)
    assert exchange is not None
    assert exchange.request["method"] == "session/load"
    isolation = _isolation_evidence()
    assert classify_live_zed_observation(
        exchange,
        isolation,
        _valid_invocation(),
        already_running_zed=False,
        relay_failed=False,
        cleanup_roots_empty=True,
    ) is Finding.REACHABLE


def test_classification_rejects_project_authored_client_call() -> None:
    extract = {
        "source": "project-acp-client",
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load"},
        "response": {"jsonrpc": "2.0", "id": 7, "result": {}},
    }
    with pytest.raises(ProbeError, match="sanitized post-run relay extract"):
        exchange_from_relay_extract(extract)


def test_absent_descriptor_already_running_relay_failure_and_nonempty_cleanup_prevent_verdict() -> None:
    isolation = _isolation_evidence()
    exchange = _session_load_exchange()
    missing = ZedInvocation(argv=("Zed.exe",), user_data_root=None, discovered_from="")
    assert (
        classify_live_zed_observation(
            exchange, isolation, missing, already_running_zed=False, relay_failed=False, cleanup_roots_empty=True
        )
        is Finding.INDETERMINATE
    )
    assert (
        classify_live_zed_observation(
            exchange,
            isolation,
            _valid_invocation(),
            already_running_zed=True,
            relay_failed=False,
            cleanup_roots_empty=True,
        )
        is Finding.INDETERMINATE
    )
    assert (
        classify_live_zed_observation(
            exchange,
            isolation,
            _valid_invocation(),
            already_running_zed=False,
            relay_failed=True,
            cleanup_roots_empty=True,
        )
        is Finding.INDETERMINATE
    )
    assert (
        classify_live_zed_observation(
            exchange,
            isolation,
            _valid_invocation(),
            already_running_zed=False,
            relay_failed=False,
            cleanup_roots_empty=False,
        )
        is Finding.INDETERMINATE
    )
    assert zed_target_already_running(("notepad.exe", "Zed.exe")) is True
    assert zed_target_already_running(("notepad.exe",)) is False


def test_opaque_relay_command_uses_custody_relay_not_project_client() -> None:
    command = build_opaque_relay_command(
        capture_root=Path(r"C:\scratch\capture"),
        run_id="run-1",
        child_executable=Path(r"C:\scratch\optimus-agent.exe"),
        invocation=_valid_invocation(),
    )
    joined = " ".join(command)
    assert "plan117_custody_relay.py" in joined
    assert "--child-executable" in command
    assert "acpx" not in joined.casefold()


def test_acpx_baseline_fails_closed_without_isolated_load_session() -> None:
    evidence = AcpxBaselineEvidence(
        acpx_version="0.12.0",
        acpx_executable=r"C:\Tools\acpx.cmd",
        acpx_sha256="a" * 64,
        capability_payload={"sessionCapabilities": {}},
        origin_a_launches=0,
    )
    with pytest.raises(ProbeError, match="loadSession"):
        validate_acpx_baseline(evidence)


def test_acpx_baseline_accepts_isolated_advertisement_without_zed_claim() -> None:
    evidence = AcpxBaselineEvidence(
        acpx_version="0.12.0",
        acpx_executable=r"C:\Tools\acpx.cmd",
        acpx_sha256="a" * 64,
        capability_payload={"loadSession": True, "sessionCapabilities": {}},
        origin_a_launches=0,
    )
    validate_acpx_baseline(evidence)


def test_acpx_baseline_accepts_advertisement_without_live_set_mode_exchange() -> None:
    """Optimus has no session/set_mode; baseline must not require that CLI path."""
    evidence = AcpxBaselineEvidence(
        acpx_version="0.12.0",
        acpx_executable=r"C:\Tools\acpx.cmd",
        acpx_sha256="a" * 64,
        capability_payload={"loadSession": True, "sessionCapabilities": {}},
        origin_a_launches=0,
        session_load_exchange=None,
    )
    validate_acpx_baseline(evidence)


def test_acpx_baseline_rejects_non_empty_live_load_result() -> None:
    evidence = AcpxBaselineEvidence(
        acpx_version="0.12.0",
        acpx_executable=r"C:\Tools\acpx.cmd",
        acpx_sha256="a" * 64,
        capability_payload={"loadSession": True, "sessionCapabilities": {}},
        origin_a_launches=0,
        session_load_exchange={
            "request": {"method": "session/load"},
            "response": {"result": {"sessionId": "x"}},
        },
    )
    with pytest.raises(ProbeError, match="session/load with"):
        validate_acpx_baseline(evidence)


def test_real_zed_cli_mode_does_not_launch(tmp_path: Path) -> None:
    assert main(["--mode", "real-zed", str(tmp_path)]) == 1


def test_preflight_failure_retains_sanitized_command_stderr() -> None:
    result: dict[str, object] = {}
    record_probe_command_failure(
        result,
        ProbeError(
            "acpx_new_session",
            "exit=1: captured command evidence",
            CommandResult(
                command=["acpx", "sessions", "new"],
                returncode=1,
                stdout="",
                stderr="agent exited: Redis is not reachable\nOPTIMUS_API_KEY=live-secret\n",
            ),
        ),
    )
    assert result["failure"]["stage"] == "acpx_new_session"
    evidence = result["acpx_failure"]
    assert evidence["exit_code"] == 1
    assert "Redis is not reachable" in str(evidence["stderr"])
    assert "live-secret" not in json.dumps(result)


def test_baseline_empty_load_failure_keeps_stdout_records() -> None:
    result: dict[str, object] = {}
    record_probe_command_failure(
        result,
        ProbeError(
            "acpx_baseline",
            "isolated probe must answer session/load with {}",
            CommandResult(
                command=["acpx", "set-mode", "x"],
                returncode=1,
                stdout=(
                    '{"jsonrpc":"2.0","id":null,"error":{"code":-32603,'
                    '"message":"Persistent ACP session missing","data":{"detailCode":"SESSION_RESUME_REQUIRED"}}}\n'
                ),
                stderr="",
            ),
        ),
    )
    assert result["acpx_failure"]["stdout_records"]
    assert "SESSION_RESUME_REQUIRED" in json.dumps(result["acpx_failure"])


def test_iter_acp_messages_parses_ndjson_and_pairs_session_load() -> None:
    request = {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "s1"}}
    response = {"jsonrpc": "2.0", "id": 7, "result": {}}
    zed_bytes = (json.dumps(request) + "\n").encode("utf-8")
    agent_bytes = (json.dumps(response) + "\n").encode("utf-8")
    exchange = extract_session_load_from_messages(iter_acp_messages(zed_bytes), iter_acp_messages(agent_bytes))
    assert exchange is not None
    assert exchange["request"]["method"] == "session/load"
    assert exchange["response"]["result"] == {}
    reconstructed = reconstruct_sanitized_relay_bytes(iter_acp_messages(zed_bytes))
    assert b"session/load" in reconstructed


def test_iter_acp_messages_parses_content_length_frames() -> None:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode("utf-8")
    framed = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
    messages = iter_acp_messages(framed)
    assert messages[0]["method"] == "initialize"


def test_seed_hermetic_settings_and_launcher_stay_under_scratch(tmp_path: Path) -> None:
    hermetic = tmp_path / "zed-home"
    appdata = tmp_path / "zed-appdata"
    launcher = write_isolated_agent_launcher(tmp_path / "probe-build", tmp_path / "probe-source")
    settings = seed_hermetic_zed_settings(
        appdata,
        relay_command="python",
        relay_args=["relay.py", "--capture-root", str(tmp_path / "capture")],
    )
    assert launcher.is_relative_to(tmp_path)
    assert settings == (appdata / "Zed" / "settings.json").resolve()
    assert settings.is_relative_to(appdata)
    assert not (hermetic / "settings.json").exists()
    payload = json.loads(settings.read_text(encoding="utf-8"))
    assert payload["agent_servers"]["optimus"]["command"] == "python"
    assert "loadSession" not in settings.read_text(encoding="utf-8")
    assert "probe-source" in launcher.read_text(encoding="utf-8")
    bind = hermetic_appdata_environment_bind(appdata)
    assert bind == (("APPDATA", str(appdata.resolve())),)
    assert not any(key in {"USERPROFILE", "HOME", "LOCALAPPDATA"} for key, _ in bind)


def test_seed_hermetic_settings_uses_windows_appdata_zed_layout(tmp_path: Path) -> None:
    """Windows settings live under %APPDATA%\\Zed\\settings.json, not --user-data-dir."""
    appdata = tmp_path / "AppData" / "Roaming"
    settings = seed_hermetic_zed_settings(
        appdata,
        relay_command="python",
        relay_args=["relay.py"],
    )
    assert settings.name == "settings.json"
    assert settings.parent.name == "Zed"
    assert settings.parent.parent == appdata.resolve()
    bind = hermetic_appdata_environment_bind(appdata)
    assert len(bind) == 1
    assert bind[0][0] == "APPDATA"


COMMIT = "cfaffbebf184cd7e08f15749ce5aaff414991ec1"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
RAW_CAPTURE_CANARY = b"RAW_CAPTURE_CANARY=sk-live-not-for-disk"
PLAN_1124_REPORT_NAME = "plan-11-24-zed-guided-session-load-probe"


def reachable_result() -> dict[str, object]:
    """Complete sanitizer-safe REACHABLE fixture for verifier-valid materialization."""
    exchange = {
        "request": {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/load",
            "params": {"sessionId": "saved-1"},
        },
        "response": {"jsonrpc": "2.0", "id": 7, "result": {}},
    }
    return {
        "schema": "plan-11-19-zed-session-load-reprobe-v1",
        "recorded_at_utc": "2026-08-18T12:00:00+00:00",
        "commit": COMMIT,
        "finding": "REACHABLE",
        "indeterminate_reason": None,
        "zed": {
            "version": "Zed 1.15.0",
            "executable": "C:/Tools/Zed.exe",
            "executable_sha256": SHA_A,
        },
        "acpx": {
            "version": "0.12.0",
            "executable": "C:/Tools/acpx.cmd",
            "executable_sha256": SHA_B,
        },
        "normal_source": {
            "commit": COMMIT,
            "sha256_before": SHA_C,
            "sha256_after": SHA_C,
        },
        "isolated_source": {"sha256": SHA_A},
        "isolated_build": {"sha256": SHA_B},
        "invocation": {
            "discovered_from": "zed --help",
            "argv": ["C:/Tools/Zed.exe", "--isolated-user-data", "scratch/zed-home"],
            "user_data_root": "scratch/zed-home",
            "help_sha256": SHA_A,
        },
        "isolation": {
            "normal_agent_load_session_advertised": False,
            "isolated_probe_load_session_advertised": True,
            "cleanup_dry_run_verified": True,
            "cleanup_verified": True,
        },
        "capability_payload": {"loadSession": True, "sessionCapabilities": {}},
        "relay": {
            "source": "opaque-relay-post-run",
            "zed_to_agent_sha256": SHA_A,
            "agent_to_zed_sha256": SHA_B,
        },
        "captured_exchange": exchange,
        "origin_a_launches": 0,
        "zed_launches": 1,
        "_sanitized_relay_zed": b"should-not-be-serialized",
        "_secret_sidecar_key": "must-not-reach-disk",
    }


def _guided_report_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    reports_root = tmp_path / "reports"
    reports_root.mkdir()
    monkeypatch.setattr("tools.probe_p11_zed_session_load.REPORTS_ROOT", reports_root)
    return reports_root / PLAN_1124_REPORT_NAME


def _paired_sanitized_relay_bytes() -> tuple[bytes, bytes]:
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "session/load",
        "params": {"sessionId": "saved-1"},
    }
    response = {"jsonrpc": "2.0", "id": 7, "result": {}}
    return (
        reconstruct_sanitized_relay_bytes([request]),
        reconstruct_sanitized_relay_bytes([response]),
    )


def _scan_tree_for_canary(root: Path) -> list[str]:
    hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if RAW_CAPTURE_CANARY in payload or b"must-not-reach-disk" in payload:
            hits.append(path.as_posix())
    return hits


def test_nonempty_sanitized_relay_bundle_passes_existing_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir = _guided_report_dir(tmp_path, monkeypatch)
    zed_to_agent, agent_to_zed = _paired_sanitized_relay_bytes()
    raw_zed = zed_to_agent + RAW_CAPTURE_CANARY
    raw_agent = agent_to_zed + RAW_CAPTURE_CANARY
    sanitized_zed = reconstruct_sanitized_relay_bytes(iter_acp_messages(raw_zed))
    sanitized_agent = reconstruct_sanitized_relay_bytes(iter_acp_messages(raw_agent))

    manifest = materialize_sanitized_zed_evidence(
        report_dir=report_dir,
        result=reachable_result(),
        zed_to_agent=sanitized_zed,
        agent_to_zed=sanitized_agent,
    )

    verify_manifest(manifest)
    published_zed = (report_dir / "relay" / "zed-to-agent.bin").read_bytes()
    published_agent = (report_dir / "relay" / "agent-to-zed.bin").read_bytes()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert published_zed
    assert published_agent
    assert published_zed == sanitized_zed
    assert published_agent == sanitized_agent
    assert payload["relay"]["zed_to_agent_sha256"] == hashlib.sha256(published_zed).hexdigest()
    assert payload["relay"]["agent_to_zed_sha256"] == hashlib.sha256(published_agent).hexdigest()
    report_text = (report_dir / "report.md").read_text(encoding="utf-8")
    assert "Plan 11.24" in report_text
    assert "REACHABLE" in report_text
    assert "Plan 11.19" in report_text
    assert _scan_tree_for_canary(report_dir) == []
    assert RAW_CAPTURE_CANARY not in json.dumps(payload).encode("utf-8")


def test_materialize_rejects_existing_target_without_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir = _guided_report_dir(tmp_path, monkeypatch)
    report_dir.mkdir()
    sentinel = report_dir / "preexisting.txt"
    sentinel.write_text("keep-me", encoding="utf-8")
    zed_to_agent, agent_to_zed = _paired_sanitized_relay_bytes()

    with pytest.raises(ProbeError, match="existing"):
        materialize_sanitized_zed_evidence(
            report_dir=report_dir,
            result=reachable_result(),
            zed_to_agent=zed_to_agent,
            agent_to_zed=agent_to_zed,
        )

    assert sentinel.read_text(encoding="utf-8") == "keep-me"
    assert not (report_dir / "manifest.json").exists()
    assert not (report_dir / "relay").exists()


def test_materialize_rejects_target_outside_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _guided_report_dir(tmp_path, monkeypatch)
    outside = tmp_path / "not-reports" / PLAN_1124_REPORT_NAME
    zed_to_agent, agent_to_zed = _paired_sanitized_relay_bytes()

    with pytest.raises(ProbeError, match="reports"):
        materialize_sanitized_zed_evidence(
            report_dir=outside,
            result=reachable_result(),
            zed_to_agent=zed_to_agent,
            agent_to_zed=agent_to_zed,
        )

    assert not outside.exists()


def test_materialize_cleanup_failed_result_leaves_no_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir = _guided_report_dir(tmp_path, monkeypatch)
    zed_to_agent, agent_to_zed = _paired_sanitized_relay_bytes()
    result = reachable_result()
    isolation = dict(result["isolation"])  # type: ignore[arg-type]
    isolation["cleanup_verified"] = False
    result["isolation"] = isolation
    result["finding"] = "INDETERMINATE"
    result["indeterminate_reason"] = "CLEANUP_UNVERIFIED"

    with pytest.raises(ProbeError, match="cleanup"):
        materialize_sanitized_zed_evidence(
            report_dir=report_dir,
            result=result,
            zed_to_agent=zed_to_agent,
            agent_to_zed=agent_to_zed,
        )

    assert not report_dir.exists()
