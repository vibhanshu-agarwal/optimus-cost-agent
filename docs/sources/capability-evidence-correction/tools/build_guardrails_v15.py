"""Build Guardrails v1.5: the v1.4 edition with only its cover page replaced.

Same mechanism as the 2026-10-15 correction builder (build_corrections.py, imported from this directory):
native bodies carried from the v1.3 baseline in docs/archive, the v1.4 replaced bodies rebuilt from the
sealed Plan 12.2 page-updates.json, the appended section 14 rebuilt from 14-context-guardrails.md, the
candidate label on every page and the correction footer. The cover text is read from the correction
bundle (sources/guardrails-v15-cover.md). Writes build-manifest.json in the validator's format.

Usage: build_guardrails_v15.py REPO_ROOT OUT_DIR
Never run it inside a sealed packet.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_corrections as bc  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

PREFIX = "Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy"
TITLE = "Guardrails and Workflow"
BASELINE_VERSION, PREDECESSOR_VERSION, NEW_VERSION = "1.3", "1.4", "1.5"
BASELINE_SHA = "94f8f829d60fb9945237227b16e82cb523659e4d67c8488909035fe9bdb27957"  # pragma: allowlist secret
PREDECESSOR_SHA = "981d6b6d846ed2c6bbb9d676ccc90be658a39964071786142ec7e222b5755c1c"  # pragma: allowlist secret
APPENDED = ["14-context-guardrails.md"]
COVER_SOURCE = "guardrails-v15-cover.md"


def body(text: str) -> str:
    """Same normalisation as validate_corrections.body: strip running controls, join without whitespace."""
    import re

    lines = []
    for s in text.splitlines():
        s = s.strip()
        if not s or s.startswith("Optimus-Cost-Agent - ") or s.startswith("Optimus - ") or s.startswith(bc.FOOTER) or s.startswith("Plan 12 | "):
            continue
        if re.fullmatch(r"(Page \d+ of \d+|v\d+\.\d+|\d+ / \d+)", s):
            continue
        lines.append(s)
    return re.sub(r"\s+", "", "\n".join(lines))


def main() -> None:
    repo = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bundle = repo / "docs" / "sources" / "capability-evidence-correction"
    p122 = repo / "docs" / "sources" / "plan-12-2-context-engine-closure" / "sources"
    bc.register_fonts()
    pagesize = bc.LETTER

    basefile = repo / "docs" / "archive" / f"{PREFIX}-v{BASELINE_VERSION}.pdf"
    assert bc.sha256(basefile) == BASELINE_SHA, "baseline (v1.3) hash mismatch"
    predecessor = repo / "docs" / f"{PREFIX}-v{PREDECESSOR_VERSION}.pdf"
    if not predecessor.exists():
        predecessor = repo / "docs" / "archive" / predecessor.name
    assert bc.sha256(predecessor) == PREDECESSOR_SHA, "predecessor (v1.4) hash mismatch"

    updates = json.loads((p122 / "page-updates.json").read_text(encoding="utf-8"))["guardrails"]
    cover_md = (bundle / "sources" / COVER_SOURCE).read_text(encoding="utf-8")

    reader = PdfReader(basefile)
    writer = PdfWriter()
    mapping = []
    for p in bc.markdown_pdf(cover_md, pagesize).pages:
        writer.add_page(p)
    mapping.append({"baseline_page": 1, "action": "replace-cover", "successor_pages": [1, len(writer.pages)]})
    cover_pages = len(writer.pages)
    for i, page in enumerate(reader.pages, start=1):
        if i == 1:
            continue
        start = len(writer.pages) + 1
        if str(i) in updates:
            for rp in bc.markdown_pdf(updates[str(i)], pagesize).pages:
                writer.add_page(rp)
            action = "replace-body"
        else:
            writer.add_page(page)
            bc.remove_controls(writer.pages[-1])
            action = "carry-body"
        mapping.append({"baseline_page": i, "action": action, "successor_pages": [start, len(writer.pages)]})
    for source in APPENDED:
        start = len(writer.pages) + 1
        text = (p122 / source).read_text(encoding="utf-8")
        for p in bc.markdown_pdf(text, pagesize).pages:
            writer.add_page(p)
        mapping.append({"baseline_page": None, "action": "new-section", "source": source, "successor_pages": [start, len(writer.pages)]})
    total = len(writer.pages)
    for n, p in enumerate(writer.pages, start=1):
        bc.stamp(p, TITLE, NEW_VERSION, n, total, pagesize)
    writer.add_metadata({
        "/Title": f"Optimus {TITLE} v{NEW_VERSION} - cover alignment with the capability and evidence correction (local filing candidate)",
        "/Author": "Claude - cover author; v1.4 body by Codex as architect/reviewer",
        "/Subject": "Cover-only successor of v1.4 of 2026-10-15; body unchanged; publication and activation separate",
        "/CreationDate": "D:20261015000000+0530",
    })
    target = out / f"{PREFIX}-v{NEW_VERSION}.pdf"
    with target.open("wb") as f:
        writer.write(f)

    # Predecessor (v1.4) page map, established by text equality of every non-cover page.
    new = PdfReader(target)
    pred = PdfReader(predecessor)
    assert len(new.pages) == len(pred.pages), f"page count differs from v1.4: {len(new.pages)} vs {len(pred.pages)}"
    equal = []
    for n in range(cover_pages + 1, total + 1):
        nb = body(new.pages[n - 1].extract_text() or "")
        pb = body(pred.pages[n - 1].extract_text() or "")
        equal.append(nb == pb)
        if nb != pb:
            print(f"BODY DIFFERS from v1.4 at page {n}: {len(nb)} vs {len(pb)} chars")
    pred_map = {"1": [1, cover_pages]}
    for n in range(cover_pages + 1, total + 1):
        pred_map[str(n)] = [n, n]
    manifest = {
        "inspected_source": bc.PIN,
        "built": "2026-10-15",
        "label": bc.LABEL,
        "footer": bc.FOOTER,
        "page_updates_sha256": bc.sha256(p122 / "page-updates.json"),
        "cover_source_sha256": bc.sha256(bundle / "sources" / COVER_SOURCE),
        "documents": {
            "guardrails": {
                "file": target.name, "pages": total, "sha256": bc.sha256(target), "predecessor": predecessor.name,
                "predecessor_sha256": PREDECESSOR_SHA, "baseline": basefile.name, "baseline_sha256": BASELINE_SHA,
                "mapping": mapping, "predecessor_page_map": pred_map,
                "body_pages_equal_to_v1_4": {"pages": [cover_pages + 1, total], "all_equal": all(equal), "compared": len(equal)},
                "appended_sources": {s: hashlib.sha256((p122 / s).read_bytes()).hexdigest() for s in APPENDED},
            }
        },
    }
    (out / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"file": target.name, "pages": total, "cover_pages": cover_pages, "sha256": manifest["documents"]["guardrails"]["sha256"], "body_pages_equal_to_v1_4": all(equal), "mapping": mapping}, indent=1))


if __name__ == "__main__":
    main()
