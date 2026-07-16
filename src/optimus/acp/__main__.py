from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

import keyring

from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server
from optimus.acp.debug_trace import configure_debug_trace, log_provenance_once, resolve_debug_log_path
from optimus.acp.launch_approvals import LAUNCH_POLICY_COMPATIBILITY, KeyringApprovalStore
from optimus.acp.launch_audit import LaunchAuditError, LaunchAuditEvent, append_launch_audit_event
from optimus.acp.launch_gate import AuthorizedLaunch, LaunchCandidate, LaunchGateError, authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.local_gateway_secrets import run_setup_wizard
from optimus.acp.local_infra import (
    apply_local_defaults,
    ensure_local_gateway,
    ensure_local_redis,
)
from optimus.acp.operator_paths import OperatorPathConfigurationError, resolve_authorized_operator_paths
from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.acp.server import StdioByteReader, StdioByteWriter, StdioNdjsonLineReader, StdioNdjsonLineWriter
from optimus.acp.trusted_paths import (
    TrustedPathError,
    resolve_trusted_operator_roots,
    resolve_workspace_identity,
    revalidate_workspace_identity,
)


def _print_log(message: str) -> None:
    print(message, file=sys.stderr)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="optimus-agent")
    parser.add_argument("--workspace-root", default=".", help="Workspace root exposed to the ACP agent.")
    parser.add_argument("--model", default=None, help="Gateway model for agent planning.")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration and exit.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="With --check-config, probe gateway authentication in addition to Redis checks.",
    )
    parser.add_argument(
        "--framed",
        action="store_true",
        help="Use Content-Length framed JSON-RPC instead of newline-delimited JSON (IDE default is ndjson).",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Interactively store local gateway credentials in the OS keychain, then exit.",
    )
    parser.add_argument(
        "--no-auto-start",
        action="store_true",
        help="Do not auto-start local Redis or the local gateway process; assume they are already running.",
    )
    parser.add_argument(
        "--debug-trace",
        action="store_true",
        help="Enable ACP protocol debug tracing to an NDJSON log file (never stdout).",
    )
    parser.add_argument(
        "--debug-log",
        default=None,
        metavar="PATH",
        help=(
            "Debug trace log path. Relative paths resolve under --workspace-root. "
            "Default with --debug-trace: .optimus/debug-acp.ndjson"
        ),
    )
    # Internal-only arguments (Plan 9.96, Task 5 Step 2). Never documented as
    # a public operator-facing flag beyond the optimus-trust CLI, which is
    # the only intended caller: it substitutes {approval_id}/
    # {launch_session_id} placeholders into the target argv it spawns.
    parser.add_argument("--launch-approval-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--launch-session-id", default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def _apply_debug_trace_args(
    args: argparse.Namespace,
    *,
    workspace_root: Path,
    default_log_path: Path,
) -> Path | None:
    if not args.debug_trace:
        return None
    resolved = resolve_debug_log_path(
        workspace_root=workspace_root,
        log_path=args.debug_log or default_log_path,
    )
    configure_debug_trace(enabled=True, log_path=resolved, provenance_root=workspace_root)
    return resolved


def _no_approval_remediation(workspace_root: Path) -> str:
    return (
        "optimus-agent: no launch approval found for this workspace. Review the effective "
        "configuration and author one with:\n"
        f"  optimus-trust --workspace-root {workspace_root} approve --mode durable"
    )


def _snapshot_mismatch_remediation(workspace_root: Path) -> str:
    return (
        "optimus-agent: effective configuration changed since the last approval. Review the new "
        "configuration and re-approve with:\n"
        f"  optimus-trust --workspace-root {workspace_root} approve --mode durable"
    )


def _authorize_or_exit(
    *,
    snapshot: LaunchEnvironmentSnapshot,
    workspace_root: Path,
    args: argparse.Namespace,
) -> tuple[AuthorizedLaunch, KeyringApprovalStore] | int:
    """Resolve the launch candidate and authorize it against the keyring
    approval store.

    Plan 9.96, Task 5 Step 2: this is the ONLY place __main__.py resolves a
    candidate or checks authorization. It is called before any Redis,
    Gateway, agent, debug-file, or preflight side effect — including for
    --check-config, which is a diagnostic over the SAME gated path, not a
    bypass of it (see the plan's Task 5 Deliverable: "No Redis, Gateway,
    agent, debug file, preflight, or child starts before exact
    authorization"). Malformed configuration is still reported before an
    approval is required, because resolve_launch_candidate() runs (and can
    raise LaunchGateError) before authorize_launch() is reached.

    Returns either (AuthorizedLaunch, store) on success, or an int exit code
    on failure (already printed to stderr).
    """
    try:
        workspace_identity = resolve_workspace_identity(workspace_root)
    except TrustedPathError as exc:
        print(f"optimus-agent: {exc}", file=sys.stderr)
        return 2

    try:
        operator_paths = resolve_authorized_operator_paths(
            workspace_root=workspace_root,
            snapshot_values=snapshot.values,
            platform_name=sys.platform,
        )
    except OperatorPathConfigurationError as exc:
        print(f"optimus-agent: {exc.user_message}", file=sys.stderr)
        return exc.exit_code

    try:
        roots = resolve_trusted_operator_roots(platform_name=sys.platform)
    except TrustedPathError as exc:
        print(f"optimus-agent: {exc}", file=sys.stderr)
        return 2

    # Module-level `keyring` import (rather than a local import inside this
    # function) so tests can monkeypatch acp_main.keyring with a fake
    # backend without touching the real OS keychain.
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=roots.approval_runtime_root)

    try:
        candidate: LaunchCandidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_identity=workspace_identity,
            operator_paths=operator_paths,
            hmac_key=store.hmac_key,
        )
    except LaunchGateError as exc:
        print(f"optimus-agent: {exc.code}" + (f": {exc.detail}" if exc.detail else ""), file=sys.stderr)
        return 2

    launch_session_id = args.launch_session_id or f"sess_{secrets.token_hex(12)}"

    try:
        authorized = authorize_launch(
            candidate=candidate,
            store=store,
            approval_id=args.launch_approval_id,
            launch_session_id=launch_session_id,
        )
    except LaunchGateError as exc:
        if exc.code == "NO_APPROVAL":
            print(_no_approval_remediation(workspace_root), file=sys.stderr)
        elif exc.code == "SNAPSHOT_MISMATCH":
            print(_snapshot_mismatch_remediation(workspace_root), file=sys.stderr)
        else:
            print(f"optimus-agent: {exc.code}" + (f": {exc.detail}" if exc.detail else ""), file=sys.stderr)
        return 2

    return authorized, store


