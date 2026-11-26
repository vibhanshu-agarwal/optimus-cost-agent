"""Build HLD v2.26 and LLD v2.50 from the archived native baselines and this bundle's sources.

The #576 bundle's builder (``issue576-edit-failure-lifecycle/tools/build_successor.py``), widened to both documents as
the #361 bundle's was. It reuses the filed renderer of ``capability-evidence-correction/tools/build_corrections.py``
and writes a manifest of the same shape, so the filed ``validate_corrections.py`` checks both editions unchanged.

Predecessor page maps: HLD v2.25's comes from the filed #361 build manifest. #576 filed no manifest, so LLD v2.49's
comes from rebuilding it with #576's own filed builder, which must reproduce the filed v2.49 byte for byte.

Usage: build_successor.py REPO_ROOT OUT_DIR
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter

HERE = Path(__file__).resolve().parent
SOURCES = HERE.parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bc = _load("build_corrections", SOURCES / "capability-evidence-correction" / "tools" / "build_corrections.py")

LABEL = "ISSUE #512 SUCCESSOR"
FOOTER = "#512 Agent-mode answer settlement | 2026-11-27"
REPORT_PIN = "72d2349bba987df419ac69a23694ff1766dee12f"  # pragma: allowlist secret
PDF_TITLE = {
    "hld": "Optimus - Architecture (HLD) v2.26 - issue 512 Agent-mode answer settlement",
    "lld": "Optimus - Low-Level Design v2.50 - issue 512 Agent-mode answer settlement",
}
PDF_SUBJECT = {
    "hld": "Issue #512: section 14.8 at main 72d2349; all carried text keeps its original source pins.",
    "lld": "Issue #512: sections 4B.1, 13.11.1 and 13.11.3 at main 72d2349; all carried text keeps its original source pins.",
}
# key: (file prefix, baseline version, predecessor version, new version, title, [appended sources])
DOCS = {
    "hld": ("Optimus-Cost-Agent-Architecture", "2.18", "2.25", "2.26", "Architecture (HLD)", ["hld-14-context-engine.md", "hld-15-capability-status.md"]),
    "lld": ("Optimus-Cost-Agent-LLD", "2.41", "2.49", "2.50", "Low-Level Design", ["lld-13-context-integration.md", "lld-14-capability-status.md"]),
}
PREDECESSOR_SHA = {
    "hld": "30f3992275ebf223de1f2c5217f8fff171795ba42765ccbdda655604d98638a6",  # pragma: allowlist secret
    "lld": "3a8c05bd37e0be1dd787725fa49ad5aa09a692968a66b66548e49a6d3fac3a24",  # pragma: allowlist secret
}


def _page_map(mapping: list[dict]) -> tuple[dict[int, tuple[int, int]], tuple[int, int]]:
    pages = {m["baseline_page"]: tuple(m["successor_pages"]) for m in mapping if m["baseline_page"] is not None}
    sections = [m["successor_pages"] for m in mapping if m["baseline_page"] is None]
    return pages, (sections[0][0], sections[-1][1])


def predecessor_page_map(key: str, repo: Path) -> tuple[dict[int, tuple[int, int]], tuple[int, int]]:
    """Baseline page -> predecessor page range, and the predecessor's appended-chapter range."""
    if key == "hld":
        doc = json.loads((SOURCES / "issue361-search-independent-metadata" / "build-manifest.json").read_text(encoding="utf-8"))["documents"][key]
    else:
        bundle = SOURCES / "issue576-edit-failure-lifecycle"
        m576 = _load("build_successor_576", bundle / "tools" / "build_successor.py")
        m576.bc.LABEL, m576.bc.FOOTER = m576.LABEL, m576.FOOTER
        m576.bc.register_fonts()
        with tempfile.TemporaryDirectory() as scratch:
            doc = m576.build(repo, bundle, Path(scratch))
    if doc["sha256"] != PREDECESSOR_SHA[key]:
        raise AssertionError(f"the predecessor page map does not describe the filed {key} predecessor")
    return _page_map(doc["mapping"])


