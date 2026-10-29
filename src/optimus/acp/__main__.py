from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
import time
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

import keyring

from optimus.acp.auto_composition import AutoComposition, compose_auto_composition
from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server, resolve_ephemeral_hmac_flag
from optimus.acp.debug_trace import (
    configure_debug_trace,
    log_authorized_launch_comparison,
    log_provenance_once,
    resolve_debug_log_path,
)
from optimus.acp.launch_approvals import LAUNCH_POLICY_COMPATIBILITY, ApprovalError, KeyringApprovalStore
from optimus.acp.launch_audit import LaunchAuditError, LaunchAuditEvent, append_launch_audit_event
from optimus.acp.launch_gate import AuthorizedLaunch, LaunchCandidate, LaunchGateError, authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.lifecycle import NoticeControl
from optimus.acp.local_gateway_secrets import run_setup_wizard
from optimus.acp.local_infra import (
    LocalGatewayProcess,
    LocalInfrastructureError,
    apply_local_defaults,
    ensure_local_gateway,
    ensure_local_phoenix,
    ensure_local_redis,
)
from optimus.acp.operator_paths import OperatorPathConfigurationError, resolve_authorized_operator_paths
from optimus.acp.outbound_writer import DedicatedOutboundWriter
from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.acp.process_lifecycle import (
    ProcessLifecycle,
    ShutdownObservation,
    StartupTermination,
    StopReason,
    cleanup_failure,
    raise_preserving_failure,
    signal_handlers,
)
from optimus.acp.server import AcpStreamServer, StdioByteReader, StdioByteWriter, StdioNdjsonLineReader, StdioNdjsonLineWriter
from optimus.acp.stage_c import StageCLaunchError, resolve_stage_c_launch
from optimus.acp.subprocess_env import system_environ_view
from optimus.acp.test_composition import compose_test_composition
from optimus.acp.trusted_paths import (
    TrustedPathError,
    format_trusted_path_operator_message,
    resolve_trusted_operator_roots,
    resolve_workspace_security_state,
    revalidate_workspace_security_state,
)
from optimus.agent.defaults import AgentModelError, auto_requested, resolve_agent_model
from optimus.gateway.client import DEFAULT_GATEWAY_TIMEOUT_SECONDS, validate_gateway_timeout_seconds
from optimus.mcp.client_disposition import ClientMcpRuntime
from optimus.mcp.client_supervisor import MCPSupervisorState
from optimus.redis.runtime import RedisRuntime, RedisRuntimeShutdownIncomplete
from optimus_model_policy import RegistryError, binding
from optimus_model_policy.binding import APPROVAL_LITERAL_NAME, COMPOSITION_LITERAL_NAME, BindingError
from optimus_model_policy.test_profiles import TEST_PROFILE_NAMES

_OWNED_READER_TYPES = (StdioByteReader, StdioNdjsonLineReader)
_FRAMED_WRITER_TYPE = StdioByteWriter

if TYPE_CHECKING:
    from optimus.acp.stage_c import StageCLaunch
    from optimus.acp.test_composition import TestComposition


class _BuildServerKwargs(TypedDict):
    environ: Mapping[str, str]
    system_environ: Mapping[str, str]
    ephemeral_hmac: bool
    workspace_root: Path
    model: str | None
    gateway_timeout_seconds: NotRequired[float]
    test_composition: NotRequired[TestComposition]
    stage_c: NotRequired[StageCLaunch]
    auto_composition: NotRequired[AutoComposition]



def _print_log(message: str) -> None:
    print(message, file=sys.stderr)


def _report_shutdown(observation: ShutdownObservation) -> None:
    print(f"optimus-agent: SHUTDOWN_INCOMPLETE stage={observation.stage} pending={observation.pending}", file=sys.stderr)


def _stop_startup_gateway(gateway: LocalGatewayProcess, lifecycle: ProcessLifecycle, primary: BaseException | None) -> None:
    if lifecycle.gateway_attempted:
        return
    lifecycle.gateway_attempted = True
    lifecycle.begin_cleanup()
    try:
        gateway.stop()
    except BaseException as exc:
        failure = cleanup_failure(([("startup", primary)] if primary is not None else []) + [("gateway", exc)])
        process = getattr(gateway, "process", None)
        alive = bool(getattr(gateway, "stop_pending", False)) or (process is not None and process.poll() is None)
        lifecycle.record(ShutdownObservation(not alive, "gateway" if alive else "done", int(alive), ("gateway",)))
        if alive and isinstance(gateway, LocalGatewayProcess):
            failure.__dict__["_optimus_pending_gateway"] = gateway
        failure.__dict__["_optimus_cleanup_stages"] = ("gateway",)
        failure.__dict__["_optimus_cleanup_only"] = primary is None and isinstance(exc, Exception)
        try:
            _print_log("optimus-agent: SHUTDOWN_FAILED stage=gateway")
        except BaseException:
            pass
        raise_preserving_failure(failure)
    lifecycle.record(ShutdownObservation(True, "done", 0, lifecycle.observation.failure_stages))


