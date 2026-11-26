"""Reproduce the complete #576 LLD sources from the #361 predecessor sources and the exact edit ledger.

The #361 bundle's derive step, narrowed to the one document this edition changes. Each OLD must occur exactly once
in its predecessor page; the result must equal the filed sources byte for byte.

Usage: python derive_sources.py REPO_ROOT OUTPUT_DIR
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CARRIED = ("lld-13-context-integration.md", "lld-14-capability-status.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    predecessor = args.repo.resolve() / "docs/sources/issue361-search-independent-metadata/sources"
    bundle = Path(__file__).resolve().parents[1]
    files = {name: (predecessor / name).read_text(encoding="utf-8") for name in CARRIED}
    pages = json.loads((predecessor / "page-updates.json").read_text(encoding="utf-8"))["lld"]
    edits = json.loads((bundle / "sources/edits.json").read_text(encoding="utf-8"))
    for edit in edits:
        if edit["file"] != "page-updates.json" or edit["document"] != "lld":
            raise ValueError(f"this edition edits only LLD page sources: {edit['file']} {edit['document']}")
        page = edit["page"]
        if pages[page].count(edit["old"]) != 1:
            raise ValueError(f"expected exactly one predecessor match: lld:{page}")
        pages[page] = pages[page].replace(edit["old"], edit["new"])
    files["page-updates.json"] = json.dumps({"lld": pages}, indent=2, ensure_ascii=False)
    for name, text in files.items():
        if text.encode("utf-8") != (bundle / "sources" / name).read_bytes():
            raise ValueError(f"derived source differs from published source: {name}")
    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"Verified and reproduced {len(files)} complete source files; {len(edits)} exact edits")


if __name__ == "__main__":
    main()
