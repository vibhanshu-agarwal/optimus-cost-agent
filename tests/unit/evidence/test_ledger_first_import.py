from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"


def test_ledger_imports_first_in_a_fresh_process() -> None:
    # #563: optimus.evidence.ledger <-> optimus.usage.accounting must not form an import cycle.
    # The child gets this checkout's src first and reports the file it loaded, so another checkout's
    # install cannot pass for this one.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(_SRC), os.environ.get("PYTHONPATH")]))}
    result = subprocess.run(
        [sys.executable, "-c", "import optimus.evidence.ledger as m; print(m.__file__)"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == _SRC / "optimus" / "evidence" / "ledger.py"