async def _run_serving_process(
    server: Any,
    *,
    lifecycle: ProcessLifecycle,
    framed: bool = False,
    gateway_process: LocalGatewayProcess | None = None,
    reader: Any | None = None,
    writer: Any | None = None,
    observation_seconds: float = 10.0,
    start_serving: bool = True,
) -> int:
    source_reader = reader if reader is not None else (
        StdioByteReader(sys.stdin.buffer) if framed else StdioNdjsonLineReader(sys.stdin.buffer)
    )
    source_writer = writer if writer is not None else (
        StdioByteWriter(sys.stdout.buffer) if framed else StdioNdjsonLineWriter(sys.stdout.buffer)
    )
    dedicated: DedicatedOutboundWriter | None = None
    failures: list[tuple[str, BaseException]] = []
    failed: set[str] = set()

    def record_failure(stage: str, exc: BaseException) -> None:
        failed.add(stage)
        if not any(old_stage == stage and isinstance(old, Exception) == isinstance(exc, Exception) for old_stage, old in failures):
            failures.append((stage, exc))

    def pending(stage: str) -> None:
        lifecycle.record(ShutdownObservation(False, stage, 1, tuple(sorted(failed))))

    async def finish() -> ShutdownObservation:
        lifecycle.begin_cleanup()
        close_mcp = getattr(server, "_close_unused_mcp_stage", None)
        runtime = getattr(server, "client_mcp_runtime", None)
        try:
            if callable(close_mcp):
                await close_mcp()
            elif isinstance(runtime, ClientMcpRuntime) and runtime.supervisor.state is not MCPSupervisorState.DEAD:
                await asyncio.to_thread(runtime.close)
        except BaseException as exc:
            record_failure("mcp", exc)
        if isinstance(runtime, ClientMcpRuntime):
            while runtime.supervisor.state is not MCPSupervisorState.DEAD:
                pending("mcp")
                try:
                    # STOPPING close only observes/finalizes the retained generation; no SDK hook is replayed.
                    await asyncio.to_thread(runtime.supervisor.close)
                except BaseException as exc:
                    record_failure("mcp", exc)
                    await asyncio.sleep(0.1)
            if runtime._stage_failure_recorded:
                failed.add("mcp")
        elif runtime is not None:
            failed.add("mcp")  # a foreign runtime cannot establish clean production custody

        closer = dedicated if dedicated is not None else source_writer if isinstance(source_writer, _FRAMED_WRITER_TYPE) else None
        if closer is not None:
            pending("writer")
            already_observed = getattr(server, "_writer_shutdown_task", None) is not None
            try:
                close_writer = getattr(server, "_close_writer_stage", None)
                if callable(close_writer):
                    await close_writer(closer)
                else:
                    await asyncio.to_thread(closer.close_and_join)
            except BaseException as exc:
                failed.add("writer")
                if not already_observed:
                    record_failure("writer", exc)
            while closer.thread_alive:
                pending("writer")
                try:
                    await asyncio.to_thread(closer.observe_closed, 0.1)
                except BaseException:
                    failed.add("writer")
                    await asyncio.sleep(0.1)

        redis = getattr(server, "redis_runtime", None)
        if isinstance(redis, RedisRuntime):
            while True:
                pending("redis")
                try:
                    record = await redis.close_async(timeout=1.0)
                except RedisRuntimeShutdownIncomplete:
                    continue  # another observation of the same record, never another teardown
                except BaseException as exc:
                    record_failure("redis", exc)
                    failed_record = redis.teardown_record
                    if failed_record is None or not failed_record.owner_terminated:
                        await asyncio.sleep(0.1)
                        continue
                    break
                if record is not None and not record.is_clean:
                    failed.add("redis")
                break
        elif redis is not None:
            failed.add("redis")
        failed.update(getattr(server, "cleanup_failure_stages", ()))

        if gateway_process is not None:
            pending("gateway")
            lifecycle.gateway_attempted = True
            try:
                await asyncio.to_thread(gateway_process.stop)
            except BaseException as exc:
                record_failure("gateway", exc)
            process = getattr(gateway_process, "process", None)
            while getattr(gateway_process, "stop_pending", False) or (process is not None and process.poll() is None):
                pending("gateway")
                await asyncio.sleep(0.1)  # retain a failed owned stop; never repeat terminate/kill

        if isinstance(source_reader, _OWNED_READER_TYPES):
            source_reader.request_close()
            while True:
                remaining = lifecycle.remaining(observation_seconds)
                if await asyncio.to_thread(source_reader.observe_closed, min(0.1, remaining)):
                    break
                observation = ShutdownObservation(False, "borrowed_stdio", 1, tuple(sorted(failed)))
                lifecycle.record(observation)
                if remaining <= 0:
                    lifecycle.report_incomplete()
                    return observation
        return ShutdownObservation(True, "done", 0, tuple(sorted(failed)))

    async def owned() -> ShutdownObservation:
        nonlocal dedicated
        try:
            if not start_serving:
                lifecycle.begin_cleanup()
            elif framed:
                await server.serve(source_reader, source_writer, lifecycle=lifecycle)
            else:
                if hasattr(source_writer, "write_bytes") and hasattr(source_writer, "flush"):
                    dedicated = DedicatedOutboundWriter(source_writer)
                    dedicated.start()
                await server.serve_ndjson(source_reader, source_writer, dedicated_writer=dedicated,
                    notice_control=NoticeControl(), join_dedicated_writer=True, lifecycle=lifecycle)
        except BaseException as exc:
            if isinstance(server, AcpStreamServer) and server.cleanup_control_failure is not None:
                record_failure(*server.cleanup_control_failure)
            if (isinstance(exc, Exception) and isinstance(server, AcpStreamServer)
                    and server.cleanup_started and server.serving_failure is None):
                failed.update(server.cleanup_failure_stages)
            elif not (isinstance(exc, asyncio.CancelledError) and lifecycle.reason in (StopReason.SIGINT, StopReason.SIGTERM)):
                record_failure("serve", exc)
        lifecycle.begin_cleanup()
        job = asyncio.create_task(finish(), name="optimus-process-cleanup")
        cancelled: asyncio.CancelledError | None = None
        while not job.done():
            try:
                await asyncio.shield(job)
            except asyncio.CancelledError as exc:
                cancelled = cancelled or exc
            except BaseException:
                break
        observation = job.result()
        lifecycle.record(observation)
        if cancelled is not None and lifecycle.reason not in (StopReason.SIGINT, StopReason.SIGTERM):
            failures.append(("serve", cancelled))
        if failures and (any(stage == "serve" for stage, _exc in failures) or any(not isinstance(exc, Exception) for _stage, exc in failures)):
            raise_preserving_failure(cleanup_failure(failures))
        return observation

    task = asyncio.create_task(owned(), name="optimus-process-lifetime")
    lifecycle.bind(asyncio.get_running_loop(), task)
    await lifecycle.wait_for_stop()
    await lifecycle.observe(timeout=observation_seconds)
    if not task.done():
        await asyncio.shield(task)  # non-stdio ownership may genuinely remain incomplete
    code = lifecycle.exit_code
    if code is None and isinstance(source_reader, _OWNED_READER_TYPES):
        while not await asyncio.to_thread(source_reader.observe_closed, 0.1):
            pass
        lifecycle.record(ShutdownObservation(True, "done", 0, tuple(sorted(failed))))
        code = lifecycle.exit_code
    if code is None:
        raise RuntimeError("process cleanup remains incomplete")
    return code