def build(key: str, repo: Path, bundle: Path, out: Path, updates: dict) -> dict:
    prefix, baseline_version, predecessor_version, new_version, title, appended = DOCS[key]
    basefile = repo / "docs" / "archive" / f"{prefix}-v{baseline_version}.pdf"
    if bc.sha256(basefile) != bc.BASELINE_SHA[key]:
        raise AssertionError(f"baseline hash mismatch for {basefile}")
    predecessor = repo / "docs" / f"{prefix}-v{predecessor_version}.pdf"
    if not predecessor.exists():
        predecessor = repo / "docs" / "archive" / f"{prefix}-v{predecessor_version}.pdf"
    if bc.sha256(predecessor) != PREDECESSOR_SHA[key]:
        raise AssertionError(f"predecessor hash mismatch for {predecessor}")
    base_to_pred, (a, b) = predecessor_page_map(key, repo)
    bc.LABEL, bc.FOOTER = LABEL, FOOTER  # read by bc.stamp
    bc.register_fonts()
    edits = updates[key]
    reader = PdfReader(basefile)
    writer = PdfWriter()
    mapping = []
    cover = (bundle / "sources" / f"{key}-cover.md").read_text(encoding="utf-8")
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
    for source in appended:
        start = len(writer.pages) + 1
        for p in bc.markdown_pdf((bundle / "sources" / source).read_text(encoding="utf-8"), bc.LETTER).pages:
            writer.add_page(p)
        mapping.append({"baseline_page": None, "action": "new-section", "source": source, "successor_pages": [start, len(writer.pages)]})
    total = len(writer.pages)
    for n, p in enumerate(writer.pages, start=1):
        bc.stamp(p, title, new_version, n, total, bc.LETTER)
    writer.add_metadata({
        "/Title": PDF_TITLE[key],
        "/Author": "Claude - successor document; Codex - CLI authorship of the edits and review",
        "/Subject": PDF_SUBJECT[key],
        "/CreationDate": "D:20261127000000+0530",
    })
    target = out / f"{prefix}-v{new_version}.pdf"
    with target.open("wb") as f:
        writer.write(f)
    pred_map = {}
    for base_page, (pa, pb) in base_to_pred.items():
        new_range = next(m["successor_pages"] for m in mapping if m["baseline_page"] == base_page)
        for pp in range(pa, pb + 1):
            pred_map[str(pp)] = new_range
    sections = [m["successor_pages"] for m in mapping if m["baseline_page"] is None]
    pred_map[f"{a}-{b}"] = [sections[0][0], sections[-1][1]]
    return {
        "file": target.name, "pages": total, "sha256": bc.sha256(target), "predecessor": predecessor.name,
        "predecessor_sha256": PREDECESSOR_SHA[key], "baseline": basefile.name, "baseline_sha256": bc.BASELINE_SHA[key],
        "mapping": mapping, "predecessor_page_map": pred_map,
        "cover_source_sha256": bc.sha256(bundle / "sources" / f"{key}-cover.md"),
        "appended_sources": {s: hashlib.sha256((bundle / "sources" / s).read_bytes()).hexdigest() for s in appended},
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
    updates = json.loads((bundle / "sources" / "page-updates.json").read_text(encoding="utf-8"))
    documents = {key: build(key, repo, bundle, out, updates) for key in DOCS}
    manifest = {
        "inspected_source": f"Issue #512: HLD section 14.8 and LLD sections 4B.1, 13.11.1 and 13.11.3 checked against main {REPORT_PIN}; carried claims retain their own pins",
        "built": "2026-11-27", "label": LABEL, "footer": FOOTER,
        "page_updates_sha256": bc.sha256(bundle / "sources" / "page-updates.json"),
        "edits_sha256": bc.sha256(bundle / "sources" / "edits.json"),
        "documents": documents,
    }
    (out / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="")
    print(json.dumps({k: {"pages": v["pages"], "sha256": v["sha256"]} for k, v in manifest["documents"].items()}, indent=2))


if __name__ == "__main__":
    main()
