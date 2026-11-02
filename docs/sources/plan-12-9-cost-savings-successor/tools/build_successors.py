"""Build HLD v2.24, LLD v2.47 and Test Strategy v1.10 from the archived native baselines and this bundle's sources.

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
LABEL = "LOCAL FILING - NOT ACTIVATED"
FOOTER = "Cost-savings report | 2026-11-02"
PDF_TITLE = {
    "hld": "Optimus - Architecture (HLD) v2.24 - Cost-savings report (local filing - not activated)",
    "lld": "Optimus - Low-Level Design v2.47 - Cost-savings report (local filing - not activated)",
    "test": "Optimus - Test Strategy v1.10 - Cost-savings report (local filing - not activated)",
}
PDF_SUBJECT = {
    "hld": "Plan 12.9 cost-savings report and necessary durable-capture/Postgres accounting corrections at main a88fde86a2ddf382a9bb39a6e2c1a74a1db20498; prior pins and controlling unrefreshed Plan 12.2 amendment preserved. Qualified evidence; ADR-034 Proposed. Local filing; publication to main requires separate operator approval.",
    "lld": "Usage-report route, ACP savings commands, durable accounting ownership, Auto attribution and independent reference/snapshot contracts at main a88fde86a2ddf382a9bb39a6e2c1a74a1db20498; earlier contracts and evidence retain their pins. ADR-034 Proposed. Local filing; publication to main requires separate operator approval.",
    "test": "Real Postgres capture/report tier and Plan 12.9 evidence at main a88fde86a2ddf382a9bb39a6e2c1a74a1db20498; failed Windows gate and separately attributed successful Linux PR/main CI preserved. Local filing; publication to main requires separate operator approval. Open Gateway attachment gap owned by #465.",
}
REPORT_PIN = "a88fde86a2ddf382a9bb39a6e2c1a74a1db20498"  # pragma: allowlist secret

# key: (file prefix, baseline version, predecessor version, new version, title, [appended sources], pagesize)
DOCS = {
    "hld": ("Optimus-Cost-Agent-Architecture", "2.18", "2.23", "2.24", "Architecture (HLD)", ["hld-14-context-engine.md", "hld-15-capability-status.md"], bc.LETTER),
    "lld": ("Optimus-Cost-Agent-LLD", "2.41", "2.46", "2.47", "Low-Level Design", ["lld-13-context-integration.md", "lld-14-capability-status.md"], bc.LETTER),
    "test": ("Optimus-Cost-Agent-Test-Strategy", "1.7", "1.9", "1.10", "Test Strategy", ["test-15-context-evidence.md", "test-16-capability-status.md"], bc.LETTER),
}
PREDECESSOR_SHA = {
    "hld": "3abcc0c047795d91350b8660c6e26943d39fea13bf99568704b91838cfbb2acb",  # pragma: allowlist secret
    "lld": "4a2f9cb64c69d6a8284b72905cb25abf6f979a18d9ccdcad37b98b790e2712a6",  # pragma: allowlist secret
    "test": "21ab8cacd90fd56bdce7841c48efaf2642cc45555dc5fa43f40786e12fbb60fd",  # pragma: allowlist secret
}
# Baseline page -> predecessor page range, and the appended chapters' range. From the build manifests of the filed
# drivers (p397-escalation-successor and capability-evidence-correction). Here they reproduce their editions' page counts
# and extracted text, not their bytes: the Windows Arial fonts have since changed version; see validation-record.md.
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
        "/Author": "Codex - successor wording; Claude - build and verification",
        "/Subject": PDF_SUBJECT[key],
        "/CreationDate": "D:20261102000000+0530",
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
        "inspected_source": f"{REPORT_PIN} for the cost-savings report and its accounting source; earlier pins as each carried statement states",
        "built": "2026-11-02", "label": LABEL, "footer": FOOTER,
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