def _parse_gateway_timeout_seconds(value: str) -> float:
    try:
        return validate_gateway_timeout_seconds(value)
    except ValueError:
        # Stable message matches validate_gateway_timeout_seconds; avoid str(exc)
        # so Plan 9.96 surface discovery does not classify this as exception_export.
        raise argparse.ArgumentTypeError(
            "gateway timeout must be a positive finite number of seconds"
        ) from None


def _short_gateway_timeout_warning(seconds: float) -> str:
    """Allowed (an explicit investigation override), but below the shared host wait (Codex round 1 on #397 Z2)."""
    return (
        f"optimus-agent: warning: --gateway-timeout-seconds {seconds:g} is below the default "
        f"{DEFAULT_GATEWAY_TIMEOUT_SECONDS:g}, which outlasts the Gateway's upstream budget for one request; a slower reply the "
        "provider has billed can be abandoned, and its turn then stops as PLANNING_GATEWAY_COST_UNKNOWN"
    )


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
        "--with-local-phoenix",
        action="store_true",
        help=(
            "After launch authorization, ensure the named local Phoenix container and pass its "
            "fixed loopback OTLP endpoint only to the Gateway child."
        ),
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
    parser.add_argument(
        "--gateway-timeout-seconds",
        type=_parse_gateway_timeout_seconds,
        default=None,
        metavar="SECONDS",
        help=f"Gateway request timeout in seconds for this process (default: {DEFAULT_GATEWAY_TIMEOUT_SECONDS:.1f}).",
    )
    # Plan 12.2 closure (release supplement V2): select one reviewed, source-owned test profile by its
    # fixed name. The name grants nothing: the launch approval must bind the profile's exact effective
    # hash, and the Gateway composes the same profile itself. Absent, the composition is today's.
    parser.add_argument(
        "--plan12-test-profile",
        choices=TEST_PROFILE_NAMES,
        default=None,
        help="Reviewed Plan 12.2 test profile; its launch approval must bind the profile's exact effective hash.",
    )
    # Plan 12.2 Task 13 (Stage C): bind the shared test envelope; its approval must bind it too.
    parser.add_argument(
        "--plan12-stage-c",
        action="store_true",
        default=False,
        help="Bind the shared Plan 12.2 Stage C test envelope (with --plan12-test-profile; its approval must bind it).",
    )
    # Internal-only arguments (Plan 9.96, Task 5 Step 2). Never documented as
    # a public operator-facing flag beyond the optimus-trust CLI, which is
    # the only intended caller: it substitutes {approval_id}/
    # {launch_session_id} placeholders into the target argv it spawns.
    parser.add_argument("--launch-approval-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--launch-session-id", default=None, help=argparse.SUPPRESS)
    # Plan 9.96, Task 6 Batch 2: same internal-only slot pattern as the two
    # arguments above. The only intended caller is optimus-trust's
    # `run --elevated-debug`, which substitutes {diagnostic_grant_id} into
    # the argv it spawns.
    parser.add_argument("--diagnostic-grant-id", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.with_local_phoenix and args.no_auto_start:
        parser.error("--with-local-phoenix cannot be combined with --no-auto-start")
    if args.with_local_phoenix and args.check_config and not args.strict:
        parser.error("--with-local-phoenix with --check-config requires --strict")
    if args.plan12_stage_c and args.plan12_test_profile is None:
        parser.error("--plan12-stage-c needs --plan12-test-profile")
    if args.plan12_test_profile is not None:
        # A profiled launch starts its own profiled Gateway child and binds every request through the
        # ndjson session adapters. A Gateway it did not start is unprofiled, the framed transport has no
        # route policy, and strict check-config sends an unbound probe: each would only end in generic
        # refusals (Fable CP4 release review M1, m2).
        for flag, chosen in (("--no-auto-start", args.no_auto_start), ("--framed", args.framed), ("--strict", args.strict)):
            if chosen:
                parser.error(f"--plan12-test-profile cannot be combined with {flag}")
    if args.framed and binding.ENFORCEMENT_ACTIVE:
        # Closure plan v3: the framed transport has no route binding, so under the enforced shipped registry every
        # request it sent would be refused as unbound. Refuse at startup instead, before any service starts.
        parser.error(
            "--framed is not supported while the trusted model registry is enforced: the framed transport has no route "
            "binding. Use the default newline-delimited JSON transport (omit --framed)."
        )
    return args


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
        workspace_state = resolve_workspace_security_state(workspace_root)
    except TrustedPathError as exc:
        print(
            format_trusted_path_operator_message(
                exc,
                prefix="optimus-agent",
                workspace_root=workspace_root,
                when="initial",
            ),
            file=sys.stderr,
        )
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
        print(
            format_trusted_path_operator_message(
                exc,
                prefix="optimus-agent",
                workspace_root=workspace_root,
                when="initial",
            ),
            file=sys.stderr,
        )
        return 2

    # Module-level `keyring` import (rather than a local import inside this
    # function) so tests can monkeypatch acp_main.keyring with a fake
    # backend without touching the real OS keychain.
    try:
        store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=roots.approval_runtime_root)
    except ApprovalError as exc:  # #433: a keyring failure reading or creating the HMAC key
        print(f"optimus-agent: {exc}", file=sys.stderr)
        return 2

    try:
        candidate: LaunchCandidate = resolve_launch_candidate(
            snapshot=snapshot,
            workspace_state=workspace_state,
            operator_paths=operator_paths,
            hmac_key=store.hmac_key,
            test_profile=args.plan12_test_profile,
            stage_c=args.plan12_stage_c,
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

    # Plan 9.96, Task 6 Batch 2: consume the diagnostic grant, if one was
    # named, AFTER the launch itself is already authorized above. Unlike
    # authorize_launch's own fail-closed behavior, an invalid/expired/
    # mismatched diagnostic grant must SILENTLY DOWNGRADE to ordinary mode
    # (diagnostic_grant stays None, no tags emitted downstream) rather than
    # fail the launch — ordinary is the SAFE mode here, and failing an
    # otherwise fully-authorized launch over a diagnostics feature that
    # isn't itself security-critical would be a pure denial-of-service.
    # Every ApprovalError code (GRANT_NOT_FOUND, GRANT_SESSION_MISMATCH,
    # GRANT_EXPIRED, GRANT_INTEGRITY_FAILURE, GRANT_CORRUPT) is treated
    # identically: silent downgrade, no stderr noise for what is, from the
    # operator's perspective, just "elevated diagnostics didn't turn on."
    diagnostic_grant = None
    if args.diagnostic_grant_id:
        try:
            diagnostic_grant = store.consume_diagnostic_grant(args.diagnostic_grant_id, launch_session_id)
        except ApprovalError:
            diagnostic_grant = None

    if diagnostic_grant is not None:
        authorized = replace(authorized, diagnostic_grant=diagnostic_grant)

    return authorized, store


def _audit_event_common_fields(authorized: AuthorizedLaunch) -> dict[str, object]:
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
    return {
        "timestamp": datetime.now(timezone.utc),
        "workspace_digest": candidate.workspace_identity.digest,
        "launch_session_id": authorized.launch_session_id,
        "approval_id": authorized.approval_id,
        "approval_mode": authorized.approval_mode,
        "registry_version": LAUNCH_POLICY_COMPATIBILITY,
        "policy_version": LAUNCH_POLICY_COMPATIBILITY,
        "setting_decisions": setting_decisions,
        "monotonic_dispositions": monotonic_dispositions,
        "rejected_names": (),
        "child_propagation_decisions": {
            "agent_child": tuple(sorted(candidate.agent_environ)),
            "gateway_child": tuple(sorted(candidate.gateway_environ)),
        },
        "diagnostic_grant_state": "none" if authorized.diagnostic_grant is None else "granted",
        "sanitizer_rule_counts": {},
    }


def _authorization_audit_events(authorized: AuthorizedLaunch) -> tuple[LaunchAuditEvent, ...]:
    common = _audit_event_common_fields(authorized)
    events: list[LaunchAuditEvent] = []
    if authorized.approval_record_state == "migrated":
        provenance = authorized.migration_provenance
        events.append(
            LaunchAuditEvent(
                **common,  # type: ignore[arg-type]
                event_type="approval_migration",
                approval_migration_disposition=(
                    provenance.disposition if provenance is not None else "legacy_v2_to_v3"
                ),
                inherited_trust=(
                    provenance.inherited_trust
                    if provenance is not None
                    else "pre_migration_assurance_not_upgraded"
                ),
                workspace_identity_disposition="equal",
                final_reason_code="AUTHORIZED",
            )
        )
    events.append(
        LaunchAuditEvent(
            **common,  # type: ignore[arg-type]
            event_type="authorization",
            approval_migration_disposition="none",
            inherited_trust=None,
            workspace_identity_disposition="equal",
            final_reason_code="AUTHORIZED",
        )
    )
    return tuple(events)


def _workspace_identity_disposition_for(exc: TrustedPathError) -> str:
    if exc.reason == "stable_identity_mismatch":
        return "stable_identity_mismatch"
    if exc.reason == "root_topology_mismatch":
        return "root_topology_mismatch"
    if any(item.disposition == "retry_exhausted" for item in exc.diagnostics):
        return "unavailable_retry_exhausted"
    return "unavailable_permanent"


def _probe_attempt_summaries(exc: TrustedPathError) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "phase": item.phase,
            "probe": item.probe,
            "attempt": item.attempt,
            "classification": item.classification,
            "disposition": item.disposition,
            "exception_type": item.exception_type,
            "errno": item.errno,
            "winerror": item.winerror,
            "return_code": item.return_code,
            "duration_ms": item.duration_ms,
        }
        for item in exc.diagnostics
    )


