"""Interactive writer-only optimus-trust CLI command.

Plan 9.96, Task 4 Step 5: Commands are setup-credentials, approve --mode durable,
approve --mode one-shot -- <argv>, inspect, revoke, and rotate-key.
Authoring and rotation require stdin.isatty() and stdout.isatty().
One-shot target argv may contain {approval_id} and {launch_session_id} placeholders;
replace them in-memory, invoke with shell=False, never print the identifiers, and
delete the one-shot record if spawning fails.
"""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from optimus.acp.launch_approvals import (
    LAUNCH_POLICY_COMPATIBILITY,
    ApprovalError,
    ClientMcpReviewDisplay,
    KeyringApprovalStore,
    build_approval_record,
    compute_secret_fingerprint,
    format_client_mcp_review_lines,
)
from optimus.acp.launch_gate import (
    LaunchCandidate,
    LaunchGateError,
    authorize_launch,
    resolve_launch_candidate,
    validate_config_file_permissions,
)
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot, project_gateway_tool_child_env
from optimus.acp.local_gateway_secrets import (
    ProviderCredentialConfigurationError,
    _parse_env_gateway_file,
    resolve_provider_credentials,
    resolve_shared_secret,
)
from optimus.acp.local_infra import LocalInfrastructureError, ensure_local_phoenix
from optimus.acp.operator_paths import (
    OperatorPaths,
    WorkspaceRuntimeRootError,
    bootstrap_workspace_runtime_root,
    resolve_authorized_operator_paths,
)
from optimus.acp.trusted_paths import (
    TrustedOperatorRoots,
    TrustedPathError,
    format_trusted_path_operator_message,
    resolve_trusted_operator_roots,
    resolve_workspace_identity,
    resolve_workspace_security_state,
)
from optimus.mcp.client_config import ClientMcpSafeIdentity
from optimus.mcp.client_trust import (
    ClientMcpDurableStore,
    ClientMcpTrustError,
    EffectCeiling,
    compute_identity_fingerprint,
    derive_ipc_auth_key,
    write_client_mcp_durable_from_fingerprint,
)
from optimus.mcp.local_ipc import PendingClientMcpCandidateEndpoint, SafeCandidateSnapshot
from optimus_security.launch_manifest import build_gateway_child_manifest, serialize_gateway_child_manifest
from optimus_security.sanitization import mask_uri_userinfo


class CliError(SystemExit):
    """CLI error with user-facing message."""

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        self.message = message
        super().__init__(exit_code)


