"""Evidence-only support for tools/verify_evidence_handoff_live.py.

May not emulate MCP, PostgreSQL, or an agent. Records and validates operator-
supplied native-client evidence only.
"""

from __future__ import annotations

from .canary import scan_raw_canaries
from .errors import VerificationError
from .verify import inspect_evidence_root, verify_evidence_root

__all__ = [
    "VerificationError",
    "inspect_evidence_root",
    "scan_raw_canaries",
    "verify_evidence_root",
]
