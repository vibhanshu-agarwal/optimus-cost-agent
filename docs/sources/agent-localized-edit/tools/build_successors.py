"""Build HLD v2.21 and LLD v2.44 from the archived native baselines and this bundle's sources.

Reuses the filed builder of the 2026-10-15 correction (``capability-evidence-correction/tools/build_corrections.py``)
for its Markdown renderer, page stamp, fonts and control-character removal. This bundle supplies only the
editions, the cover sources, the label, footer and metadata, and the v2.20/v2.43 page map. The manifest keeps
the predecessor's shape, so that bundle's ``validate_corrections.py`` checks these editions unchanged.

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
LABEL = "LOCAL FILING - NOT ACTIVATED"
FOOTER = "Agent-mode localized EDIT | 2026-10-24"
EDIT_PIN = "d13fd34bde86a656188f6f7b5b3b6f6703ff9dac"  # pragma: allowlist secret

# key: (file prefix, baseline version, predecessor version, new version, title, [appended sources], pagesize)
DOCS = {
    "hld": ("Optimus-Cost-Agent-Architecture", "2.18", "2.20", "2.21", "Architecture (HLD)", ["hld-14-context-engine.md", "hld-15-capability-status.md"], bc.LETTER),
    "lld": ("Optimus-Cost-Agent-LLD", "2.41", "2.43", "2.44", "Low-Level Design", ["lld-13-context-integration.md", "lld-14-capability-status.md"], bc.LETTER),
}
PREDECESSOR_SHA = {
    "hld": "52c35442a0d9027dc4b18a693284c45406cf02913001a59f2df364c77a2e176a",  # pragma: allowlist secret
    "lld": "3fb89935201eb5947eff666a97431653d264ee482b8a5a8a6a4d229d4c8b7c27",  # pragma: allowlist secret
}
# Baseline page -> v2.20/v2.43 page range; None is the appended chapters (capability-evidence-correction/validation-record.md).
PREDECESSOR_MAP = {
    "hld": {i: (i, i) for i in range(1, 9)} | {9: (9, 10)} | {i: (i + 1, i + 1) for i in range(10, 14)} | {None: (15, 20)},
    "lld": {1: (1, 1), 2: (2, 3)} | {i: (i + 1, i + 1) for i in range(3, 41)} | {None: (42, 48)},
}


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
        "/Title": f"Optimus {title} v{new_version} - Agent-mode localized EDIT ({LABEL.lower()})",
        "/Author": "Codex - successor wording; Claude - build and verification",
        "/Subject": f"Agent-mode localized EDIT (#407, PR #411) and execution-path corrections at {EDIT_PIN[:7]}; carried statements at 91fd64a",
        "/CreationDate": "D:20261024000000+0530",
    })
    target = out / f"{prefix}-v{new_version}.pdf"
    with target.open("wb") as f:
        writer.write(f)
    pred_map = {}
    for base_page, (a, b) in PREDECESSOR_MAP[key].items():
        if base_page is None:
            continue
        new_range = next(m["successor_pages"] for m in mapping if m["baseline_page"] == base_page)
        for pp in range(a, b + 1):
            pred_map[str(pp)] = new_range
    a, b = PREDECESSOR_MAP[key][None]
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
        "inspected_source": f"{EDIT_PIN} for the EDIT and execution-path statements; {bc.PIN} for carried statements",
        "built": "2026-10-24", "label": LABEL, "footer": FOOTER,
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