def _require_tty() -> None:
    """Authoring and rotation require both stdin and stdout to be a TTY."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise CliError(
            "optimus-trust: this command requires an interactive terminal (TTY). "
            "Headless processes cannot author, rotate, or revoke approvals.",
            exit_code=2,
        )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="optimus-trust",
        description="Manage operator launch approvals for the Optimus Cost Agent.",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root for approval binding (default: current directory).",
    )

    subparsers = parser.add_subparsers(dest="command")

    # approve
    approve_parser = subparsers.add_parser("approve", help="Author a new launch approval.")
    approve_parser.add_argument(
        "--mode",
        choices=["durable", "one-shot"],
        required=True,
        help="Approval mode: durable (persists) or one-shot (single use).",
    )
    # Remaining args after -- are the target argv for one-shot spawning.
    approve_parser.add_argument(
        "target_argv",
        nargs=argparse.REMAINDER,
        default=[],
        help="Target command for one-shot (after --).",
    )

    # inspect
    subparsers.add_parser("inspect", help="Display approval metadata (no secrets).")

    # revoke
    subparsers.add_parser("revoke", help="Revoke the durable approval for this workspace.")

    # rotate-key
    subparsers.add_parser("rotate-key", help="Rotate the HMAC integrity key (invalidates all approvals).")

    # setup-credentials
    subparsers.add_parser("setup-credentials", help="Interactively store provider credentials.")

    # run (with optional --elevated-debug)
    run_parser = subparsers.add_parser("run", help="Run a command with an existing durable approval.")
    run_parser.add_argument(
        "--elevated-debug",
        action="store_true",
        help="Enable elevated diagnostic output for this launch.",
    )
    run_parser.add_argument(
        "target_argv",
        nargs=argparse.REMAINDER,
        default=[],
        help="Target command (after --).",
    )

    # run-gateway
    run_gateway_parser = subparsers.add_parser(
        "run-gateway", help="Start the local gateway with approval ceremony."
    )
    run_gateway_parser.add_argument(
        "--with-local-phoenix",
        action="store_true",
        default=False,
        help="Auto-start local Phoenix and inject OTEL_EXPORTER_OTLP_ENDPOINT into the Gateway child only.",
    )

    mcp_parser = subparsers.add_parser("mcp", help="Client-supplied ACP MCP trust ceremony.")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_review = mcp_sub.add_parser("review", help="Author a durable client-MCP trust record.")
    mcp_review.add_argument(
        "--fingerprint",
        default=None,
        help="Rendered identity fingerprint (required for --no-ipc; must match derived identity).",
    )
    mcp_review.add_argument("--server-name", default=None, help="ASCII model-safe server name (manual path).")
    mcp_review.add_argument(
        "--no-ipc",
        action="store_true",
        default=False,
        help="Manual review fallback when pending-candidate IPC is unavailable.",
    )
    mcp_review.add_argument("--transport", default="http", choices=["stdio", "http", "sse"])
    mcp_review.add_argument(
        "--canonical-target",
        default=None,
        help="Canonical executable or URL identity (required for --no-ipc).",
    )
    mcp_review.add_argument("--candidate-id", default=None, help="Opaque pending candidate id from IPC.")
    mcp_review.add_argument(
        "--ipc-address",
        default=None,
        help="Local AF_PIPE/AF_UNIX address for pending-candidate IPC.",
    )
    mcp_review.add_argument(
        "--effect-ceiling",
        default=None,
        choices=["non_mutating", "side_effect_eligible"],
        help="Operator-selected client effect ceiling (default: prompt / non_mutating).",
    )
    mcp_review.add_argument(
        "--credential-name",
        action="append",
        default=[],
        help="Named credential field (header/env/query name) for manual review display/binding.",
    )
    mcp_review.add_argument(
        "--credential-fingerprint",
        action="append",
        default=[],
        help="Keyed credential fingerprint matching --credential-name order (manual path).",
    )
    mcp_review.add_argument(
        "--received-at",
        default=None,
        help="Optional ISO-8601 received-at provenance for operator display.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the optimus-trust CLI."""
    args = _parse_args(argv)

    if args.command is None:
        _parse_args(["--help"])
        return 0

    workspace_root = Path(args.workspace_root).resolve()

    try:
        if args.command == "approve":
            return _cmd_approve(workspace_root, mode=args.mode, target_argv=args.target_argv)
        if args.command == "inspect":
            return _cmd_inspect(workspace_root)
        if args.command == "revoke":
            return _cmd_revoke(workspace_root)
        if args.command == "rotate-key":
            return _cmd_rotate_key(workspace_root)
        if args.command == "setup-credentials":
            return _cmd_setup_credentials(workspace_root)
        if args.command == "run":
            return _cmd_run(workspace_root, target_argv=args.target_argv, elevated_debug=args.elevated_debug)
        if args.command == "run-gateway":
            return _cmd_run_gateway_default(
                workspace_root,
                with_local_phoenix=bool(getattr(args, "with_local_phoenix", False)),
            )
        if args.command == "mcp":
            if getattr(args, "mcp_command", None) != "review":
                print("optimus-trust: mcp requires a subcommand (review)", file=sys.stderr)
                return 2
            return _cmd_mcp_review(
                workspace_root,
                fingerprint=args.fingerprint,
                server_name=args.server_name,
                no_ipc=bool(args.no_ipc),
                transport=args.transport,
                canonical_target=args.canonical_target,
                candidate_id=args.candidate_id,
                ipc_address=args.ipc_address,
                effect_ceiling=getattr(args, "effect_ceiling", None),
                credential_names=tuple(getattr(args, "credential_name", None) or ()),
                credential_fingerprints=tuple(getattr(args, "credential_fingerprint", None) or ()),
                received_at=getattr(args, "received_at", None),
            )
    except CliError as exc:
        print(exc.message, file=sys.stderr)
        return exc.code
    except TrustedPathError as exc:
        print(
            format_trusted_path_operator_message(
                exc,
                prefix="optimus-trust",
                workspace_root=workspace_root,
                when="initial",
            ),
            file=sys.stderr,
        )
        return 2
    except ApprovalError as exc:
        print(f"optimus-trust: {exc}", file=sys.stderr)
        return 2
    except LaunchGateError as exc:
        print(f"optimus-trust: {exc}", file=sys.stderr)
        return 2
    except WorkspaceRuntimeRootError as exc:
        print(f"optimus-trust: {exc.code}", file=sys.stderr)
        return 2

    print(f"optimus-trust: unknown command '{args.command}'", file=sys.stderr)
    return 2


