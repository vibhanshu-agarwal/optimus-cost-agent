"""Validate the built correction editions against their manifest, baselines and predecessors.

Checks (per document): manifest hash matches the file; page count; every baseline page position is
represented exactly once and successor pages are contiguous; every carried native page's body text
equals the baseline page's body text; every page carries the candidate label and the correction footer;
the predecessor page map covers every predecessor page; the text contains no HTML escape artifacts.
Writes document-validation.json beside the PDFs. Usage: validate_corrections.py REPO_ROOT BUILD_DIR
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from pathlib import Path

from pypdf import PdfReader

logging.disable(logging.CRITICAL)
repo = Path(sys.argv[1]).resolve()
build = Path(sys.argv[2]).resolve()
manifest = json.loads((build / "build-manifest.json").read_text(encoding="utf-8"))
LABEL = manifest["label"]
FOOTER = manifest["footer"]


def body(text: str) -> str:
    lines = []
    for s in text.splitlines():
        s = s.strip()
        if not s or s.startswith("Optimus-Cost-Agent - ") or s.startswith("Optimus - ") or s.startswith(FOOTER) or s.startswith("Plan 12 | "):
            continue
        if re.fullmatch(r"(Page \d+ of \d+|v\d+\.\d+|\d+ / \d+)", s):
            continue
        lines.append(s)
    return re.sub(r"\s+", "", "\n".join(lines))


results = []
failures = []
for key, d in manifest["documents"].items():
    target = build / d["file"]
    new = PdfReader(target)
    r = {"document": key, "file": d["file"], "pages": len(new.pages), "checks": {}}
    r["checks"]["manifest_hash_matches"] = hashlib.sha256(target.read_bytes()).hexdigest() == d["sha256"]
    r["checks"]["page_count_matches"] = len(new.pages) == d["pages"]
    physical = []
    for m in d["mapping"]:
        a, b = m["successor_pages"]
        physical.extend(range(a, b + 1))
    r["checks"]["successor_pages_contiguous"] = physical == list(range(1, len(new.pages) + 1))
    carries = 0
    carried_ok = True
    if d.get("baseline"):
        old = PdfReader(repo / "docs" / "archive" / d["baseline"])
        r["checks"]["baseline_hash_matches"] = hashlib.sha256((repo / "docs" / "archive" / d["baseline"]).read_bytes()).hexdigest() == d["baseline_sha256"]
        base_pages = [m["baseline_page"] for m in d["mapping"] if m["baseline_page"] is not None]
        r["checks"]["every_baseline_page_once"] = base_pages == list(range(1, len(old.pages) + 1))
        for m in d["mapping"]:
            if m["action"] == "carry-body":
                a, b = m["successor_pages"]
                if a != b:
                    carried_ok = False
                    failures.append(f"{key}: carried page {m['baseline_page']} spans {a}-{b}")
                ob = body(old.pages[m["baseline_page"] - 1].extract_text() or "")
                nb = body(new.pages[a - 1].extract_text() or "")
                if ob != nb:
                    carried_ok = False
                    failures.append(f"{key}: carried body mismatch baseline {m['baseline_page']} -> page {a} ({len(ob)} vs {len(nb)} chars)")
                carries += 1
    r["checks"]["carried_bodies_equal_baseline"] = carried_ok
    r["carried_native_pages"] = carries
    pred = repo / "docs" / d["predecessor"]
    if not pred.exists():
        pred = repo / "docs" / "archive" / d["predecessor"]
    pred_reader = PdfReader(pred)
    r["checks"]["predecessor_hash_matches"] = hashlib.sha256(pred.read_bytes()).hexdigest() == d["predecessor_sha256"]
    covered = set()
    for k in d["predecessor_page_map"]:
        if "-" in k:
            a, b = k.split("-")
            covered.update(range(int(a), int(b) + 1))
        else:
            covered.add(int(k))
    r["checks"]["predecessor_pages_all_mapped"] = covered == set(range(1, len(pred_reader.pages) + 1))
    r["predecessor_pages"] = len(pred_reader.pages)
    label_ok = True
    artifacts = []
    for n, p in enumerate(new.pages, start=1):
        t = p.extract_text() or ""
        if LABEL not in t or FOOTER not in t:
            label_ok = False
            failures.append(f"{key}: page {n} lacks label/footer")
        # Unrendered markup would surface as HTML entities or a font tag; a literal "<b>" is legitimate
        # content here (the ADL grammar placeholders "<a>" / "<b>" on the carried §5 page).
        for pat in ("&lt;", "&gt;", "&amp;", "&#", "<font", "\\u"):
            if pat in t:
                artifacts.append((n, pat))
    r["checks"]["label_and_footer_on_every_page"] = label_ok
    r["checks"]["no_escape_artifacts"] = not artifacts
    if artifacts:
        failures.append(f"{key}: escape artifacts {artifacts[:10]}")
    r["sha256"] = d["sha256"]
    r["status"] = "PASS" if all(r["checks"].values()) else "FAIL"
    results.append(r)

out = {
    "scope": "PDF assembly, carried native text, predecessor page coverage, label/footer presence and escape-artifact scan; no product or live run",
    "inspected_source": manifest["inspected_source"],
    "results": results,
    "failures": failures,
    "status": "PASS" if not failures and all(r["status"] == "PASS" for r in results) else "FAIL",
}
(build / "document-validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps({r["document"]: {"status": r["status"], "pages": r["pages"], "carried": r["carried_native_pages"], "pred_pages": r["predecessor_pages"], "checks": r["checks"]} for r in results}, indent=1))
print("FAILURES:", failures or "none")
