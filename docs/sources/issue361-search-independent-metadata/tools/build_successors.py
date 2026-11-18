"""Build HLD v2.25, LLD v2.48 and Test Strategy v1.11 from the archived native baselines and this bundle's sources.

Reuses the filed builder of the 2026-10-15 correction (``capability-evidence-correction/tools/build_corrections.py``)
for its Markdown renderer, page stamp, fonts and control-character removal, as the v2.23/v2.46 bundle did. This bundle
supplies only the editions, the cover sources, the label, footer and metadata, and the predecessor page maps. The
manifest keeps the predecessors' shape, so the filed ``validate_corrections.py`` checks these editions unchanged.

Usage: build_successors.py REPO_ROOT OUT_DIR
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

# Page header and footer of the filed editions (Codex's build strings in successor-edits.md).
LABEL = "ISSUE #361 SUCCESSOR"
FOOTER = "#361 metadata independence | 2026-11-17"
PDF_TITLE = {
    "hld": "Optimus - Architecture (HLD) v2.25 - issue 361 metadata independence",
    "lld": "Optimus - Low-Level Design v2.48 - issue 361 metadata independence",
    "test": "Optimus - Test Strategy v1.11 - issue 361 metadata independence",
}
PDF_SUBJECT = {key: "Issue #361 metadata configuration independence; unit/loopback evidence only, live release UNRUN; all carried evidence keeps its original source pins." for key in ("hld", "lld", "test")}
REPORT_PIN = "43e5e5b415140a17005045d3d21c6de2ed8595b3"  # pragma: allowlist secret

# key: (file prefix, baseline version, predecessor version, new version, title, [appended sources], pagesize)
DOCS = {
    "hld": ("Optimus-Cost-Agent-Architecture", "2.18", "2.24", "2.25", "Architecture (HLD)", ['hld-14-context-engine.md', 'hld-15-capability-status.md'], bc.LETTER),
    "lld": ("Optimus-Cost-Agent-LLD", "2.41", "2.47", "2.48", "Low-Level Design", ['lld-13-context-integration.md', 'lld-14-capability-status.md'], bc.LETTER),
    "test": ("Optimus-Cost-Agent-Test-Strategy", "1.7", "1.10", "1.11", "Test Strategy", ['test-15-context-evidence.md', 'test-16-capability-status.md'], bc.LETTER),
}
PREDECESSOR_SHA = {
    "hld": "cfd627f2cc5c3c026072940590f535a8c65c282c26fd19f0ed14893e6f3852c5",  # pragma: allowlist secret
    "lld": "e8e42bb59dcdcfe17f297ad968854950e8bca3babfaad440221ef1a649ba0d51",  # pragma: allowlist secret
    "test": "e9346917c705099631d3b171fa70da130ad17619e496802675701ec8b0bab95a",  # pragma: allowlist secret
}
# Baseline page -> predecessor page range, and the appended chapters' range. From the build manifests of the filed
# immediate predecessor driver. All three current editions were reproduced byte-for-byte before deriving these maps;
# see validation-record.md. Frozen predecessor inputs remain unchanged.
PREDECESSOR_MAP = json.loads((HERE / "predecessor-page-map.json").read_text(encoding="utf-8"))


def build_doc(key: str, repo: Path, bundle: Path, out: Path, updates: dict, manifest: dict) -> None:
    prefix, baseline_version, predecessor_version, new_version, title, appended, pagesize = DOCS[key]
    basefile = repo / "docs" / "archive" / f"{prefix}-v{baseline_version}.pdf"
    if bc.sha256(basefile) != bc.BASELINE_SHA[key]:
        raise AssertionError(f"baseline hash mismatch for {basefile}")
    predecessor = repo / "docs" / f"{prefix}-v{predecessor_version}.pdf"
    if not predecessor.exists():
        predecessor = repo / "docs" / "archive" / f"{prefix}-v{predecessor_version}.pdf"
    if bc.sha256(predecessor) != PREDECESSOR_SHA[key]:
        raise AssertionError(f"predecessor hash mismatch for {predecessor}")
    reader = PdfReader(basefile)
    writer = PdfWriter()
    mapping = []
    edits = updates[key]
    cover = (bundle / "sources" / f"{key}-cover.md").read_text(encoding="utf-8")
    for p in bc.markdown_pdf(cover, pagesize).pages:
        writer.add_page(p)
    mapping.append({"baseline_page": 1, "action": "replace-cover", "successor_pages": [1, len(writer.pages)]})
    for i, page in enumerate(reader.pages, start=1):
        if i == 1:
            continue
        start = len(writer.pages) + 1
        if str(i) in edits:
            for replacement_page in bc.markdown_pdf(edits[str(i)], pagesize).pages:
                writer.add_page(replacement_page)
            action = "replace-body"
        else:
            writer.add_page(page)
            bc.remove_controls(writer.pages[-1])
            action = "carry-body"
        mapping.append({"baseline_page": i, "action": action, "successor_pages": [start, len(writer.pages)]})
    for source in appended:
        start = len(writer.pages) + 1
        for p in bc.markdown_pdf((bundle / "sources" / source).read_text(encoding="utf-8"), pagesize).pages:
            writer.add_page(p)
        mapping.append({"baseline_page": None, "action": "new-section", "source": source, "successor_pages": [start, len(writer.pages)]})
    total = len(writer.pages)
    for n, p in enumerate(writer.pages, start=1):
        bc.stamp(p, title, new_version, n, total, pagesize)
    writer.add_metadata({
        "/Title": PDF_TITLE[key],
        "/Author": "Codex - implementation and successor documents; Claude - read-only review",
        "/Subject": PDF_SUBJECT[key],
        "/CreationDate": "D:20261117000000+0530",
    })
    target = out / f"{prefix}-v{new_version}.pdf"
    with target.open("wb") as f:
        writer.write(f)
    pred_map = {}
    for base_page, (a, b) in PREDECESSOR_MAP[key]["pages"].items():
        new_range = next(m["successor_pages"] for m in mapping if m["baseline_page"] == int(base_page))
        for pp in range(a, b + 1):
            pred_map[str(pp)] = new_range
    a, b = PREDECESSOR_MAP[key]["appended"]
    sections = [m["successor_pages"] for m in mapping if m["baseline_page"] is None]
    pred_map[f"{a}-{b}"] = [sections[0][0], sections[-1][1]]
    manifest["documents"][key] = {
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
    bc.LABEL, bc.FOOTER = LABEL, FOOTER  # read by bc.stamp
    bc.register_fonts()
    updates = json.loads((bundle / "sources" / "page-updates.json").read_text(encoding="utf-8"))
    manifest = {
        "inspected_source": f"Issue #361 implementation descended from {REPORT_PIN}; exact production/source/test identities are recorded in the validation record and issue; carried claims retain their own pins",
        "built": "2026-11-17", "label": LABEL, "footer": FOOTER,
        "page_updates_sha256": bc.sha256(bundle / "sources" / "page-updates.json"),
        "successor_edits_sha256": bc.sha256(bundle / "sources" / "successor-edits.md"),
        "documents": {},
    }
    for key in DOCS:
        build_doc(key, repo, bundle, out, updates, manifest)
    (out / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="")
    print(json.dumps({k: {"pages": v["pages"], "sha256": v["sha256"]} for k, v in manifest["documents"].items()}, indent=2))


if __name__ == "__main__":
    main()