def _resolve_trusted_roots() -> TrustedOperatorRoots:
    """Resolve OS-derived trusted roots. NEVER reads inherited APPDATA/HOME/
    XDG_CONFIG_HOME (Plan 9.96 Global Constraint 8)."""
    return resolve_trusted_operator_roots(platform_name=sys.platform)


def _resolve_store(workspace_root: Path) -> tuple[KeyringApprovalStore, Path]:
    """Resolve the approval store from trusted roots."""
    import keyring as keyring_backend

    roots = _resolve_trusted_roots()
    store = KeyringApprovalStore(
        keyring_backend=keyring_backend,
        runtime_root=roots.approval_runtime_root,
    )
    return store, roots.approval_runtime_root


def _prepare_candidate_context(workspace_root: Path) -> tuple[LaunchEnvironmentSnapshot, OperatorPaths]:
    """Capture the one authorization snapshot and resolve its operator paths.

    This common preparation is deliberately non-bootstrapping so headless
    durable-record consumers such as ``optimus-trust run`` cannot initialize
    a workspace runtime root.
    """
    snapshot = LaunchEnvironmentSnapshot.capture(os.environ)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace_root,
        snapshot_values=snapshot.values,
        platform_name=sys.platform,
    )
    return snapshot, paths


def _prepare_approval_context(workspace_root: Path) -> tuple[LaunchEnvironmentSnapshot, OperatorPaths]:
    """Prepare the TTY-gated approval ceremony and initialize its root."""
    snapshot, paths = _prepare_candidate_context(workspace_root)
    bootstrap_workspace_runtime_root(paths)
    return snapshot, paths


def _resolve_candidate(
    workspace_root: Path,
    store: KeyringApprovalStore,
    *,
    snapshot: LaunchEnvironmentSnapshot,
    operator_paths: OperatorPaths,
) -> LaunchCandidate:
    """Resolve the full launch candidate from an already-captured context.

    Plan 9.96, Task 5 cutover: uses resolve_authorized_operator_paths() —
    the single shared helper composing trusted-root resolution and
    OPTIMUS_CONFIG_ROOT override validation — exclusively. Never the legacy
    resolve_operator_paths(), which bootstraps from inherited
    APPDATA/HOME/XDG_CONFIG_HOME. __main__.py's authorized launch path calls
    the same shared helper, so there is exactly one implementation of this
    security-relevant resolution rather than two independently-maintained
    ones.

    Global Constraint 6: os.environ is read exactly once, into the snapshot.
    Every downstream decision — including the OPTIMUS_CONFIG_ROOT override
    used to resolve operator paths — reads from snapshot.values, never
    os.environ again. A second direct os.environ read here would let the
    approval's digest (bound to the snapshot's OPTIMUS_CONFIG_ROOT) diverge
    from the config root this function actually resolves and reads
    .env.gateway from — the same credential-swap shape as the Task 4 digest
    hole, reintroduced through an ambient re-read.

    .env.gateway's permissions are validated by resolve_launch_candidate()
    itself (validate_config_file_permissions(), POSIX owner/mode bits or real
    Windows DACL enumeration) before it is parsed — that check lives inside
    resolve_launch_candidate rather than here, so every caller gets it
    structurally rather than by remembering to call it.
    """
    workspace_state = resolve_workspace_security_state(workspace_root)

    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_state=workspace_state,
        operator_paths=operator_paths,
        hmac_key=store.hmac_key,
    )
    return candidate


def _display_candidate(candidate: LaunchCandidate) -> None:
    """Display the effective configuration for operator confirmation."""
    print("optimus-trust: effective launch configuration:")
    print(f"  Workspace: {candidate.workspace_identity.canonical_path}")
    print(f"  Snapshot digest: {candidate.security_snapshot_digest[:16]}...")
    print()
    for row in candidate.display_rows:
        print(f"  [{row.tier.value:>15}] {row.name} = {row.display_value}")
        print(f"  {'':>17} decision: {row.decision}")
        print(f"  {'':>17} source: {row.source_class}")
    print()