def _append_audit_or_exit(
    authorized: AuthorizedLaunch,
    *,
    runtime_root: Path,
    events: tuple[LaunchAuditEvent, ...] | None = None,
) -> int | None:
    """Append authorization, migration, or revalidation-failure audit events.

    Plan 9.96, Task 5 Step 6 / Plan 11.15 Task 6: audit append failure is
    fatal — there is no raw fallback. Returns an int exit code on failure
    (already printed), or None on success.
    """
    to_write = events if events is not None else _authorization_audit_events(authorized)
    for event in to_write:
        try:
            append_launch_audit_event(event, runtime_root=runtime_root)
        except LaunchAuditError as exc:
            print(
                f"optimus-agent: {exc.code}: audit could not be recorded; startup stopped.",
                file=sys.stderr,
            )
            return 2
    return None


def _append_revalidation_failure_audit_or_report(
    authorized: AuthorizedLaunch,
    exc: TrustedPathError,
    *,
    runtime_root: Path,
) -> None:
    common = _audit_event_common_fields(authorized)
    failure_event = LaunchAuditEvent(
        **common,  # type: ignore[arg-type]
        event_type="workspace_revalidation_failure",
        workspace_identity_disposition=_workspace_identity_disposition_for(exc),
        workspace_identity_attempts=_probe_attempt_summaries(exc),
        approval_migration_disposition="none",
        inherited_trust=None,
        final_reason_code=exc.code,
    )
    _append_audit_or_exit(authorized, runtime_root=runtime_root, events=(failure_event,))


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
    try:
        revalidate_workspace_security_state(candidate.workspace_state)
    except TrustedPathError as exc:
        print(
            format_trusted_path_operator_message(
                exc,
                prefix="optimus-agent",
                workspace_root=workspace_root,
                when="revalidate",
            ),
            file=sys.stderr,
        )
        _append_revalidation_failure_audit_or_report(
            authorized,
            exc,
            runtime_root=candidate.operator_paths.runtime_root,
        )
        return 2

    debug_log_path = _apply_debug_trace_args(
        args,
        workspace_root=candidate.operator_paths.workspace_root,
        default_log_path=candidate.operator_paths.debug_log_path,
    )
    if debug_log_path is not None:
        _print_log(f"ACP debug trace: {debug_log_path}")
        log_authorized_launch_comparison(authorized)

    # candidate.agent_environ is the registry projection of only the
    # AGENT_CHILD-authorized names actually PRESENT in the snapshot — it does
    # not fill in loopback URL defaults or fold in a keyring/.env.gateway-
    # resolved shared secret the operator never set explicitly as
    # OPTIMUS_API_KEY. apply_local_defaults() still performs that
    # default-filling, but now operates on the already-authorized projection
    # (never os.environ) and receives the already-resolved shared secret from
    # the candidate rather than re-resolving it.
    test_composition = None
    auto_composition = None
    stage_c_launch = None
    try:
        agent_environ = apply_local_defaults(
            candidate.agent_environ,
            config_root=candidate.operator_paths.config_root,
            resolved_shared_secret=candidate.shared_secret,
        )
        if args.plan12_test_profile is not None:
            # Release supplement V2: the named profile, re-composed from its reviewed source. The
            # operator's approval binds it through the authorized candidate's snapshot digest
            # (authorize_launch, above); this refuses any composition other than the one that
            # candidate digested.
            test_composition = compose_test_composition(
                args.plan12_test_profile, approved_literal=candidate.security_literals.get(APPROVAL_LITERAL_NAME)
            )
            test_composition.agent_model(agent_environ, cli_model=args.model)
            if args.plan12_stage_c:
                # Plan 12.2 Task 13: the approved envelope, recomposed from source; the ledger the release
                # ceremony created must exist. Refused here, before any service starts.
                stage_c_launch = resolve_stage_c_launch(candidate, test_composition)
        elif auto_requested(agent_environ, cli_model=args.model):
            # Plan 12.4 Design 1: the Auto composition, re-composed and refused unless it is the one the authorized
            # candidate digested, with its composition name bound beside its hash.
            auto_composition = compose_auto_composition(
                approved_literal=candidate.security_literals.get(APPROVAL_LITERAL_NAME),
                composition=candidate.security_literals.get(COMPOSITION_LITERAL_NAME),
            )
            auto_composition.default_model()
            # Plan 12.4 Task 5: the classifier model is checked here too, before Redis, the Gateway or the server start.
            auto_composition.classifier_model()
        else:
            # Plan 12.2 Task 5: under an enforced model registry an unusable model fails here with a
            # typed message rather than inside the runtime composition. Inactive: today's rules.
            resolve_agent_model(agent_environ, cli_model=args.model)
    except AgentModelError as exc:
        print(f"optimus-agent: AGENT_MODEL_INVALID: {exc}", file=sys.stderr)
        return 2
    except (BindingError, RegistryError) as exc:
        print(f"optimus-agent: MODEL_REGISTRY_INVALID: {exc.code}", file=sys.stderr)
        return 2
    except StageCLaunchError as exc:
        print(f"optimus-agent: {exc.code}", file=sys.stderr)
        return 2

    def _start_local_dependencies() -> tuple[str | None, int | None]:
        """Start Redis (+ optional Phoenix). Returns (otlp_endpoint, error_exit)."""
        try:
            ensure_local_redis(agent_environ.get("OPTIMUS_REDIS_URL", ""), log=_print_log)
            if args.with_local_phoenix:
                return ensure_local_phoenix(log=_print_log), None
        except LocalInfrastructureError as exc:
            print(f"optimus-agent: {exc.user_message}", file=sys.stderr)
            return None, 2
        return None, None

    def _start_gateway(*, otlp_endpoint: str | None):
        return ensure_local_gateway(
            gateway_url=agent_environ.get("OPTIMUS_GATEWAY_URL", ""),
            provider_credentials=candidate.provider_credentials,
            shared_secret=candidate.shared_secret,
            workspace_digest=candidate.workspace_identity.digest,
            security_snapshot_digest=candidate.security_snapshot_digest,
            manifest_hmac_key=store.hmac_key,
            policy_version=LAUNCH_POLICY_COMPATIBILITY,
            runtime_root=candidate.operator_paths.runtime_root,
            system_env=snapshot.values,
            config_root=candidate.operator_paths.config_root,
            otlp_endpoint=otlp_endpoint,
            log=_print_log,
            # Plan 12.2 Task 5: the registry literal the operator approved, or None while inactive.
            model_registry=candidate.security_literals.get(APPROVAL_LITERAL_NAME),
            test_profile=args.plan12_test_profile,
            auto_composition=auto_composition is not None,
            stage_c_envelope=None if stage_c_launch is None else stage_c_launch.envelope.literal,
            stage_c_ledger=None if stage_c_launch is None else stage_c_launch.ledger,
        )

    lifecycle = ProcessLifecycle(report=_report_shutdown)
    configured_server: Any | None = None
    startup_control = False

    def run_authorized() -> int:
        nonlocal configured_server, startup_control
        startup_failure: BaseException | None = None
        if args.check_config:
            gateway_process = None
            try:
                otlp_endpoint = None
                if not args.no_auto_start:
                    otlp_endpoint, error_exit = _start_local_dependencies()
                    if error_exit is not None:
                        return error_exit
                    # Strict check-config (and Phoenix, which requires strict) must exercise
                    # the Gateway path that receives OTLP configuration.
                    if args.strict or args.with_local_phoenix:
                        gateway_process = _start_gateway(otlp_endpoint=otlp_endpoint)
                try:
                    run_preflight(
                        agent_environ,
                        workspace_root=workspace_root,
                        strict=args.strict,
                        require_timeseries=True,
                        cli_model=args.model,
                    )
                except PreflightFailure as exc:
                    print(f"optimus-agent: {exc.user_message}", file=sys.stderr)
                    return exc.exit_code
                log_provenance_once()
                print("Optimus ACP agent configuration OK.", file=sys.stderr)
                return 0
            except BaseException as exc:
                startup_failure = exc
                if not lifecycle.bound and lifecycle.reason in (StopReason.SIGINT, StopReason.SIGTERM):
                    startup_control = isinstance(exc, (KeyboardInterrupt, StartupTermination))
                raise
            finally:
                if gateway_process is not None:
                    _stop_startup_gateway(gateway_process, lifecycle, startup_failure)

        gateway_process = None
        startup_failure = None
        # Single try/finally around BOTH build_configured_server(...) and serve(...): an earlier draft
        # of this plan wrapped only the serve() call, so an unexpected (non-StartupConfigurationError)
        # exception from build_configured_server() would skip both the except block below and the
        # inner finally, leaking the already-spawned gateway_process. Nesting everything inside one
        # outer finally means every exit path — normal completion, StartupConfigurationError, or any
        # other exception — stops it exactly once.
        try:
            if not args.no_auto_start:
                otlp_endpoint, error_exit = _start_local_dependencies()
                if error_exit is not None:
                    return error_exit
                gateway_process = _start_gateway(otlp_endpoint=otlp_endpoint)
                if test_composition is not None and gateway_process is None:
                    # The profiled launch owns its profiled Gateway child. A Gateway already listening, or none
                    # at all, would refuse every bound request with a generic text (Fable CP4 release review M1).
                    print(
                        "optimus-agent: TEST_PROFILE_GATEWAY_NOT_STARTED: a test-profile launch must start its own "
                        "profiled Gateway; stop any Gateway already listening on the configured URL and see the "
                        "local gateway log.",
                        file=sys.stderr,
                    )
                    return 2
            try:
                # Seam 3: MCP construction reads PATH/PATHEXT/SystemRoot and the
                # ephemeral-HMAC request from the ORIGINAL launch snapshot, projected to
                # allowlisted system names only. agent_environ is the registry
                # projection -- it has already lost the system keys and legitimately
                # carries the Gateway credential, which must not cross the narrower MCP
                # subprocess boundary. Both views are derived from the one capture.
                build_server_kwargs: _BuildServerKwargs = {
                    "environ": agent_environ,
                    "system_environ": system_environ_view(snapshot.values),
                    "ephemeral_hmac": resolve_ephemeral_hmac_flag(snapshot.values),
                    "workspace_root": workspace_root,
                    "model": args.model,
                }
                if args.gateway_timeout_seconds is not None:
                    build_server_kwargs["gateway_timeout_seconds"] = args.gateway_timeout_seconds
                    if args.gateway_timeout_seconds < DEFAULT_GATEWAY_TIMEOUT_SECONDS:
                        print(_short_gateway_timeout_warning(args.gateway_timeout_seconds), file=sys.stderr)
                if test_composition is not None:
                    build_server_kwargs["test_composition"] = test_composition
                if stage_c_launch is not None:
                    build_server_kwargs["stage_c"] = stage_c_launch
                if auto_composition is not None:
                    build_server_kwargs["auto_composition"] = auto_composition
                server = build_configured_server(**build_server_kwargs)
                configured_server = server
            except StartupConfigurationError as exc:
                print(f"optimus-agent: {exc.user_message}", file=sys.stderr)
                return exc.exit_code
            except ApprovalError as exc:  # #433: the server's approval store hit a keyring failure
                print(f"optimus-agent: {exc}", file=sys.stderr)
                return 2

            return asyncio.run(_run_serving_process(server, lifecycle=lifecycle, framed=args.framed, gateway_process=gateway_process))
        except BaseException as exc:
            startup_failure = exc
            if not lifecycle.bound and lifecycle.reason in (StopReason.SIGINT, StopReason.SIGTERM):
                startup_control = isinstance(exc, (KeyboardInterrupt, StartupTermination))
            raise
        finally:
            if configured_server is not None and not lifecycle.bound:
                asyncio.run(_run_serving_process(configured_server, lifecycle=lifecycle, framed=args.framed,
                    gateway_process=gateway_process, start_serving=False))
            if gateway_process is not None and not lifecycle.gateway_attempted:
                _stop_startup_gateway(gateway_process, lifecycle, startup_failure)
        return 0

    with signal_handlers(lifecycle):
        try:
            return run_authorized()
        except BaseException as exc:
            retained = getattr(exc, "_optimus_pending_gateway", None)
            if isinstance(retained, LocalGatewayProcess):
                lifecycle.begin_cleanup()
                while retained.stop_pending or (retained.process is not None and retained.process.poll() is None):
                    lifecycle.record(ShutdownObservation(False, "gateway", 1, ("gateway",)))
                    if lifecycle.remaining() <= 0:
                        lifecycle.report_incomplete()
                    time.sleep(0.1)
                lifecycle.record(ShutdownObservation(True, "done", 0, ("gateway",)))
            stages = getattr(exc, "_optimus_cleanup_stages", ())
            if stages:
                lifecycle.record(ShutdownObservation(True, "done", 0, stages))
            if startup_control or (not lifecycle.bound and lifecycle.reason in (StopReason.SIGINT, StopReason.SIGTERM)
                    and isinstance(exc, (KeyboardInterrupt, StartupTermination))):
                if lifecycle.observation.pending == 0 and not lifecycle.observation.failure_stages:
                    lifecycle.record(ShutdownObservation(True, "done", 0, ()))
                code = lifecycle.exit_code
                if code is not None:
                    return code
            if getattr(exc, "_optimus_cleanup_only", False):
                return 74
            raise


if __name__ == "__main__":
    raise SystemExit(main())
