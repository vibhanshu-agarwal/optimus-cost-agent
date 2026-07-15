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

from optimus.acp.launch_approvals import (
    ApprovalError,
    KeyringApprovalStore,
    build_approval_record,
)
from optimus.acp.launch_gate import (
    LaunchCandidate,
    LaunchGateError,
    resolve_launch_candidate,
)
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.trusted_paths import (
    TrustedPathError,
    resolve_trusted_operator_roots,
    resolve_workspace_identity,
)


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
    subparsers.add_parser("run-gateway", help="Start the local gateway with approval ceremony.")

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
    except CliError as exc:
        print(exc.message, file=sys.stderr)
        return exc.code
    except TrustedPathError as exc:
        print(f"optimus-trust: {exc}", file=sys.stderr)
        return 2
    except ApprovalError as exc:
        print(f"optimus-trust: {exc}", file=sys.stderr)
        return 2
    except LaunchGateError as exc:
        print(f"optimus-trust: {exc}", file=sys.stderr)
        return 2

    print(f"optimus-trust: unknown command '{args.command}'", file=sys.stderr)
    return 2


def _resolve_store(workspace_root: Path) -> tuple[KeyringApprovalStore, Path]:
    """Resolve the approval store from trusted roots."""
    import keyring as keyring_backend

    roots = resolve_trusted_operator_roots(platform_name=sys.platform)
    store = KeyringApprovalStore(
        keyring_backend=keyring_backend,
        runtime_root=roots.approval_runtime_root,
    )
    return store, roots.approval_runtime_root


def _resolve_candidate(workspace_root: Path, store: KeyringApprovalStore) -> LaunchCandidate:
    """Resolve the full launch candidate from the current environment."""
    from optimus.acp.operator_paths import resolve_operator_paths

    snapshot = LaunchEnvironmentSnapshot.capture(os.environ)
    workspace_identity = resolve_workspace_identity(workspace_root)
    paths = resolve_operator_paths(workspace_root=workspace_root, environ=os.environ)

    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=workspace_identity,
        operator_paths=paths,
        hmac_key=store._hmac_key,
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
    print()


def _strip_separator(argv: list[str]) -> list[str]:
    """Strip the leading '--' from REMAINDER-captured argv."""
    if argv and argv[0] == "--":
        return argv[1:]
    return argv


def _cmd_approve(workspace_root: Path, *, mode: str, target_argv: list[str]) -> int:
    """Author a durable or one-shot approval."""
    _require_tty()
    target_argv = _strip_separator(target_argv)

    store, _ = _resolve_store(workspace_root)
    candidate = _resolve_candidate(workspace_root, store)

    # Display the effective configuration for operator review.
    _display_candidate(candidate)

    # Build the approval record by REUSING the candidate's exact
    # security_literals/secret_fingerprints/monotonic_grants/model_observation.
    # These MUST be reused verbatim (not reconstructed from display_rows) so
    # that build_approval_record()'s digest computation matches
    # candidate.security_snapshot_digest exactly — both call the same shared
    # compute_security_snapshot_digest() with identical inputs.
    hmac_key = store._hmac_key

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
    """Display approval metadata (no secrets, no handles)."""
    store, _ = _resolve_store(workspace_root)
    workspace_identity = resolve_workspace_identity(workspace_root)

    record = store.read_durable(workspace_identity.digest)
    if record is None:
        print("optimus-trust: no durable approval found for this workspace.")
        return 1

    print(f"  Approval ID: {record.approval_id}")
    print(f"  Mode: {record.mode}")
    print(f"  Created: {record.created_at.isoformat()}")
    print(f"  Policy: {record.policy_compatibility}")
    print(f"  Snapshot digest: {record.security_snapshot_digest[:16]}...")
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

    store, _ = _resolve_store(workspace_root)
    candidate = _resolve_candidate(workspace_root, store)

    # Verify the durable approval exists and matches.
    ws_digest = candidate.workspace_identity.digest
    record = store.read_durable(ws_digest)
    if record is None:
        print("optimus-trust: no durable approval found for this workspace.", file=sys.stderr)
        return 2
    if record.security_snapshot_digest != candidate.security_snapshot_digest:
        print("optimus-trust: configuration changed since approval. Re-approve.", file=sys.stderr)
        return 2

    launch_session_id = f"sess_{secrets.token_hex(12)}"

    # Elevated debug: create a diagnostic grant (TTY required).
    diagnostic_grant_id = ""
    if elevated_debug:
        _require_tty()
        from datetime import datetime, timedelta, timezone

        from optimus.acp.launch_approvals import DIAGNOSTIC_TTL_SECONDS, DiagnosticGrant

        diagnostic_grant_id = f"diag_{secrets.token_hex(12)}"
        grant = DiagnosticGrant(
            grant_id=diagnostic_grant_id,
            workspace_digest=ws_digest,
            approval_id=record.approval_id,
            launch_session_id=launch_session_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=DIAGNOSTIC_TTL_SECONDS),
            record_hmac="",  # Grant HMAC computed separately in Task 6.
        )
        store.write_diagnostic_grant(grant)

    # Substitute placeholders — never print identifiers.
    substituted_argv = [
        arg.replace("{approval_id}", record.approval_id)
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
