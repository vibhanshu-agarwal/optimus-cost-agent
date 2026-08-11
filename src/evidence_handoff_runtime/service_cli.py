"""CLI for the evidence-handoff Streamable HTTP service.

Credentials are accepted only via files — never as argv string values.
--auth-bundle-file carries signing key / store conninfo for Task 6; the child
process loads it into memory and deletes the file immediately.
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
            "Unused when --auth-bundle-file supplies store conninfo."
        ),
    )
    parser.add_argument(
        "--auth-bundle-file",
        type=Path,
        required=False,
        help="Ephemeral auth bundle path (signing key + store conninfo). Deleted after read.",
    )
    return parser


def _serve(runtime_file: Path, auth_bundle_file: Path | None) -> int:
    import uvicorn

    from evidence_handoff_runtime.service import build_asgi_app

    runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
    if "conninfo" in runtime or any(
        "password=" in str(value).lower() for value in runtime.values() if isinstance(value, str)
    ):
        raise SystemExit("runtime_file_must_not_contain_credentials")
    if "signing_key" in runtime or "signing_key_b64" in runtime:
        raise SystemExit("runtime_file_must_not_contain_credentials")

    auth_bundle = None
    if auth_bundle_file is not None:
        auth_bundle = json.loads(auth_bundle_file.read_text(encoding="utf-8"))
        try:
            auth_bundle_file.unlink(missing_ok=True)
        except OSError:
            pass

    app = build_asgi_app(runtime, auth_bundle=auth_bundle)
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
        if args.admin_password_file is not None and args.auth_bundle_file is None:
            parser.error(
                "--admin-password-file requires store wiring; prefer --auth-bundle-file for Task 6"
            )
        return _serve(args.runtime_file, args.auth_bundle_file)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
