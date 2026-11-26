"""The #576 LLD v2.49 filing binds its PDF, its sources and its predecessor to canonical repository bytes."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from tools.doc_paths import doc_path

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "docs/sources/issue576-edit-failure-lifecycle"

# Recorded by the build in validation-record.md; the PDF is the filed tool's output from exactly these sources.
FILED = {
    "Optimus-Cost-Agent-LLD-v2.49.pdf": "3a8c05bd37e0be1dd787725fa49ad5aa09a692968a66b66548e49a6d3fac3a24",  # pragma: allowlist secret - public artifact digest
    "Optimus-Cost-Agent-LLD-v2.48.pdf": "620ee455216572e71c28ae7923c12ccc7673659089bae01a0199e807cd44644f",  # pragma: allowlist secret - public artifact digest
}
SOURCES = {
    "page-updates.json": "5bbc77b75e05fb02ab8ed46e1286bdbb84ab00fbf110f6fccc808d436fa3f665",  # pragma: allowlist secret - public artifact digest
    "lld-cover.md": "9c126a82473af214f2ec91094eda994a15c22a838bce32330a54c3261faf8f4f",  # pragma: allowlist secret - public artifact digest
    "edits.json": "f5216866f5621b6a516d813394cd70085abebe5cdc68ab9431ffc28313ad19e1",  # pragma: allowlist secret - public artifact digest
}


def test_filed_pdfs_match_their_recorded_digests() -> None:
    for name, expected in FILED.items():
        assert hashlib.sha256(doc_path(name).read_bytes()).hexdigest() == expected, name


def test_sources_match_the_digests_the_pdf_was_built_from() -> None:
    for name, expected in SOURCES.items():
        raw = (BUNDLE / "sources" / name).read_bytes()
        assert b"\r\n" not in raw, f"source must match the repository LF contract: {name}"
        assert hashlib.sha256(raw).hexdigest() == expected, name


def test_sources_derive_from_the_issue361_predecessor_and_the_exact_edits(tmp_path: Path) -> None:
    # The filed derive tool fails unless every edit matches once and the result equals the filed sources byte for byte.
    subprocess.run(
        [sys.executable, "-X", "utf8", "-I", str(BUNDLE / "tools/derive_sources.py"), str(ROOT), str(tmp_path)],
        check=True,
        capture_output=True,
    )