def _confirm_approval() -> bool:
    try:
        answer = input("optimus-trust: approve this exact launch configuration? [y/N]: ")
    except EOFError:
        answer = ""
    if answer.strip().casefold() in {"y", "yes"}:
        return True
    print("optimus-trust: approval cancelled; no record was written.")
    return False


def _strip_separator(argv: list[str]) -> list[str]:
    """Strip the leading '--' from REMAINDER-captured argv."""
    if argv and argv[0] == "--":
        return argv[1:]
    return argv


def _cmd_approve(workspace_root: Path, *, mode: str, target_argv: list[str]) -> int:
    """Author a durable or one-shot approval."""
    _require_tty()
    target_argv = _strip_separator(target_argv)

    snapshot, paths = _prepare_approval_context(workspace_root)
    store, _ = _resolve_store(workspace_root)
    candidate = _resolve_candidate(workspace_root, store, snapshot=snapshot, operator_paths=paths)

    # Display the effective configuration for operator review.
    _display_candidate(candidate)

    # P9.96-FU-7: the confirmation gate is enforced here; the effective-row display gap
    # for keyring/config/default-sourced settings remains open under this same finding.
    if not _confirm_approval():
        return 1

    # Build the approval record by REUSING the candidate's exact
    # security_literals/secret_fingerprints/monotonic_grants/model_observation.
    # These MUST be reused verbatim (not reconstructed from display_rows) so
    # that build_approval_record()'s digest computation matches
    # candidate.security_snapshot_digest exactly — both call the same shared
    # compute_security_snapshot_digest() with identical inputs.
    hmac_key = store.hmac_key

    record = build_approval_record(
        mode=mode,
        workspace_identity=candidate.workspace_identity,
        security_literals=candidate.security_literals,
        secret_fingerprints=candidate.secret_fingerprints,
        monotonic_grants=candidate.monotonic_grants,
        model_observation=candidate.model_observation,
        hmac_key=hmac_key,
    )

    if mode == "durable":
        store.write_durable(record)
        print(f"optimus-trust: durable approval written (id: {record.approval_id})")
        return 0

    # One-shot: write, spawn with placeholder substitution, delete on failure.
    nonce = secrets.token_bytes(32)
    handle = store.write_one_shot(record, nonce)
    launch_session_id = f"sess_{secrets.token_hex(12)}"

    if not target_argv:
        # No target command — just report success (handle is NOT printed).
        print(f"optimus-trust: one-shot approval written (id: {record.approval_id})")
        return 0

    # Substitute placeholders in target argv (in-memory only, never printed).
    substituted_argv = [
        arg.replace("{approval_id}", handle)
           .replace("{launch_session_id}", launch_session_id)
        for arg in target_argv
    ]

    # Spawn with shell=False. Delete the one-shot record if spawning fails.
    try:
        result = subprocess.run(
            substituted_argv,
            shell=False,
            check=False,
        )
    except OSError as exc:
        # Spawning failed — delete the one-shot record.
        try:
            store.consume_one_shot(handle, candidate.security_snapshot_digest)
        except ApprovalError:
            pass  # Best-effort cleanup.
        print(f"optimus-trust: spawn failed: {exc}", file=sys.stderr)
        return 3

    return result.returncode


def _cmd_inspect(workspace_root: Path) -> int:
    """Display approval metadata (no secrets, no handles). Does not promote."""
    workspace_state = resolve_workspace_security_state(workspace_root)
    store, _ = _resolve_store(workspace_root)

    current = store.read_durable(workspace_state.identity.digest)
    if current is not None:
        if current.migration_provenance is not None:
            print("optimus-trust: approval record state: migrated from v2")
            print(
                "  inherited-trust: pre_migration_assurance_not_upgraded "
                "(compatibility, not a fresh approval ceremony)"
            )
        else:
            print("optimus-trust: approval record state: current")
        print(f"  Approval ID: {current.approval_id}")
        print(f"  Mode: {current.mode}")
        print(f"  Created: {current.created_at.isoformat()}")
        print(f"  Policy: {current.policy_compatibility}")
        print(f"  Snapshot digest: {current.security_snapshot_digest[:16]}...")
        return 0

    legacy = store.read_durable(workspace_state.legacy_v2_digest)
    if legacy is not None:
        print("optimus-trust: approval record state: legacy")
        print("  A reachable v1 durable approval exists; launch promotion is required to use it.")
        print(f"  Approval ID: {legacy.approval_id}")
        print(f"  Mode: {legacy.mode}")
        return 0

    print(
        "optimus-trust: no reachable current approval exists; "
        "an explicit approval ceremony is required."
    )
    return 1


