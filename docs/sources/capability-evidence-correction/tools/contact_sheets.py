"""Render every page of every built PDF and tile them into contact sheets for visual review.

Usage: contact_sheets.py BUILD_DIR OUT_DIR [DPI] [PER_SHEET]
Writes <doc>-sheet-NN.png (3 columns) and a render-log.json with page counts and exit codes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

build = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 55
per_sheet = int(sys.argv[4]) if len(sys.argv) > 4 else 6
out.mkdir(parents=True, exist_ok=True)
log = {"renderer": f"Poppler pdftoppm {dpi} dpi", "documents": {}}
for pdf in sorted(build.glob("*.pdf")):
    stem = pdf.stem
    pages_dir = out / f"{stem}-pages"
    pages_dir.mkdir(exist_ok=True)
    proc = subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(pages_dir / "p")], capture_output=True, text=True)
    images = sorted(pages_dir.glob("p-*.png"))
    sheets = []
    for s in range(0, len(images), per_sheet):
        chunk = images[s : s + per_sheet]
        tiles = [Image.open(p) for p in chunk]
        w = max(t.width for t in tiles)
        h = max(t.height for t in tiles)
        cols = 3
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * w + (cols + 1) * 8, rows * h + (rows + 1) * 8), "#888888")
        for idx, t in enumerate(tiles):
            x = 8 + (idx % cols) * (w + 8)
            y = 8 + (idx // cols) * (h + 8)
            sheet.paste(t, (x, y))
        name = out / f"{stem}-sheet-{s // per_sheet + 1:02d}-pages-{s + 1}-{s + len(chunk)}.png"
        sheet.save(name)
        sheets.append(name.name)
    log["documents"][stem] = {"pages_rendered": len(images), "pdftoppm_exit": proc.returncode, "stderr_lines": len(proc.stderr.splitlines()), "sheets": sheets}
(out / "render-log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
print(json.dumps(log, indent=1))
