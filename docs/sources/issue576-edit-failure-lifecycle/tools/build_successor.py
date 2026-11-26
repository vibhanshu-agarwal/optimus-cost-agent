"""Build LLD v2.49 from the archived native baseline and this bundle's sources.

The #361 bundle's builder (``issue361-search-independent-metadata/tools/build_successors.py``), narrowed to the LLD:
it reuses the filed renderer of ``capability-evidence-correction/tools/build_corrections.py`` for the Markdown pages,
page stamp, fonts and control-character removal, and writes a manifest of the same shape, so the filed
``validate_corrections.py`` checks the edition unchanged. The predecessor page map is read from the filed #361
build manifest rather than copied.

Usage: build_successor.py REPO_ROOT OUT_DIR
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("build_corrections", HERE.parents[1] / "capability-evidence-correction" / "tools" / "build_corrections.py")
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)

LABEL = "ISSUE #576 SUCCESSOR"
FOOTER = "#576 EDIT failure lifecycle | 2026-11-26"
PDF_TITLE = "Optimus - Low-Level Design v2.49 - issue 576 EDIT failure lifecycle"
PDF_SUBJECT = "Issue #576: section 4B.5 EDIT failure lifecycle at main 31c6de5; all carried text keeps its original source pins."
REPORT_PIN = "31c6de5821b994a9498800fdfed2a2ca6b0a13f6"  # pragma: allowlist secret
KEY = "lld"
PREFIX, BASELINE_VERSION, PREDECESSOR_VERSION, NEW_VERSION, TITLE = "Optimus-Cost-Agent-LLD", "2.41", "2.48", "2.49", "Low-Level Design"
APPENDED = ["lld-13-context-integration.md", "lld-14-capability-status.md"]
PREDECESSOR_SHA = "620ee455216572e71c28ae7923c12ccc7673659089bae01a0199e807cd44644f"  # pragma: allowlist secret
PREDECESSOR_MANIFEST = HERE.parents[1] / "issue361-search-independent-metadata" / "build-manifest.json"


def predecessor_page_map() -> tuple[dict[int, tuple[int, int]], tuple[int, int]]:
    """Baseline page -> v2.48 page range, and v2.48's appended-chapter range, from the filed #361 manifest."""
    doc = json.loads(PREDECESSOR_MANIFEST.read_text(encoding="utf-8"))["documents"][KEY]
    if doc["sha256"] != PREDECESSOR_SHA:
        raise AssertionError("the #361 manifest does not describe the v2.48 predecessor")
    pages = {m["baseline_page"]: tuple(m["successor_pages"]) for m in doc["mapping"] if m["baseline_page"] is not None}
    sections = [m["successor_pages"] for m in doc["mapping"] if m["baseline_page"] is None]
    return pages, (sections[0][0], sections[-1][1])


def build(repo: Path, bundle: Path, out: Path) -> dict:
    basefile = repo / "docs" / "archive" / f"{PREFIX}-v{BASELINE_VERSION}.pdf"
    if bc.sha256(basefile) != bc.BASELINE_SHA[KEY]:
        raise AssertionError(f"baseline hash mismatch for {basefile}")
    predecessor = repo / "docs" / f"{PREFIX}-v{PREDECESSOR_VERSION}.pdf"
    if not predecessor.exists():
        predecessor = repo / "docs" / "archive" / f"{PREFIX}-v{PREDECESSOR_VERSION}.pdf"
    if bc.sha256(predecessor) != PREDECESSOR_SHA:
        raise AssertionError(f"predecessor hash mismatch for {predecessor}")
    edits = json.loads((bundle / "sources" / "page-updates.json").read_text(encoding="utf-8"))[KEY]
    reader = PdfReader(basefile)
    writer = PdfWriter()
    mapping = []
    cover = (bundle / "sources" / f"{KEY}-cover.md").read_text(encoding="utf-8")
    for p in bc.markdown_pdf(cover, bc.LETTER).pages:
        writer.add_page(p)
    mapping.append({"baseline_page": 1, "action": "replace-cover", "successor_pages": [1, len(writer.pages)]})
    for i, page in enumerate(reader.pages, start=1):
        if i == 1:
            continue
        start = len(writer.pages) + 1
        if str(i) in edits:
            for replacement_page in bc.markdown_pdf(edits[str(i)], bc.LETTER).pages:
                writer.add_page(replacement_page)
            action = "replace-body"
        else:
            writer.add_page(page)
            bc.remove_controls(writer.pages[-1])
            action = "carry-body"
        mapping.append({"baseline_page": i, "action": action, "successor_pages": [start, len(writer.pages)]})
    for source in APPENDED:
        start = len(writer.pages) + 1
        for p in bc.markdown_pdf((bundle / "sources" / source).read_text(encoding="utf-8"), bc.LETTER).pages:
            writer.add_page(p)
        mapping.append({"baseline_page": None, "action": "new-section", "source": source, "successor_pages": [start, len(writer.pages)]})
    total = len(writer.pages)
    for n, p in enumerate(writer.pages, start=1):
        bc.stamp(p, TITLE, NEW_VERSION, n, total, bc.LETTER)
    writer.add_metadata({
        "/Title": PDF_TITLE,
        "/Author": "Claude - successor document; Codex - CLI review",
        "/Subject": PDF_SUBJECT,
        "/CreationDate": "D:20261126000000+0530",
    })
    target = out / f"{PREFIX}-v{NEW_VERSION}.pdf"
    with target.open("wb") as f:
        writer.write(f)
    base_to_pred, (a, b) = predecessor_page_map()
    pred_map = {}
    for base_page, (pa, pb) in base_to_pred.items():
        new_range = next(m["successor_pages"] for m in mapping if m["baseline_page"] == base_page)
        for pp in range(pa, pb + 1):
            pred_map[str(pp)] = new_range
    sections = [m["successor_pages"] for m in mapping if m["baseline_page"] is None]
    pred_map[f"{a}-{b}"] = [sections[0][0], sections[-1][1]]
    return {
        "file": target.name, "pages": total, "sha256": bc.sha256(target), "predecessor": predecessor.name,
        "predecessor_sha256": PREDECESSOR_SHA, "baseline": basefile.name, "baseline_sha256": bc.BASELINE_SHA[KEY],
        "mapping": mapping, "predecessor_page_map": pred_map,
        "cover_source_sha256": bc.sha256(bundle / "sources" / f"{KEY}-cover.md"),
        "appended_sources": {s: hashlib.sha256((bundle / "sources" / s).read_bytes()).hexdigest() for s in APPENDED},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("out")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bundle = HERE.parent
    bc.LABEL, bc.FOOTER = LABEL, FOOTER  # read by bc.stamp
    bc.register_fonts()
    manifest = {
        "inspected_source": f"Issue #576: LLD section 4B.5 checked against main {REPORT_PIN}; carried claims retain their own pins",
        "built": "2026-11-26", "label": LABEL, "footer": FOOTER,
        "page_updates_sha256": bc.sha256(bundle / "sources" / "page-updates.json"),
        "edits_sha256": bc.sha256(bundle / "sources" / "edits.json"),
        "documents": {KEY: build(repo, bundle, out)},
    }
    (out / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="")
    print(json.dumps({k: {"pages": v["pages"], "sha256": v["sha256"]} for k, v in manifest["documents"].items()}, indent=2))


if __name__ == "__main__":
    main()
