"""Operator CLI for evidence handoff lifecycle management."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidence_handoff_runtime.backends import registered_backend_ids
from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext
from evidence_handoff_runtime.lifecycle import LifecycleManager
from optimus_security.sanitization import PathAliasRule

_IMPLEMENTED_BACKENDS = tuple(sorted(registered_backend_ids()))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-handoff-lifecycle")
    parser.add_argument("command", choices=("start", "stop", "status", "health"))
    parser.add_argument("--enabled", action="store_true", default=False)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--lock-path", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--quarantine-root", type=Path, required=True)
    parser.add_argument("--forbidden-root", type=Path, required=True)
    parser.add_argument("--admin-user", default="handoff")
    parser.add_argument(
        "--admin-password-file",
        type=Path,
        required=True,
        help="Path to a file containing the store admin password (password never accepted via argv).",
    )
    parser.add_argument(
        "--backend-id",
        default="docker",
        choices=_IMPLEMENTED_BACKENDS,
        help="Stopped-lifecycle store backend selection (implemented: docker only).",
    )
    parser.add_argument("--postgres-port", type=int, default=55432)
    parser.add_argument("--container-name", default="evidence-handoff-postgres")
    parser.add_argument("--volume-name", default="evidence-handoff-postgres-data")
    parser.add_argument("--image", default="postgres:16-alpine")
    return parser


def _read_admin_password(path: Path) -> str:
    try:
        password = path.read_text(encoding="utf-8").strip("\r\n")
    except OSError as exc:
        raise SystemExit(f"evidence-handoff-lifecycle: error: cannot read admin password file: {exc.errno}") from None
    if not password:
        raise SystemExit("evidence-handoff-lifecycle: error: admin password file is empty")
    return password


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    admin_password = _read_admin_password(args.admin_password_file)
    config = FeatureConfig.from_mapping(
        {
            "enabled": "true" if args.enabled else "false",
            "backend_id": args.backend_id,
            "bind_host": "127.0.0.1",
            "postgres_port": str(args.postgres_port),
            "container_name": args.container_name,
            "volume_name": args.volume_name,
            "image": args.image,
        }
    )
    bootstrap = LifecycleBootstrapContext(
        service_secrets=(admin_password,),
        identity_values=("lifecycle-cli",),
        path_aliases=(PathAliasRule(source_root=str(args.capture_root), alias="<temp>"),),
        temporary_capture_root=args.capture_root,
        staging_root=args.staging_root,
        quarantine_root=args.quarantine_root,
        forbidden_persistence_roots=(args.forbidden_root,),
        allowed_origins=("http://127.0.0.1:8765",),
        enrollment_principal_ids=("operator",),
        capabilities=("review-ruling",),
        lock_path=args.lock_path,
        control_root=args.control_root,
        store_admin_user=args.admin_user,
        store_admin_password=admin_password,
    )
    manager = LifecycleManager(config, bootstrap)
    if args.command == "start":
        status = manager.start()
    elif args.command == "stop":
        status = manager.stop()
    elif args.command == "status":
        status = manager.status()
    else:
        health = manager.health()
        print(
            json.dumps(
                {
                    "ready": health.ready,
                    "postgres_version": health.postgres_version,
                    "ledger_instance_id": health.ledger_instance_id,
                },
                sort_keys=True,
            )
        )
        return 0 if health.ready else 1
    print(
        json.dumps(
            {
                "availability": None if status.availability is None else str(status.availability),
                "running": status.running,
                "active_route": status.active_route,
                "summary_code": status.summary_code,
                "ledger_instance_id": status.ledger_instance_id,
                "backend_id": status.backend_id,
            },
            sort_keys=True,
        )
    )
    return 0 if status.summary_code in {"store_ready", "feature_disabled_operator_relay", "store_stopped"} else 1


if __name__ == "__main__":
    sys.exit(main())
