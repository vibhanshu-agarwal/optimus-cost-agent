"""The K3 provisioner's admission binding (Checkpoint B round 89 pass 2, finding 4): run-derived names only, and a
provisioned root that names anything but the admitted resource and this run's role and entry is refused before any
secret access. No keyring, container or database is touched here."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from optimus_security import accounting_config as ac
from tests.support import plan12_capture_provisioner as prov

RUN = "0123456789abcdef"
SECTION = {"host": "127.0.0.1", "port": 56217, "database": "optimus_usage_k3", "user": "optimus_k3"}


def _root(tmp_path: Path, **changes: object) -> Path:
    root = tmp_path / "accounting"
    root.mkdir()
    document = {"schema_version": 1, "host": "127.0.0.1", "port": 56217, "database": "optimus_usage_k3", "user": f"k3_boundary_{RUN}",
                "credential_name": f"k3-boundary-{RUN}", "connect_timeout_seconds": 5, **changes}
    (root / ac.CONFIG_NAME).write_bytes(json.dumps(document).encode("utf-8"))
    return root


def test_the_bound_root_names_the_admitted_resource_and_the_run():
    with pytest.raises(ValueError):
        prov.run_identity("operator-entry")
    assert prov.run_identity(RUN) == (f"k3_boundary_{RUN}", f"k3-boundary-{RUN}")


def test_a_matching_root_is_bound(tmp_path):
    root = _root(tmp_path)

    literal, config = prov.bound_accounting(SECTION, root, RUN)

    assert literal == ac.config_literal(root) and config.user == f"k3_boundary_{RUN}"


@pytest.mark.parametrize(
    "changes",
    [{"database": "another"}, {"port": 5432}, {"host": "db.example"}, {"user": "optimus_k3"}, {"credential_name": "operator-entry"}],
)
def test_a_root_naming_another_target_or_credential_is_refused(tmp_path, changes):
    with pytest.raises(ValueError, match="accounting_config_not_bound"):
        prov.bound_accounting(SECTION, _root(tmp_path, **changes), RUN)


def test_a_root_holding_anything_else_is_refused(tmp_path):
    root = _root(tmp_path)
    (root / "extra").write_bytes(b"")

    with pytest.raises(ValueError, match="accounting_root_not_temporary"):
        prov.bound_accounting(SECTION, root, RUN)
    with pytest.raises(SystemExit):
        prov.temporary_root(root)  # the provisioner never writes into a non-empty root
