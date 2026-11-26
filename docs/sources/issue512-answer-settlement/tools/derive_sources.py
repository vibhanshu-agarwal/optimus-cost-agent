"""Reproduce the complete #512 HLD and LLD sources from their predecessor sources and the exact edit ledger.

The LLD's predecessor sources are the #576 bundle's (LLD v2.49); the HLD's are the #361 bundle's (HLD v2.25), the
last edition of each. Edits may change a page source or an appended chapter. Each OLD must occur exactly once in its
predecessor text; the result must equal the filed sources byte for byte.

Usage: python derive_sources.py REPO_ROOT OUTPUT_DIR
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# document key -> (predecessor bundle, appended chapters)
PREDECESSORS = {
    "hld": ("issue361-search-independent-metadata", ("hld-14-context-engine.md", "hld-15-capability-status.md")),
    "lld": ("issue576-edit-failure-lifecycle", ("lld-13-context-integration.md", "lld-14-capability-status.md")),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    sources = args.repo.resolve() / "docs/sources"
    bundle = Path(__file__).resolve().parents[1]
    files: dict[str, str] = {}
    pages: dict[str, dict[str, str]] = {}
    for key, (predecessor, chapters) in PREDECESSORS.items():
        files.update({name: (sources / predecessor / "sources" / name).read_text(encoding="utf-8") for name in chapters})
        pages[key] = json.loads((sources / predecessor / "sources/page-updates.json").read_text(encoding="utf-8"))[key]
    edits = json.loads((bundle / "sources/edits.json").read_text(encoding="utf-8"))
    for edit in edits:
        if edit["file"] == "page-updates.json" and edit.get("document") in pages:
            text, where = pages[edit["document"]][edit["page"]], f"{edit['document']}:{edit['page']}"
        elif edit["file"] in files:
            text, where = files[edit["file"]], edit["file"]
        else:
            raise ValueError(f"this edition edits only HLD and LLD sources: {edit['file']}")
        if text.count(edit["old"]) != 1:
            raise ValueError(f"expected exactly one predecessor match: {where}")
        if edit["file"] == "page-updates.json":
            pages[edit["document"]][edit["page"]] = text.replace(edit["old"], edit["new"])
        else:
            files[edit["file"]] = text.replace(edit["old"], edit["new"])
    files["page-updates.json"] = json.dumps(pages, indent=2, ensure_ascii=False)
    for name, text in files.items():
        if text.encode("utf-8") != (bundle / "sources" / name).read_bytes():
            raise ValueError(f"derived source differs from published source: {name}")
    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"Verified and reproduced {len(files)} complete source files; {len(edits)} exact edits")


if __name__ == "__main__":
    main()
