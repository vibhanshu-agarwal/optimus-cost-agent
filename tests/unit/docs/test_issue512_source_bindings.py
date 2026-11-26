"""The #512 HLD v2.26 and LLD v2.50 filing binds its PDFs, its sources and its predecessors to canonical repository bytes."""
from __future__ import annotations

import hashlib
import runpy
import sys
from pathlib import Path

import pytest

from tools.doc_paths import doc_path

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "docs/sources/issue512-answer-settlement"

# Recorded by the build in validation-record.md; each PDF is the filed tool's output from exactly these sources.
FILED = {
    "Optimus-Cost-Agent-Architecture-v2.26.pdf": "cb75f9d46613d91dc1fc6501bd651d99779ae2881307f77b44215ea1a5bcd9a6",  # pragma: allowlist secret - public artifact digest
    "Optimus-Cost-Agent-LLD-v2.50.pdf": "260ec305a2e7218085f91a42985731ffa7c5280a19bd3cef7a7f07ed0bfa5c75",  # pragma: allowlist secret - public artifact digest
    "Optimus-Cost-Agent-Architecture-v2.25.pdf": "30f3992275ebf223de1f2c5217f8fff171795ba42765ccbdda655604d98638a6",  # pragma: allowlist secret - public artifact digest
    "Optimus-Cost-Agent-LLD-v2.49.pdf": "3a8c05bd37e0be1dd787725fa49ad5aa09a692968a66b66548e49a6d3fac3a24",  # pragma: allowlist secret - public artifact digest
}
SOURCES = {
    "edits.json": "72c3cece07b45ad90300c9473c9b78dbe99b31a921265fd677981e302e3a7948",  # pragma: allowlist secret - public artifact digest
    "page-updates.json": "0b7c409e55c63d6a1a5a9e182a98b2e74c3d1479e18695d902edd8e992e53d7d",  # pragma: allowlist secret - public artifact digest
    "hld-cover.md": "47f7a66baa068bbd1e56d0dfeeefcdf4e1f08264935a0950727b32795fb59034",  # pragma: allowlist secret - public artifact digest
    "lld-cover.md": "870a41d206df30ad4f25fb65158162fd91bf045e0bb5624d89f9c990f7566f8d",  # pragma: allowlist secret - public artifact digest
}


def test_filed_pdfs_match_their_recorded_digests() -> None:
    for name, expected in FILED.items():
        assert hashlib.sha256(doc_path(name).read_bytes()).hexdigest() == expected, name


def test_sources_match_the_digests_the_pdfs_were_built_from() -> None:
    for name, expected in SOURCES.items():
        raw = (BUNDLE / "sources" / name).read_bytes()
        assert b"\r\n" not in raw, f"source must match the repository LF contract: {name}"
        assert hashlib.sha256(raw).hexdigest() == expected, name


def test_sources_derive_from_the_predecessors_and_the_exact_edits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The filed derive tool raises unless every edit matches once and the result equals the filed sources byte for byte.
    # It runs in-process: it only reads and writes files, so it needs no child process.
    tool = BUNDLE / "tools/derive_sources.py"
    monkeypatch.setattr(sys, "argv", [str(tool), str(ROOT), str(tmp_path)])
    runpy.run_path(str(tool), run_name="__main__")
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "hld-14-context-engine.md",
        "hld-15-capability-status.md",
        "lld-13-context-integration.md",
        "lld-14-capability-status.md",
        "page-updates.json",
    ]
