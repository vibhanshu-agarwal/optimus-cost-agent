from __future__ import annotations

import subprocess
import sys


def test_ledger_imports_first_in_a_fresh_process() -> None:
    # #563: optimus.evidence.ledger <-> optimus.usage.accounting must not form an import cycle.
    result = subprocess.run(
        [sys.executable, "-c", "import optimus.evidence.ledger"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
