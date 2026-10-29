"""Derive the HLD v2.23 / LLD v2.46 sources from the v2.22/v2.45 sources and Codex's edits.

``sources/successor-edits.md`` is Codex's authored text, filed unchanged: two cover blocks, then OLD/NEW blocks.
Each OLD must occur exactly once in its source when it is applied, so every change is asserted, as in the
predecessor bundles. Writes this bundle's ``sources/``; with ``--readme`` it also applies the README blocks in
place (once: a second run finds no OLD and fails). A README block whose title names the root ``README.md`` applies
there; every other README block applies to ``docs/README.md``.

Usage: apply_successor_edits.py REPO_ROOT [--readme]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PREDECESSOR = Path("docs/sources/plan-12-4-auto-mode/sources")
BUNDLE = Path("docs/sources/p397-escalation-successor")
APPENDED = ("hld-14-context-engine.md", "hld-15-capability-status.md", "lld-13-context-integration.md", "lld-14-capability-status.md")
COVER = re.compile(r"^### (?P<item>H1|L1) — [^\n]+\n\n```markdown\n(?P<text>.*?)\n```$", re.M | re.S)
BLOCK = re.compile(
    r"^### (?P<item>[^\n]+?) — (?P<src>[^\n]+?)\s*\nOLD:\s*\n(?P<f1>`{3,})text\n(?P<old>.*?)\n(?P=f1)\s*\n"
    r"NEW:\s*\n(?P<f2>`{3,})text\n(?P<new>.*?)\n(?P=f2)\s*$",
    re.M | re.S,
)
EDITS_SECTION, README_SECTION, NOTES_SECTION = "## Edits", "## docs/README.md", "## Author notes"
ROOT_README = re.compile(r"\broot `?README\.md`?", re.I)


def block_headers(section: str) -> int:
    """The ``### `` lines outside code fences: NEW text may itself carry Markdown headings."""
    count, fence = 0, None
    for line in section.splitlines():
        run = len(line) - len(line.lstrip("`"))
        if run >= 3 and (fence is None or (run >= fence and not line.strip("`"))):
            fence = None if fence is not None else run
        elif fence is None and line.startswith("### "):
            count += 1
    return count


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
    pages = json.loads((repo / PREDECESSOR / "page-updates.json").read_text(encoding="utf-8"))
    files = {name: (repo / PREDECESSOR / name).read_text(encoding="utf-8") for name in APPENDED}
    readmes = {name: (repo / name).read_text(encoding="utf-8") for name in ("docs/README.md", "README.md")}
    edits_at, readme_at, notes_at = (edits.index(s) for s in (EDITS_SECTION, README_SECTION, NOTES_SECTION))

    blocks = [m for m in BLOCK.finditer(edits) if m.start() < notes_at]
    headers = block_headers(edits[edits_at:notes_at])
    if len(blocks) != headers:
        raise AssertionError(f"{headers} block headers but {len(blocks)} parsed OLD/NEW blocks")
    for m in blocks:
        src, old, new, where = m["src"].strip("`"), m["old"], m["new"], f"{m['item']} ({m['src']})"
        if m.start() > readme_at:
            name = "README.md" if ROOT_README.search(m["item"] + " " + m["src"]) else "docs/README.md"
            if args.readme:
                readmes[name] = replace_once(readmes[name], old, new, where)
        elif src.startswith(("hld/", "lld/")):
            doc, key = src.split("/")
            pages[doc][key] = replace_once(pages[doc][key], old, new, where)
        else:
            files[src] = replace_once(files[src], old, new, where)
    covers = {m["item"]: m["text"] + "\n" for m in COVER.finditer(edits)}
    if sorted(covers) != ["H1", "L1"]:
        raise AssertionError(f"expected the H1 and L1 covers, found {sorted(covers)}")

    out = repo / BUNDLE / "sources"
    out.mkdir(parents=True, exist_ok=True)
    (out / "page-updates.json").write_text(json.dumps(pages, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="")
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8", newline="")
    (out / "hld-cover.md").write_text(covers["H1"], encoding="utf-8", newline="")
    (out / "lld-cover.md").write_text(covers["L1"], encoding="utf-8", newline="")
    if args.readme:
        for name, text in readmes.items():
            (repo / name).write_text(text, encoding="utf-8", newline="")
    print(f"applied {len(blocks)} edit blocks; wrote {out}{' and the README blocks' if args.readme else ''}")


if __name__ == "__main__":
    main()
