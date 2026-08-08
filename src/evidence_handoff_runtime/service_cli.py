"""CLI for the evidence-handoff Streamable HTTP service.

Credentials are accepted only via files — never as argv string values.
Task 5 bind settings come from --runtime-file only (no unused bind CLI flags).
--admin-password-file is declared so password-on-argv stays forbidden; Task 5
does not open a DB connection, so the file path is rejected if supplied.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-handoff-service")
    parser.add_argument("command", choices=("serve",))
    parser.add_argument("--runtime-file", type=Path, required=True)
    parser.add_argument(
        "--admin-password-file",
        type=Path,
        required=False,
        help=(
            "Password file path only (never pass the password on argv). "
            "Unused until a later task wires store access; supplying it now errors."
        ),
    )
    return parser


def _serve(runtime_file: Path) -> int:
    import uvicorn

    from evidence_handoff_runtime.service import build_asgi_app

    runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
    if "conninfo" in runtime or any(
        "password=" in str(value).lower() for value in runtime.values() if isinstance(value, str)
    ):
        raise SystemExit("runtime_file_must_not_contain_credentials")
    app = build_asgi_app(runtime)
    uvicorn.run(
        app,
        host=str(runtime["bind_host"]),
        port=int(runtime["bind_port"]),
        log_level="warning",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        if args.admin_password_file is not None:
            parser.error(
                "--admin-password-file is reserved for later store wiring; "
                "Task 5 serve does not consume DB credentials"
            )
        return _serve(args.runtime_file)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
