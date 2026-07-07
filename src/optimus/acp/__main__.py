from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server
from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.acp.server import StdioByteReader, StdioByteWriter


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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    workspace_root = Path(args.workspace_root)
    if args.check_config:
        try:
            run_preflight(
                os.environ,
                workspace_root=workspace_root,
                strict=args.strict,
                require_timeseries=True,
            )
        except PreflightFailure as exc:
            print(exc.user_message, file=sys.stderr)
            return exc.exit_code
        print("Optimus ACP agent configuration OK.", file=sys.stderr)
        return 0
    try:
        server = build_configured_server(environ=os.environ, workspace_root=workspace_root, model=args.model)
    except StartupConfigurationError as exc:
        print(exc.user_message, file=sys.stderr)
        return exc.exit_code
    asyncio.run(server.serve(StdioByteReader(sys.stdin.buffer), StdioByteWriter(sys.stdout.buffer)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