def _append_audit_or_exit(authorized: AuthorizedLaunch, *, runtime_root: Path) -> int | None:
    """Append the LaunchAuditEvent before any child/network startup.

    Plan 9.96, Task 5 Step 6: audit append failure is fatal — there is no
    raw fallback. Returns an int exit code on failure (already printed), or
    None on success.
    """
    candidate = authorized.candidate
    setting_decisions = tuple(
        {
            "name": row.name,
            "tier": row.tier.value,
            "source_class": row.source_class,
            "decision": row.decision,
        }
        for row in candidate.display_rows
    )
    monotonic_dispositions = tuple(
        {"name": name, "disposition": "recorded"} for name in sorted(candidate.monotonic_grants)
    )
    event = LaunchAuditEvent(
        timestamp=datetime.now(timezone.utc),
        workspace_digest=candidate.workspace_identity.digest,
        launch_session_id=authorized.launch_session_id,
        approval_id=authorized.approval_id,
        approval_mode=authorized.approval_mode,
        registry_version=LAUNCH_POLICY_COMPATIBILITY,
        policy_version=LAUNCH_POLICY_COMPATIBILITY,
        setting_decisions=setting_decisions,
        monotonic_dispositions=monotonic_dispositions,
        rejected_names=(),
        child_propagation_decisions={
            "agent_child": tuple(sorted(candidate.agent_environ)),
            "gateway_child": tuple(sorted(candidate.gateway_environ)),
        },
        diagnostic_grant_state="none" if authorized.diagnostic_grant is None else "granted",
        sanitizer_rule_counts={},
        final_reason_code="AUTHORIZED",
    )
    try:
        append_launch_audit_event(event, runtime_root=runtime_root)
    except LaunchAuditError as exc:
        print(f"optimus-agent: {exc.code}: audit could not be recorded; startup stopped.", file=sys.stderr)
        return 2
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    # Global Constraint 6: os.environ is read EXACTLY ONCE, here, into the
    # immutable snapshot. Every downstream decision in this function and
    # every helper it calls must read from snapshot.values / the resolved
    # candidate/authorized objects — never os.environ again.
    snapshot = LaunchEnvironmentSnapshot.capture(os.environ)
    workspace_root = Path(args.workspace_root).resolve()

    if args.setup:
        # Storing a credential is not a launch: it touches no Redis/Gateway/
        # agent/preflight probe, so it is exempt from full authorization —
        # matching optimus-trust's _cmd_setup_credentials, which resolves
        # trusted roots directly rather than through the launch gate.
        try:
            operator_paths = resolve_authorized_operator_paths(
                workspace_root=workspace_root,
                snapshot_values=snapshot.values,
                platform_name=sys.platform,
            )
        except OperatorPathConfigurationError as exc:
            print(f"optimus-agent: {exc.user_message}", file=sys.stderr)
            return exc.exit_code
        return run_setup_wizard(config_root=operator_paths.config_root)

    result = _authorize_or_exit(snapshot=snapshot, workspace_root=workspace_root, args=args)
    if isinstance(result, int):
        return result
    authorized, store = result
    candidate = authorized.candidate

    audit_failure = _append_audit_or_exit(authorized, runtime_root=candidate.operator_paths.runtime_root)
    if audit_failure is not None:
        return audit_failure

    # Plan 9.96, Task 5 Step 7 (TOCTOU matrix): workspace identity is a
    # filesystem BINDING consumed again at spawn time (the child cwd's into
    # workspace_root), not a value captured once into the immutable
    # snapshot/candidate. Unlike os.environ, .env.gateway bytes, and the
    # keyring HMAC key -- all read exactly once and never reread, so
    # tampering with them after authorization has no effect by construction
    # -- a workspace relocation or symlink retarget in the window between
    # authorize_launch() succeeding and the first side effect below would go
    # completely undetected without an explicit revalidation call. This is
    # the one TOCTOU vector that needs active re-checking, placed as early
    # as possible after audit and before any Redis/Gateway/agent probe.
    # Plan 9.96, Task 5 Step 7 (TOCTOU matrix): workspace identity is a
    # filesystem BINDING consumed again at spawn time (the child cwd's into
    # workspace_root), not a value captured once into the immutable
    # snapshot/candidate. Unlike os.environ, .env.gateway bytes, and the
    # keyring HMAC key -- all read exactly once and never reread, so
    # tampering with them after authorization has no effect by construction
    # -- a workspace relocation or symlink retarget in the window between
    # authorize_launch() succeeding and the first side effect below would go
    # completely undetected without an explicit revalidation call. This is
    # the one TOCTOU vector that needs active re-checking, placed as early
    # as possible after audit and before any Redis/Gateway/agent probe.
    try:
        revalidate_workspace_identity(candidate.workspace_identity)
    except TrustedPathError as exc:
        print(f"optimus-agent: {exc}", file=sys.stderr)
        return 2

    debug_log_path = _apply_debug_trace_args(
        args,
        workspace_root=candidate.operator_paths.workspace_root,
        default_log_path=candidate.operator_paths.debug_log_path,
    )
    if debug_log_path is not None:
        _print_log(f"ACP debug trace: {debug_log_path}")

    # candidate.agent_environ is the registry projection of only the
    # AGENT_CHILD-authorized names actually PRESENT in the snapshot — it does
    # not fill in loopback URL defaults or fold in a keyring/.env.gateway-
    # resolved shared secret the operator never set explicitly as
    # OPTIMUS_API_KEY. apply_local_defaults() still performs that
    # default-filling, but now operates on the already-authorized projection
    # (never os.environ) and receives the already-resolved shared secret from
    # the candidate rather than re-resolving it.
    agent_environ = apply_local_defaults(
        candidate.agent_environ,
        config_root=candidate.operator_paths.config_root,
        resolved_shared_secret=candidate.shared_secret,
    )

    if args.check_config:
        if not args.no_auto_start:
            ensure_local_redis(agent_environ.get("OPTIMUS_REDIS_URL", ""), log=_print_log)
        try:
            run_preflight(
                agent_environ,
                workspace_root=workspace_root,
                strict=args.strict,
                require_timeseries=True,
            )
        except PreflightFailure as exc:
            print(exc.user_message, file=sys.stderr)
            return exc.exit_code
        log_provenance_once()
        print("Optimus ACP agent configuration OK.", file=sys.stderr)
        return 0

    gateway_process = None
    if not args.no_auto_start:
        ensure_local_redis(agent_environ.get("OPTIMUS_REDIS_URL", ""), log=_print_log)
        gateway_process = ensure_local_gateway(
            gateway_url=agent_environ.get("OPTIMUS_GATEWAY_URL", ""),
            provider_credentials=candidate.provider_credentials,
            shared_secret=candidate.shared_secret,
            workspace_digest=candidate.workspace_identity.digest,
            security_snapshot_digest=candidate.security_snapshot_digest,
            manifest_hmac_key=store.hmac_key,
            policy_version=LAUNCH_POLICY_COMPATIBILITY,
            runtime_root=candidate.operator_paths.runtime_root,
            system_env=snapshot.values,
            log=_print_log,
        )

    # Single try/finally around BOTH build_configured_server(...) and serve(...): an earlier draft
    # of this plan wrapped only the serve() call, so an unexpected (non-StartupConfigurationError)
    # exception from build_configured_server() would skip both the except block below and the
    # inner finally, leaking the already-spawned gateway_process. Nesting everything inside one
    # outer finally means every exit path — normal completion, StartupConfigurationError, or any
    # other exception — stops it exactly once.
    try:
        try:
            server = build_configured_server(environ=agent_environ, workspace_root=workspace_root, model=args.model)
        except StartupConfigurationError as exc:
            print(exc.user_message, file=sys.stderr)
            return exc.exit_code

        if args.framed:
            asyncio.run(server.serve(StdioByteReader(sys.stdin.buffer), StdioByteWriter(sys.stdout.buffer)))
        else:
            asyncio.run(
                server.serve_ndjson(
                    StdioNdjsonLineReader(sys.stdin.buffer),
                    StdioNdjsonLineWriter(sys.stdout.buffer),
                )
            )
    finally:
        if gateway_process is not None:
            gateway_process.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
