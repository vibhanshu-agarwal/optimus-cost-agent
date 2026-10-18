"""Render the compact validation record (Markdown) from the build manifest, validation JSON and render log.

Usage: write_validation_record.py REPO_ROOT BUILD_DIR SHEETS_DIR OUT_MD [CHECKS_MD]
CHECKS_MD, when given, is appended verbatim as the repository-checks section.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
build = Path(sys.argv[2]).resolve()
sheets = Path(sys.argv[3]).resolve()
out = Path(sys.argv[4]).resolve()
checks_md = Path(sys.argv[5]).read_text(encoding="utf-8") if len(sys.argv) > 5 else ""

manifest = json.loads((build / "build-manifest.json").read_text(encoding="utf-8"))
validation = json.loads((build / "document-validation.json").read_text(encoding="utf-8"))
render = json.loads((sheets / "render-log.json").read_text(encoding="utf-8"))
vres = {r["document"]: r for r in validation["results"]}

ORDER = ["hld", "lld", "roadmap", "test"]
NAMES = {"hld": "Architecture (HLD) v2.20", "lld": "LLD v2.43", "roadmap": "Architecture Roadmap v11", "test": "Test Strategy v1.9"}


def blob(path: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", f"origin/main:{path}"], capture_output=True, text=True)
    return r.stdout.strip() or "-"


lines = []
lines.append("# Validation record: capability and evidence correction (2026-10-15)\n")
lines.append(f"Inspected source `{manifest['inspected_source']}`. Label on every successor page: `{manifest['label']}`; footer: `{manifest['footer']}`. Assembly scope: {validation['scope']}. Overall assembly status: **{validation['status']}**.\n")
lines.append("## Successor editions\n")
lines.append("| Document | File | Pages | SHA-256 |\n|---|---|---|---|")
for k in ORDER:
    d = manifest["documents"][k]
    lines.append(f"| {NAMES[k]} | `{d['file']}` | {d['pages']} | `{d['sha256']}` |")
lines.append("")
lines.append("## Predecessors and baselines (preserved byte for byte)\n")
lines.append("| Document | Predecessor file | Pages | SHA-256 (filesystem) | Git blob at origin/main | Native-page baseline |\n|---|---|---|---|---|---|")
for k in ORDER:
    d = manifest["documents"][k]
    pred_pages = vres[k]["predecessor_pages"]
    base = f"`{d['baseline']}` ({d['baseline_sha256'][:12]}...)" if d.get("baseline") else "none (rendered from Markdown)"
    lines.append(f"| {NAMES[k]} | `{d['predecessor']}` | {pred_pages} | `{d['predecessor_sha256']}` | `{blob('docs/' + d['predecessor'])}` | {base} |")
lines.append("")
lines.append("## Page map: predecessor pages to successor pages\n")
lines.append("Each predecessor page position appears once. `carry` means the native baseline page was carried and its body text checked equal to the baseline; `replace` means a replaced Markdown body; `new` means an appended section.\n")
for k in ORDER:
    d = manifest["documents"][k]
    lines.append(f"**{NAMES[k]}** (predecessor `{d['predecessor']}`)\n")
    if k == "roadmap":
        lines.append(f"- Predecessor pages 1-2 -> successor pages 1-{d['pages']} (new document rendered from `sources/roadmap-v11.md`).\n")
        continue
    # baseline-indexed mapping gives the action; predecessor map gives pred page -> successor range
    action_by_base = {m["baseline_page"]: m["action"] for m in d["mapping"] if m["baseline_page"] is not None}
    rows = []
    for pred_key, rng in d["predecessor_page_map"].items():
        if "-" in pred_key:
            rows.append((int(pred_key.split("-")[0]), pred_key, rng, "new"))
    # map predecessor single pages back to the baseline page to find the action
    # PREDECESSOR_MAP in the builder is baseline -> predecessor range; invert using successor ranges
    base_for_succ = {}
    for m in d["mapping"]:
        if m["baseline_page"] is not None:
            a, b = m["successor_pages"]
            for s in range(a, b + 1):
                base_for_succ[s] = m["baseline_page"]
    for pred_key, rng in d["predecessor_page_map"].items():
        if "-" not in pred_key:
            bp = base_for_succ[rng[0]]
            act = action_by_base[bp]
            rows.append((int(pred_key), pred_key, rng, {"carry-body": "carry", "replace-body": "replace", "replace-cover": "replace (cover)"}[act]))
    rows.sort(key=lambda r: r[0])
    compact = ", ".join(f"{pk}->{rng[0]}" + (f"-{rng[1]}" if rng[1] != rng[0] else "") + f" ({act})" for _, pk, rng, act in rows)
    lines.append(f"- {compact}\n")
    new_secs = [m for m in d["mapping"] if m["baseline_page"] is None]
    for m in new_secs:
        lines.append(f"- Appended `{m['source']}` -> successor pages {m['successor_pages'][0]}-{m['successor_pages'][1]}.")
    lines.append("")
lines.append("## Assembly checks\n")
lines.append("| Document | Carried native pages | Checks | Status |\n|---|---|---|---|")
for k in ORDER:
    r = vres[k]
    checks = "; ".join(f"{name}: {'ok' if ok else 'FAIL'}" for name, ok in r["checks"].items())
    lines.append(f"| {NAMES[k]} | {r['carried_native_pages']} | {checks} | {r['status']} |")
lines.append("")
if validation["failures"]:
    lines.append("Failures: " + "; ".join(validation["failures"]) + "\n")
lines.append("## Rendered review\n")
lines.append(f"Renderer: {render['renderer']}. Every page of every successor was rendered and tiled into contact sheets, and every sheet was inspected by the author (Claude) for legible text, table integrity, code and diagram boundaries, headers and footers, pagination and clipped or missing material. This is an author review of all pages, not an independent external review.\n")
lines.append("| Document | Pages rendered | pdftoppm exit | Sheets |\n|---|---|---|---|")
for stem, info in render["documents"].items():
    lines.append(f"| `{stem}` | {info['pages_rendered']} | {info['pdftoppm_exit']} | {len(info['sheets'])} |")
lines.append("")
if checks_md:
    lines.append(checks_md.rstrip() + "\n")
out.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8", newline="\n")
print("wrote", out)
