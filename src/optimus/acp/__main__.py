from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server
from optimus.acp.debug_trace import configure_debug_trace, log_provenance_once, resolve_debug_log_path
from optimus.acp.local_gateway_secrets import run_setup_wizard
from optimus.acp.local_infra import (
    apply_local_defaults,
    ensure_local_gateway,
    ensure_local_redis,
    strip_local_provider_keys,
)
from optimus.acp.operator_paths import OperatorPathConfigurationError, resolve_operator_paths
from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.acp.server import StdioByteReader, StdioByteWriter, StdioNdjsonLineReader, StdioNdjsonLineWriter


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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    workspace_root = Path(args.workspace_root).resolve()
    try:
        paths = resolve_operator_paths(workspace_root=workspace_root, environ=os.environ)
    except OperatorPathConfigurationError as exc:
        print(exc.user_message, file=sys.stderr)
        return exc.exit_code

    if args.setup:
        return run_setup_wizard(config_root=paths.config_root)

    debug_log_path = _apply_debug_trace_args(
        args,
        workspace_root=paths.workspace_root,
        default_log_path=paths.debug_log_path,
    )
    if debug_log_path is not None:
        _print_log(f"ACP debug trace: {debug_log_path}")
    # `environ` may legitimately contain a real vendor key (e.g. ANTHROPIC_API_KEY in the
    # operator's own shell, or resolved from .env.gateway/keyring) — ensure_local_gateway needs
    # that to construct the spawned gateway's child env. It must NEVER be the same object passed
    # to build_configured_server/run_preflight, both of which reach
    # OptimusGatewaySettings.from_env(), which rejects any LOCAL_PROVIDER_KEY_NAMES entry with
    # ProviderKeyViolation. agent_environ (built just below each use) is that separate, sanitized
    # view. See the anthropic-collision finding in Source Anchors / Confirmed Design Decisions.
    environ = apply_local_defaults(os.environ, config_root=paths.config_root)

    if args.check_config:
        if not args.no_auto_start:
            ensure_local_redis(environ["OPTIMUS_REDIS_URL"], log=_print_log)
        agent_environ = strip_local_provider_keys(environ)
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
        ensure_local_redis(environ["OPTIMUS_REDIS_URL"], log=_print_log)
        gateway_process = ensure_local_gateway(
            environ=environ,
            config_root=paths.config_root,
            runtime_root=paths.runtime_root,
            log=_print_log,
        )

    agent_environ = strip_local_provider_keys(environ)

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
