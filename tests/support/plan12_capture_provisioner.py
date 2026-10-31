"""Plan 12.8 K3 provisioner (test tooling, run outside pytest by the released live run): places the disposable ledger's
credential in the Gateway's own keyring namespace and writes the non-secret accounting configuration, so the pytest
process that drives the host never holds the password. Each command prints only non-secret references.

    python -m tests.support.plan12_capture_provisioner keyring-set --k3-config CONFIG --password-file FILE --name NAME
    python -m tests.support.plan12_capture_provisioner accounting --k3-config CONFIG --name NAME --root ACCOUNTING_ROOT
    python -m tests.support.plan12_capture_provisioner keyring-delete --name NAME
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from optimus_security import accounting_config as ac


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plan12_capture_provisioner")
    commands = parser.add_subparsers(dest="command", required=True)
    keyring_set = commands.add_parser("keyring-set")
    keyring_set.add_argument("--k3-config", required=True)
    keyring_set.add_argument("--password-file", required=True)
    keyring_set.add_argument("--name", required=True)
    accounting = commands.add_parser("accounting")
    accounting.add_argument("--k3-config", required=True)
    accounting.add_argument("--name", required=True)
    accounting.add_argument("--root", required=True)
    keyring_delete = commands.add_parser("keyring-delete")
    keyring_delete.add_argument("--name", required=True)
    args = parser.parse_args(argv)

    import keyring

    if args.command == "keyring-set":
        password = Path(args.password_file).read_text(encoding="utf-8").strip()
        keyring.set_password(ac.KEYRING_SERVICE, args.name, password)
        print(json.dumps({"keyring_service": ac.KEYRING_SERVICE, "name": args.name}))
    elif args.command == "accounting":
        section = json.loads(Path(args.k3_config).read_text(encoding="utf-8"))
        root = Path(args.root)
        root.mkdir(parents=True, exist_ok=True)
        document = {"schema_version": 1, "host": section["host"], "port": section["port"], "database": section["database"],
                    "user": section["user"], "credential_name": args.name, "connect_timeout_seconds": 5}
        (root / ac.CONFIG_NAME).write_bytes(json.dumps(document).encode("utf-8"))
        print(json.dumps({"accounting_root": str(root), "config_literal": ac.config_literal(root)}))
    else:
        keyring.delete_password(ac.KEYRING_SERVICE, args.name)
        print(json.dumps({"deleted": args.name}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
