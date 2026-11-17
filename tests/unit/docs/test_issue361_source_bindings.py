"""The #361 filed digests bind canonical repository bytes on every platform."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tools.doc_paths import doc_path

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "docs/sources/issue361-search-independent-metadata"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_source_digest(path: Path) -> str:
    raw = path.read_bytes()
    assert b"\r\n" not in raw, f"source must match the repository LF contract: {path.name}"
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("key", ["hld", "lld", "test"])
def test_filed_pdf_and_source_digests_match_repository_bytes(key: str) -> None:
    manifest = json.loads((BUNDLE / "build-manifest.json").read_text(encoding="utf-8"))
    doc = manifest["documents"][key]
    assert _canonical_source_digest(BUNDLE / "sources/page-updates.json") == manifest["page_updates_sha256"]
    assert _canonical_source_digest(BUNDLE / "sources/successor-edits.md") == manifest["successor_edits_sha256"]
    assert _canonical_source_digest(BUNDLE / "sources" / f"{key}-cover.md") == doc["cover_source_sha256"]
    for name, expected in doc["appended_sources"].items():
        assert _canonical_source_digest(BUNDLE / "sources" / name) == expected
    assert _digest(doc_path(doc["file"])) == doc["sha256"]
    assert _digest(doc_path(doc["predecessor"])) == doc["predecessor_sha256"]


def test_adopted_plan_keeps_its_exact_approved_git_bytes() -> None:
    plan = doc_path("2026-11-17-plan-11-33-search-independent-metadata-implementation.md")
    blob = subprocess.check_output(["git", "show", f":{plan.relative_to(ROOT).as_posix()}"], cwd=ROOT)
    approved_sha256 = "8b8585d5ad47fb96cb38e9000ce205e85734225ce559f64ae7294870bf084933"  # pragma: allowlist secret - public approval checksum
    assert hashlib.sha256(blob).hexdigest() == approved_sha256
