"""Plan 12.8 K3 provisioner (test tooling, run outside pytest by the released live run). It admits the released container
first, then generates a run-specific password in RAM, creates a run-specific login role inside that container (SQL on
psql's stdin, never in argv), stores the password in the Gateway's own keyring namespace under the run's entry, and
writes the non-secret accounting configuration into a new temporary root. Every name it creates or deletes derives from
the run ID alone, so it can never set or delete another entry or role. It prints only non-secret references.

    python -m tests.support.plan12_capture_provisioner provision --k3-config CONFIG --run-id RUN_ID --root ACCOUNTING_ROOT
    python -m tests.support.plan12_capture_provisioner cleanup --k3-config CONFIG --run-id RUN_ID
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from optimus_security import accounting_config as ac

RUN_ID = re.compile(r"[0-9a-f]{16}")


def run_identity(run_id: str) -> tuple[str, str]:
    """The run's login role and keyring entry: the only names this provisioner ever creates or deletes."""
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("run id must be 16 lowercase hex characters")
    return f"k3_boundary_{run_id}", f"k3-boundary-{run_id}"


def bound_accounting(section: dict[str, Any], root: Path, run_id: str) -> tuple[str, ac.AccountingConfig]:
    """The provisioned root verified against the admitted resource and the run, before any secret access (the boundary
    fixture and, again, the Gateway child call it): a temporary root holding only the configuration, which names the
    admitted endpoint and database, the run's role and the run's keyring entry. Returns its literal and configuration."""
    role, entry = run_identity(run_id)
    resolved = root.resolve()
    if not resolved.is_relative_to(Path(tempfile.gettempdir()).resolve()) or sorted(p.name for p in resolved.iterdir()) != [ac.CONFIG_NAME]:
        raise ValueError("accounting_root_not_temporary")
    literal, config, refusal = ac.read(resolved)
    if literal is None or refusal is not None or config != ac.AccountingConfig(section["host"], section["port"], section["database"], role, entry, 5):
        raise ValueError("accounting_config_not_bound")
    return literal, config


def temporary_root(root: Path) -> Path:
    """A new or empty directory under the system temporary directory: never the operator's per-user config root."""
    resolved = root.resolve()
    if not resolved.is_relative_to(Path(tempfile.gettempdir()).resolve()) or (resolved.exists() and any(resolved.iterdir())):
        raise SystemExit("the accounting root must be a new or empty directory under the system temporary directory")
    return resolved


def _admit(k3_config: str) -> dict[str, Any]:
    from tools.plan12_memory import probes

    section: dict[str, Any] = json.loads(Path(k3_config).read_text(encoding="utf-8"))
    probes.admit_postgres_resource(section, probes.docker_inspect)  # before any secret or role operation
    return section


def _psql(section: dict[str, Any], sql: str) -> None:
    subprocess.run(
        ["docker", "exec", "-i", section["container"], "psql", "-q", "-v", "ON_ERROR_STOP=1", "-U", section["user"], "-d", section["database"]],
        input=sql, check=True, capture_output=True, text=True, timeout=60,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plan12_capture_provisioner")
    commands = parser.add_subparsers(dest="command", required=True)
    provision = commands.add_parser("provision")
    provision.add_argument("--k3-config", required=True)
    provision.add_argument("--run-id", required=True)
    provision.add_argument("--root", required=True)
    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("--k3-config", required=True)
    cleanup.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    role, entry = run_identity(args.run_id)
    section = _admit(args.k3_config)

    import keyring

    if args.command == "provision":
        root = temporary_root(Path(args.root))
        password = secrets.token_hex(24)  # RAM only: psql's stdin and the native keyring, nowhere else
        _psql(section, f"CREATE ROLE {role} LOGIN PASSWORD '{password}' IN ROLE {section['user']};\n")
        keyring.set_password(ac.KEYRING_SERVICE, entry, password)
        del password
        root.mkdir(parents=True, exist_ok=True)
        document = {"schema_version": 1, "host": section["host"], "port": section["port"], "database": section["database"],
                    "user": role, "credential_name": entry, "connect_timeout_seconds": 5}
        (root / ac.CONFIG_NAME).write_bytes(json.dumps(document).encode("utf-8"))
        print(json.dumps({"accounting_root": str(root), "config_literal": ac.config_literal(root), "role": role,
                          "keyring_service": ac.KEYRING_SERVICE, "credential_name": entry}))
    else:
        try:
            keyring.delete_password(ac.KEYRING_SERVICE, entry)
        except keyring.errors.PasswordDeleteError:
            pass  # already gone: cleanup is idempotent
        _psql(section, f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN "
                       f"EXECUTE 'DROP OWNED BY {role}'; EXECUTE 'DROP ROLE {role}'; END IF; END $$;\n")
        print(json.dumps({"deleted": {"keyring_service": ac.KEYRING_SERVICE, "credential_name": entry, "role": role}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
