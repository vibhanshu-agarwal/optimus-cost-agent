"""Raw-canary scanning over an operator evidence root (content-free)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Patterns that must never appear in promoted evidence, logs, or MCP captures.
_CANARY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE),
)

_TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".log",
    ".txt",
    ".md",
    ".csv",
    ".yml",
    ".yaml",
    ".sql",
    ".err",
    ".out",
}


def scan_raw_canaries(evidence_root: Path) -> dict[str, Any]:
    """Scan evidence root files for raw secret/canary material.

    Returns a content-free summary: hit counts and relative paths only.
    """
    hits: list[dict[str, str]] = []
    scanned_files = 0
    if not evidence_root.is_dir():
        return {"scanned_files": 0, "hit_count": 0, "hits": [], "clean": True}

    for path in sorted(evidence_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES and path.name not in {
            "manifest.json",
            "audit.jsonl",
            "service.log",
        }:
            continue
        scanned_files += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in _CANARY_PATTERNS:
            if pattern.search(text):
                rel = str(path.relative_to(evidence_root)).replace("\\", "/")
                hits.append({"path": rel, "pattern": pattern.pattern})
                break
    return {
        "scanned_files": scanned_files,
        "hit_count": len(hits),
        "hits": hits,
        "clean": len(hits) == 0,
    }
