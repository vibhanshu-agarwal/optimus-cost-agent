#!/usr/bin/env python3
"""Operator sign-off command for the Optimus live agent.

Requires a one-time durable approval for the verify workspace
(`reports/.verify-live-agent-workspace`) first — see
src/optimus/acp/operator_verify.py's module docstring, or run:

    optimus-trust --workspace-root reports/.verify-live-agent-workspace approve --mode durable
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from optimus.acp.operator_verify import main

if __name__ == "__main__":
    raise SystemExit(main(repository_root=ROOT))
