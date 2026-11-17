"""Reproduce the complete #361 sources from predecessor inputs and exact edits.

Usage: python derive_sources.py REPO_ROOT OUTPUT_DIR
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    predecessor = args.repo.resolve() / "docs/sources/plan-12-9-cost-savings-successor/sources"
    bundle = Path(__file__).resolve().parents[1]
    files = {p.name: p.read_text(encoding="utf-8") for p in predecessor.glob("*.md") if p.name != "successor-edits.md"}
    updates = json.loads((predecessor / "page-updates.json").read_text(encoding="utf-8"))
    edits = json.loads((bundle / "sources/edits.json").read_text(encoding="utf-8"))
    for edit in edits:
        name = edit["file"]
        if name == "page-updates.json":
            pages = updates[edit["document"]]
            page = edit["page"]
            old = edit["old"]
            if old is None:
                if page in pages:
                    raise ValueError(f"page {page} must be a new authored replacement")
                pages[page] = edit["new"]
            else:
                if pages[page].count(old) != 1:
                    raise ValueError(f"expected exactly one predecessor match: {edit['document']}:{page}")
                pages[page] = pages[page].replace(old, edit["new"])
        else:
            if name not in files or files[name].count(edit["old"]) != 1:
                raise ValueError(f"expected exactly one predecessor match: {name}")
            files[name] = files[name].replace(edit["old"], edit["new"])
    files["page-updates.json"] = json.dumps(updates, indent=2, ensure_ascii=False)
    # Verify the authored complete sources before producing a build input copy.
    for name, text in files.items():
        if text.encode("utf-8") != (bundle / "sources" / name).read_bytes():
            raise ValueError(f"derived source differs from published source: {name}")
    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"Verified and reproduced {len(files)} complete source files; {len(edits)} exact edits")


if __name__ == "__main__":
    main()