def _confirm_client_mcp_review() -> bool:
    """Require explicit operator confirmation before writing a durable client-MCP record."""
    try:
        answer = input("optimus-trust: write durable client MCP trust for this identity? [y/N]: ")
    except EOFError:
        answer = ""
    if answer.strip().casefold() in {"y", "yes"}:
        return True
    print("optimus-trust: client MCP review cancelled; no record was written.")
    return False


def _select_effect_ceiling(explicit: str | None) -> EffectCeiling:
    if explicit in {"non_mutating", "side_effect_eligible"}:
        return explicit  # type: ignore[return-value]
    try:
        answer = input(
            "optimus-trust: effect ceiling [non_mutating/side_effect_eligible] "
            "(default non_mutating): "
        )
    except EOFError:
        answer = ""
    choice = answer.strip().casefold()
    if choice in {"", "non_mutating", "n", "non-mutating"}:
        return "non_mutating"
    if choice in {"side_effect_eligible", "s", "side-effect-eligible"}:
        return "side_effect_eligible"
    raise CliError(
        "optimus-trust: effect ceiling must be non_mutating or side_effect_eligible",
        exit_code=2,
    )


def _credential_names_from_canonical_target(canonical_target: str) -> tuple[str, ...]:
    """Extract query parameter names (values are fingerprints in canonical URLs)."""
    try:
        query = urlsplit(canonical_target).query
    except ValueError:
        return ()
    if not query:
        return ()
    return tuple(name for name, _value in parse_qsl(query, keep_blank_values=True) if name)


def _client_mcp_credential_names_for_display(
    *,
    canonical_target: str,
    explicit_names: tuple[str, ...],
) -> tuple[str, ...]:
    if explicit_names:
        return explicit_names
    return _credential_names_from_canonical_target(canonical_target)


def _display_client_mcp_review(display: ClientMcpReviewDisplay) -> None:
    for line in format_client_mcp_review_lines(display):
        print(line)
    print()


