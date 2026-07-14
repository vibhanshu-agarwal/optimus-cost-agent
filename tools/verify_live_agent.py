#!/usr/bin/env python3
"""Operator sign-off command for the Optimus live agent."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from optimus.acp.operator_verify import main

if __name__ == "__main__":
    raise SystemExit(main(repository_root=ROOT))
