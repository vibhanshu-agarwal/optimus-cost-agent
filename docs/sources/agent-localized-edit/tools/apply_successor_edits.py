"""Derive the HLD v2.21 / LLD v2.44 sources from the 2026-10-15 correction sources and Codex's edits.

``sources/successor-edits.md`` is Codex's authored text, filed unchanged: two cover blocks, then OLD/NEW blocks.
Each OLD must occur exactly once in its source when it is applied, so every change is asserted, as in the
predecessor bundle's ``author_corrections.py``. Writes this bundle's ``sources/``; with ``--readme`` it also
applies the ``docs/README.md`` blocks in place (once: a second run finds no OLD and fails).

Usage: apply_successor_edits.py REPO_ROOT [--readme]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PREDECESSOR = Path("docs/sources/capability-evidence-correction/sources")
BUNDLE = Path("docs/sources/agent-localized-edit")
APPENDED = ("hld-14-context-engine.md", "hld-15-capability-status.md", "lld-13-context-integration.md", "lld-14-capability-status.md")
COVER = re.compile(r"^### (?P<item>H1|L1) — [^\n]+\n\n```markdown\n(?P<text>.*?)\n```$", re.M | re.S)
BLOCK = re.compile(
    r"^### (?P<item>[^\n]+?) — (?P<src>[^\n]+?)\s*\nOLD:\s*\n(?P<f1>`{3,})text\n(?P<old>.*?)\n(?P=f1)\s*\n"
    r"NEW:\s*\n(?P<f2>`{3,})text\n(?P<new>.*?)\n(?P=f2)\s*$",
    re.M | re.S,
)
README_SECTION = "## docs/README.md"


def replace_once(text: str, old: str, new: str, where: str) -> str:
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{where}: OLD found {count} times")
    return text.replace(old, new)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--readme", action="store_true")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    edits = (repo / BUNDLE / "sources" / "successor-edits.md").read_text(encoding="utf-8")
    updates = json.loads((repo / PREDECESSOR / "page-updates.json").read_text(encoding="utf-8"))
    pages = {doc: updates[doc] for doc in ("hld", "lld")}  # the Test Strategy is not part of this successor
    files = {name: (repo / PREDECESSOR / name).read_text(encoding="utf-8") for name in APPENDED}
    readme_path = repo / "docs" / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme_at = edits.index(README_SECTION)

    blocks = list(BLOCK.finditer(edits))
    for m in blocks:
        src, old, new, where = m["src"].strip("`"), m["old"], m["new"], f"{m['item']} ({m['src']})"
        if m.start() > readme_at:
            if args.readme:
                readme = replace_once(readme, old, new, where)
        elif src.startswith(("hld/", "lld/")):
            doc, key = src.split("/")
            pages[doc][key] = replace_once(pages[doc][key], old, new, where)
        else:
            files[src] = replace_once(files[src], old, new, where)
    covers = {m["item"]: m["text"] + "\n" for m in COVER.finditer(edits)}
    if sorted(covers) != ["H1", "L1"] or len(blocks) != 23:
        raise AssertionError(f"expected 2 covers and 23 edit blocks, found {sorted(covers)} and {len(blocks)}")

    out = repo / BUNDLE / "sources"
    (out / "page-updates.json").write_text(json.dumps(pages, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8", newline="")
    (out / "hld-cover.md").write_text(covers["H1"], encoding="utf-8", newline="")
    (out / "lld-cover.md").write_text(covers["L1"], encoding="utf-8", newline="")
    if args.readme:
        readme_path.write_text(readme, encoding="utf-8", newline="")
    print(f"applied {len(blocks)} edit blocks; wrote {out}{' and docs/README.md' if args.readme else ''}")


if __name__ == "__main__":
    main()
