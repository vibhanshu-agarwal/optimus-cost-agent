"""The committed exception-site report verifies against the committed tree (#334's gate, run on the real inputs).

The other tests in test_exception_site_disposition.py run the verifier on synthetic modules. Main went red unseen after
#694, because no test ran the verifier on reports/hardening-exception-site-disposition.json. It launches ruff
(helper_launches.json: _inventory, _ruff)."""

from __future__ import annotations

from pathlib import Path

from tools import verify_exception_site_disposition as checker

_REPORT = Path(__file__).resolve().parents[3] / "reports" / "hardening-exception-site-disposition.json"


def test_the_committed_report_verifies_against_the_tree(capsys):
    assert checker.main(["--report", str(_REPORT)]) == 0, capsys.readouterr()
