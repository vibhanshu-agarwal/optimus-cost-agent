from __future__ import annotations

from pathlib import Path

# The live-smoke launch helpers that lived here were retired with that harness (R-4, #237 6323911791).


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]