def _cmd_mcp_review(
    workspace_root: Path,
    *,
    fingerprint: str | None,
    server_name: str | None,
    no_ipc: bool,
    transport: str,
    canonical_target: str | None,
    candidate_id: str | None,
    ipc_address: str | None,
    effect_ceiling: str | None = None,
    credential_names: tuple[str, ...] = (),
    credential_fingerprints: tuple[str, ...] = (),
    received_at: str | None = None,
) -> int:
    """Author a durable client-MCP record bound to a derived identity fingerprint."""
    _require_tty()
    resolved = _resolve_store(workspace_root)
    launch_store = resolved[0] if isinstance(resolved, tuple) else resolved
    workspace_identity = resolve_workspace_identity(workspace_root)
    client_store = ClientMcpDurableStore(keyring_backend=launch_store._keyring, hmac_key=launch_store.hmac_key)

    snapshot: SafeCandidateSnapshot | None = None
    session_id = ""
    provenance = "client_supplied_acp"
    scanner_rule_ids: tuple[str, ...] = ()
    rendered_fingerprint = fingerprint
    identity_transport = transport
    identity_server = server_name
    identity_target = canonical_target
    identity_arguments: tuple[str, ...] = ()
    identity_cred_fps = credential_fingerprints

    if no_ipc:
        print("optimus-trust: manual client MCP review (IPC absent)")
        if not server_name or not canonical_target or not fingerprint:
            raise CliError(
                "optimus-trust: --no-ipc requires --server-name, --canonical-target, and --fingerprint",
                exit_code=2,
            )
        if len(credential_names) != len(credential_fingerprints) and credential_fingerprints:
            raise CliError(
                "optimus-trust: --credential-name and --credential-fingerprint counts must match",
                exit_code=2,
            )
        identity_server = server_name
        identity_target = canonical_target
        identity_transport = transport
        identity_cred_fps = credential_fingerprints
        rendered_fingerprint = fingerprint
    else:
        if not candidate_id or not ipc_address:
            raise CliError(
                "optimus-trust: mcp review requires --candidate-id and --ipc-address, or --no-ipc",
                exit_code=2,
            )
        authkey = derive_ipc_auth_key(launch_store.hmac_key)
        try:
            snapshot = PendingClientMcpCandidateEndpoint.consume_remote_snapshot(
                address=ipc_address,
                authkey=authkey,
                candidate_id=candidate_id,
            )
        except LookupError as exc:
            raise CliError(
                "optimus-trust: pending candidate not found or expired "
                "(use --no-ipc for manual review)",
                exit_code=2,
            ) from exc
        except Exception as exc:
            raise CliError(
                "optimus-trust: IPC unavailable or unreadable "
                "(use --no-ipc for manual review)",
                exit_code=2,
            ) from exc

        identity_transport = snapshot.transport
        identity_server = snapshot.server_name
        identity_target = snapshot.canonical_target
        identity_arguments = snapshot.arguments
        identity_cred_fps = snapshot.credential_name_fingerprints
        rendered_fingerprint = snapshot.rendered_fingerprint
        session_id = snapshot.session_id
        provenance = snapshot.provenance or "client_supplied_acp"
        scanner_rule_ids = snapshot.scanner_rule_ids
        if fingerprint is not None and fingerprint != snapshot.rendered_fingerprint:
            raise CliError("optimus-trust: IDENTITY_MISMATCH", exit_code=2)
        if snapshot.workspace_digest != workspace_identity.digest:
            raise CliError("optimus-trust: workspace digest mismatch", exit_code=2)

    assert identity_server is not None
    assert identity_target is not None
    assert rendered_fingerprint is not None

    identity = ClientMcpSafeIdentity(
        transport=identity_transport,
        server_name=identity_server,
        canonical_target=identity_target,
        arguments=identity_arguments,
        credential_name_fingerprints=identity_cred_fps,
    )
    derived = compute_identity_fingerprint(identity, hmac_key=launch_store.hmac_key)
    if rendered_fingerprint != derived:
        raise CliError("optimus-trust: IDENTITY_MISMATCH", exit_code=2)

    display_names = _client_mcp_credential_names_for_display(
        canonical_target=identity_target,
        explicit_names=credential_names,
    )
    display = ClientMcpReviewDisplay(
        workspace_digest=workspace_identity.digest if snapshot is None else snapshot.workspace_digest,
        session_id=session_id,
        received_at=received_at or "",
        server_name=identity_server,
        transport=identity_transport,
        canonical_target=identity_target,
        credential_field_names=display_names,
        credential_name_fingerprints=identity_cred_fps,
        rendered_fingerprint=rendered_fingerprint,
        provenance=provenance if provenance == "client_supplied_acp" else "client_supplied_acp",
        scanner_rule_ids=scanner_rule_ids,
    )
    _display_client_mcp_review(display)

    selected_ceiling = _select_effect_ceiling(effect_ceiling)
    print(f"optimus-trust: selected effect ceiling: {selected_ceiling}")

    if not _confirm_client_mcp_review():
        return 1

    try:
        write_client_mcp_durable_from_fingerprint(
            store=client_store,
            workspace_digest=display.workspace_digest,
            identity=identity,
            rendered_fingerprint=rendered_fingerprint,
            effect_ceiling=selected_ceiling,
        )
    except ClientMcpTrustError as exc:
        raise CliError(f"optimus-trust: {exc.code}", exit_code=2) from exc
    print(f"optimus-trust: reviewed client MCP server={identity_server}")
    return 0


def _cmd_revoke(workspace_root: Path) -> int:
    """Revoke the durable approval for this workspace."""
    _require_tty()

    store, _ = _resolve_store(workspace_root)
    workspace_identity = resolve_workspace_identity(workspace_root)

    store.revoke_workspace(workspace_identity.digest)
    print("optimus-trust: durable approval revoked.")
    return 0


def _cmd_rotate_key(workspace_root: Path) -> int:
    """Rotate the HMAC integrity key."""
    _require_tty()

    store, _ = _resolve_store(workspace_root)
    store.rotate_hmac_key()
    print("optimus-trust: HMAC key rotated. All existing approvals are invalidated.")
    return 0


def _cmd_setup_credentials(workspace_root: Path) -> int:
    """Interactive credential setup (delegates to existing flow via trusted roots)."""
    _require_tty()

    from optimus.acp.local_gateway_secrets import run_setup_wizard

    roots = resolve_trusted_operator_roots(platform_name=sys.platform)
    return run_setup_wizard(config_root=roots.default_config_root)


def _cmd_run(workspace_root: Path, *, target_argv: list[str], elevated_debug: bool) -> int:
    """Run a command with an existing durable approval.

    For --elevated-debug: creates a diagnostic grant, substitutes
    {approval_id}, {launch_session_id}, {diagnostic_grant_id} in argv.
    """
    target_argv = _strip_separator(target_argv)
    if not target_argv:
        print("optimus-trust run: no target command specified.", file=sys.stderr)
        return 2

    snapshot, paths = _prepare_candidate_context(workspace_root)
    store, _ = _resolve_store(workspace_root)
    candidate = _resolve_candidate(workspace_root, store, snapshot=snapshot, operator_paths=paths)

    try:
        authorized = authorize_launch(
            candidate=candidate,
            store=store,
            launch_session_id=secrets.token_hex(12),
        )
    except LaunchGateError as exc:
        if exc.code == "NO_APPROVAL":
            print(
                "optimus-trust: no reachable current approval exists; "
                "an explicit approval ceremony is required.",
                file=sys.stderr,
            )
        else:
            print(f"optimus-trust: {exc}", file=sys.stderr)
        return 2

    launch_session_id = authorized.launch_session_id

    # Elevated debug: create a diagnostic grant (TTY required).
    diagnostic_grant_id = ""
    if elevated_debug:
        _require_tty()
        from dataclasses import replace
        from datetime import datetime, timedelta, timezone

        from optimus.acp.launch_approvals import DIAGNOSTIC_TTL_SECONDS, DiagnosticGrant, compute_grant_hmac

        diagnostic_grant_id = f"diag_{secrets.token_hex(12)}"
        unsigned_grant = DiagnosticGrant(
            grant_id=diagnostic_grant_id,
            workspace_digest=candidate.workspace_identity.digest,
            approval_id=authorized.approval_id,
            launch_session_id=launch_session_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=DIAGNOSTIC_TTL_SECONDS),
            record_hmac="",
        )
        # Plan 9.96, Task 6 Batch 2: sign the grant with the store's own
        # HMAC key before persisting it, closing the Task 5 stub. Without
        # this, consume_diagnostic_grant's own HMAC verification (added in
        # the same batch) would reject every grant this CLI writes.
        grant = replace(unsigned_grant, record_hmac=compute_grant_hmac(unsigned_grant, hmac_key=store.hmac_key))
        store.write_diagnostic_grant(grant)

    # Substitute placeholders — never print identifiers.
    substituted_argv = [
        arg.replace("{approval_id}", authorized.approval_id)
           .replace("{launch_session_id}", launch_session_id)
           .replace("{diagnostic_grant_id}", diagnostic_grant_id)
        for arg in target_argv
    ]

    try:
        result = subprocess.run(substituted_argv, shell=False, check=False)
    except OSError as exc:
        print(f"optimus-trust run: spawn failed: {exc}", file=sys.stderr)
        return 3

    return result.returncode


_DEFAULT_GATEWAY_BIND_HOST = "127.0.0.1"
_DEFAULT_GATEWAY_BIND_PORT = 8765


def _cmd_run_gateway_default(workspace_root: Path, *, with_local_phoenix: bool = False) -> int:
    """Entry point for `optimus-trust run-gateway` with real trusted roots
    and the real OS keyring (no injectable parameters) — the production
    call path. _cmd_run_gateway itself takes explicit trusted_roots/
    credential_keyring_backend parameters so tests never touch either the
    real filesystem-derived roots or the real OS keychain.
    """
    import keyring as keyring_backend

    return _cmd_run_gateway(
        workspace_root,
        bind_host=_DEFAULT_GATEWAY_BIND_HOST,
        bind_port=_DEFAULT_GATEWAY_BIND_PORT,
        trusted_roots=_resolve_trusted_roots(),
        credential_keyring_backend=keyring_backend,
        with_local_phoenix=with_local_phoenix,
    )


def _cmd_run_gateway(
    workspace_root: Path,
    *,
    bind_host: str,
    bind_port: int,
    trusted_roots: TrustedOperatorRoots,
    credential_keyring_backend: object,
    with_local_phoenix: bool = False,
) -> int:
    """Start the local Gateway with the approval ceremony, reading the
    repository's own .env.gateway as untrusted DATA — never sourced or
    executed.

    Plan 9.96, Task 5 Batch 3 Step 4: earlier checkout-root Gateway launcher scripts
    previously did `source .env.gateway` (bash) or hand-parsed it into the
    invoking shell's own environment (PowerShell) — either way, executing
    or copying repository-controlled file content into the operator's
    shell. This command replaces that: .env.gateway is parsed the same way
    resolve_provider_credentials/resolve_shared_secret parse any other
    .env.gateway (as key=value data, never `source`d), its permissions are
    validated first, the safe snapshot is displayed, and a short-lived
    HMAC-signed GatewayChildManifest is built and passed to the real
    optimus_gateway subprocess via --bind-host/--port/--manifest — never
    through OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT env vars.
    """
    _require_tty()

    config_root = workspace_root.resolve()
    env_gateway_path = config_root / ".env.gateway"
    if not env_gateway_path.is_file():
        print(
            "optimus-trust run-gateway: no .env.gateway found at "
            f"{env_gateway_path}. Copy .env.gateway.example and add your provider key.",
            file=sys.stderr,
        )
        return 2

    try:
        validate_config_file_permissions(env_gateway_path)
    except LaunchGateError as exc:
        print(f"optimus-trust run-gateway: {exc.code}: .env.gateway permissions are too open.", file=sys.stderr)
        return 2

    try:
        provider_credentials = resolve_provider_credentials(
            os.environ,
            config_root=config_root,
            keyring_backend=credential_keyring_backend,
        )
    except ProviderCredentialConfigurationError as exc:
        print(f"optimus-trust run-gateway: {exc.user_message}", file=sys.stderr)
        return 2

    shared_secret = resolve_shared_secret(
        os.environ,
        config_root=config_root,
        keyring_backend=credential_keyring_backend,
    )

    provider_secrets = provider_credentials.secrets
    if provider_secrets is None or not shared_secret:
        print(
            "optimus-trust run-gateway: no compatible local gateway credentials found in "
            f"{env_gateway_path}. Run `optimus-trust setup-credentials` or edit .env.gateway.",
            file=sys.stderr,
        )
        return 2

    # Display the safe (non-secret) snapshot before starting anything.
    print("optimus-trust run-gateway: effective gateway configuration:")
    print("  Gateway credential: OpenRouter (configured)")
    print(
        f"  Base URL: {mask_uri_userinfo(provider_secrets.base_url) if provider_secrets.base_url else '(provider default)'}"
    )
    print(f"  Bind: {bind_host}:{bind_port}")
    print()

    workspace_identity = resolve_workspace_identity(workspace_root)
    hmac_key_source = KeyringApprovalStore(
        keyring_backend=credential_keyring_backend, runtime_root=trusted_roots.approval_runtime_root
    )
    security_snapshot_digest = compute_secret_fingerprint(
        provider_secrets.model_provider_api_key + "\x00" + shared_secret,
        field_name="run_gateway_snapshot",
        hmac_key=hmac_key_source.hmac_key,
    )

    manifest = build_gateway_child_manifest(
        workspace_digest=workspace_identity.digest,
        security_snapshot_digest=security_snapshot_digest,
        provider=provider_secrets.provider,
        base_url=provider_secrets.base_url,
        bind_host=bind_host,
        bind_port=bind_port,
        provider_api_key=provider_secrets.model_provider_api_key,
        shared_secret=shared_secret,
        hmac_key=hmac_key_source.hmac_key,
        policy_version=LAUNCH_POLICY_COMPATIBILITY,
    )
    serialized_manifest = serialize_gateway_child_manifest(manifest)

    child_env: dict[str, str] = {
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER": provider_secrets.provider,
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": shared_secret,
        **provider_secrets.as_gateway_child_env(),
        **project_gateway_tool_child_env(_parse_env_gateway_file(env_gateway_path)),
    }
    for key in ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP"):
        value = os.environ.get(key, "")
        if value:
            child_env[key] = value

    if with_local_phoenix:
        try:
            otlp_endpoint = ensure_local_phoenix(log=lambda msg: print(msg, file=sys.stderr))
        except LocalInfrastructureError as exc:
            print(f"optimus-trust run-gateway: {exc.code}: {exc.user_message}", file=sys.stderr)
            return 2
        child_env["OTEL_EXPORTER_OTLP_ENDPOINT"] = otlp_endpoint

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "optimus_gateway",
            "--bind-host",
            bind_host,
            "--port",
            str(bind_port),
            "--manifest",
            serialized_manifest,
        ],
        env=child_env,
        shell=False,
        check=False,
    )
    return result.returncode
