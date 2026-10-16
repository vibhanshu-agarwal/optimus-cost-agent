"""Build the capability/evidence correction editions from repository sources and archived baselines.

Derived from the sealed packet's ``sources/tools/build_drafts.py`` (plan12-closure-offline-review,
SHA256SUMS c3ce7da3...324a). Differences: it reads the complete successor sources from the repository
bundle, reads the native baselines from ``docs/archive`` (the same bytes the sealed packet carried),
adds a markdown-only document kind for the Roadmap, stamps the 2026-10-15 correction footer, and
records both the baseline mapping and the v2.19/v2.42/v1.8 page map in its manifest.

Usage: build_corrections.py REPO_ROOT OUT_DIR
Never run it inside the sealed original packet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from html import escape
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, KeepTogether, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

logging.disable(logging.WARNING)

LETTER = (612, 792)
A4 = (595.276, 841.89)
LABEL = "LOCAL FILING CANDIDATE - NOT ACTIVATED"
FOOTER = "Capability and evidence correction | 2026-10-15"
PIN = "91fd64ac78025efe1076bddb106ff89e6adb2030"  # pragma: allowlist secret

# key: (file prefix, baseline version, predecessor version, new version, title, [appended sources], pagesize)
DOCS = {
    "hld": ("Optimus-Cost-Agent-Architecture", "2.18", "2.19", "2.20", "Architecture (HLD)", ["hld-14-context-engine.md", "hld-15-capability-status.md"], LETTER),
    "lld": ("Optimus-Cost-Agent-LLD", "2.41", "2.42", "2.43", "Low-Level Design", ["lld-13-context-integration.md", "lld-14-capability-status.md"], LETTER),
    "test": ("Optimus-Cost-Agent-Test-Strategy", "1.7", "1.8", "1.9", "Test Strategy", ["test-15-context-evidence.md", "test-16-capability-status.md"], LETTER),
}
ROADMAP = ("Optimus-Architecture-Roadmap", None, "10", "11", "Architecture Roadmap", ["roadmap-v11.md"], A4)

PREDECESSOR_SHA = {
    "hld": "427b837ae97db6ed7b8f63529d7dd84fa653265f2c6be1917ad2f00241fca916",  # pragma: allowlist secret
    "lld": "4727b9ebbc9300f4f8f952468e1e2cf2350aad36ed38592eacfbb43d48661808",  # pragma: allowlist secret
    "test": "eac2765f9ffc23d496322a2d5491e78a84d669bf3ebe97b9c99d290274752f91",  # pragma: allowlist secret
    "roadmap": "3ce19aa343aad4ccee2c2812a8d8f0c3a33c800c854c8d1464b837665b89d86d",  # pragma: allowlist secret
}
BASELINE_SHA = {
    "hld": "0f8725765fecc9a93045fd26630457dfe7112508df164a3ec5bcc55dbc976807",  # pragma: allowlist secret
    "lld": "69400fd474eb30711fcc9a061243d6a4d2e35d39d7794d4aa69f5ff51b98109b",  # pragma: allowlist secret
    "test": "31a60c6a198c60cc1203ff5c4a8e6e0300a820ec18cc702e25f246edc51dc0b0",  # pragma: allowlist secret
}
# The sealed v2.19/v2.42/v1.8 manifests: baseline page -> successor page range (from build-manifest.json).
PREDECESSOR_MAP = {
    "hld": {i: (i, i) for i in range(1, 14)} | {None: (14, 15)},
    "lld": {i: (i, i) for i in range(1, 41)} | {None: (41, 44)},
    "test": {**{i: (i, i) for i in range(1, 9)}, 9: (9, 10), 10: (11, 11), 11: (12, 12), 12: (13, 13), 13: (14, 14), 14: (15, 15), None: (16, 18)},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def markdown_pdf(text: str, pagesize=LETTER) -> PdfReader:
    width = pagesize[0] - 96
    stream = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="DraftBody", fontName="DraftArial", fontSize=9, leading=12, spaceAfter=3, allowWidows=0, allowOrphans=0))
    styles.add(ParagraphStyle(name="DraftHeading", fontName="DraftArialBold", fontSize=13, leading=17, spaceBefore=9, spaceAfter=7, keepWithNext=True, textColor=colors.HexColor("#173b6c")))
    styles.add(ParagraphStyle(name="DraftSmallHeading", fontName="DraftArialBold", fontSize=10.5, leading=14, spaceBefore=7, spaceAfter=5, keepWithNext=True, textColor=colors.HexColor("#173b6c")))
    styles.add(ParagraphStyle(name="DraftTable", fontName="DraftArial", fontSize=8, leading=10, spaceAfter=0))
    styles.add(ParagraphStyle(name="DraftCode", fontName="Courier", fontSize=7, leading=8, spaceAfter=1))
    doc = SimpleDocTemplate(stream, pagesize=pagesize, leftMargin=48, rightMargin=48, topMargin=55, bottomMargin=49)
    story = []
    lines = text.splitlines()
    i = 0

    def fmt(s: str) -> str:
        s = s.replace("☐", "[ ]").replace("→", "->").replace("≤", "<=").replace("≥", ">=").replace("∈", "in").replace("\u00ad", "")
        s = escape(s)
        s = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', s)
        return s

    while i < len(lines):
        line = lines[i]
        i += 1
        if line in (":::flow", ":::graph"):
            graphical = line == ":::graph"
            nodes = []
            while i < len(lines) and lines[i] != ":::end":
                nodes.append(lines[i])
                i += 1
            i += 1
            story.append(BranchGraph(nodes, width) if graphical else Pipeline(nodes, width))
            story.append(Spacer(1, 10))
            continue
        if line.startswith("```"):
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i].replace("∈", "in").replace("→", "->"))
                i += 1
            i += 1
            story.append(Preformatted("\n".join(block), styles["DraftCode"], maxLineLength=105))
            story.append(Spacer(1, 6))
            continue
        if not line.strip():
            story.append(Spacer(1, 4))
            continue
        if line.startswith("|"):
            rows = [line]
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            cells = []
            for row in rows:
                vals = [v.strip() for v in row.strip().strip("|").split("|")]
                if all(re.fullmatch(r"[: -]+", v) for v in vals):
                    continue
                cells.append([Paragraph(fmt(v), styles["DraftTable"]) for v in vals])
            n = max(len(r) for r in cells)
            if any(len(r) != n for r in cells):
                raise AssertionError("Unequal table columns: " + rows[0][:60])
            table = Table(cells, colWidths=[width / n] * n, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e4edf7")), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b8c9dc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.extend([KeepTogether(table) if len(cells) <= 8 else table, Spacer(1, 7)])
            continue
        if line.startswith("# "):
            story.append(Paragraph(fmt(line[2:]), styles["DraftHeading"]))
            continue
        if line.startswith("## "):
            story.append(Paragraph(fmt(line[3:]), styles["DraftSmallHeading"]))
            continue
        if line.startswith("### "):
            story.append(Paragraph(fmt(line[4:]), styles["DraftSmallHeading"]))
            continue
        if line.startswith("> "):
            story.append(Paragraph(fmt(line[2:]), styles["DraftBody"]))
            continue
        if re.match(r"^\s*(?:[-•] |\d+[.)] )", line):
            match = re.match(r"^(\s*)([-•]|\d+[.)]) (.*)", line)
            indent = len(match.group(1))
            marker = match.group(2)
            content = [match.group(3)]
            while i < len(lines) and lines[i].strip() and not re.match(r"^\s*(?:[-•] |\d+[.)] )|^(?:#|\||```|:::)", lines[i]):
                content.append(lines[i].strip())
                i += 1
            bullet = "&#8226;" if marker in ("-", "•") else escape(marker)
            item_style = ParagraphStyle("ListItem", parent=styles["DraftBody"], leftIndent=12 + min(indent, 6) * 4, firstLineIndent=-10)
            story.append(Paragraph(bullet + " " + fmt(" ".join(content)), item_style))
            continue
        paragraph = [line]
        while i < len(lines) and lines[i].strip() and not re.match(r"^\s*(?:[-•] |\d+[.)] )|^(?:#|\||```|:::)", lines[i]):
            paragraph.append(lines[i].strip())
            i += 1
        story.append(Paragraph(fmt(" ".join(paragraph)), styles["DraftBody"]))
    doc.build(story)
    return PdfReader(BytesIO(stream.getvalue()))


class Pipeline(Flowable):
    def __init__(self, nodes, width):
        super().__init__()
        self.nodes = nodes
        self.width = width
        self.height = len(nodes) * 42 - 10

    def draw(self):
        c = self.canv
        mid = self.width / 2
        for i, label in enumerate(self.nodes):
            y = self.height - (i + 1) * 42 + 10
            c.setFillColor(colors.HexColor("#e5eef9"))
            c.setStrokeColor(colors.HexColor("#547dae"))
            c.roundRect(mid - 216, y, 432, 32, 5, fill=1, stroke=1)
            c.setFillColor(colors.HexColor("#173b6c"))
            c.setFont("DraftArial", 9)
            c.drawCentredString(mid, y + 13, label)
            if i < len(self.nodes) - 1:
                c.line(mid, y, mid, y - 10)
                c.line(mid - 4, y - 6, mid, y - 10)
                c.line(mid + 4, y - 6, mid, y - 10)


class BranchGraph(Flowable):
    def __init__(self, rows, width):
        super().__init__()
        self.nodes = []
        self.branches = {}
        for row in rows:
            if row.startswith("branch|"):
                _, ref, label = row.split("|", 2)
                self.branches.setdefault(ref, []).append(label)
            else:
                ident, label = row.split("|", 1) if "|" in row else (str(len(self.nodes)), row)
                self.nodes.append((ident, label))
        self.width = width
        self.height = len(self.nodes) * 50 + 8

    def draw(self):
        c = self.canv
        style = ParagraphStyle("graph", fontName="DraftArial", fontSize=8, leading=10, textColor=colors.HexColor("#173b6c"), alignment=1)
        for i, (ident, label) in enumerate(self.nodes):
            y = self.height - 50 * (i + 1)
            c.setFillColor(colors.HexColor("#e5eef9"))
            c.setStrokeColor(colors.HexColor("#547dae"))
            c.roundRect(4, y, 254, 38, 5, fill=1)
            p = Paragraph(escape(label), style)
            _, h = p.wrap(244, 36)
            p.drawOn(c, 9, y + (38 - h) / 2)
            if i < len(self.nodes) - 1:
                c.line(131, y, 131, y - 12)
                c.line(127, y - 8, 131, y - 12)
                c.line(135, y - 8, 131, y - 12)
            if ident in self.branches:
                label = "<br/>".join(escape(v) for v in self.branches[ident])
                c.setFillColor(colors.HexColor("#fff1dc"))
                c.roundRect(286, y, 222, 38, 5, fill=1)
                p = Paragraph(label, style)
                _, h = p.wrap(212, 36)
                p.drawOn(c, 291, y + (38 - h) / 2)
                c.line(258, y + 19, 286, y + 19)
                c.line(281, y + 23, 286, y + 19)
                c.line(281, y + 15, 286, y + 19)


def remove_controls(page):
    """Strip the predecessor's running header/footer text blocks from a carried native page."""
    positions = []

    def visit(text, cm, tm, font, size):
        s = text.strip()
        if s.startswith("Optimus-Cost-Agent - ") or re.fullmatch(r"Page \d+ of \d+", s) or re.fullmatch(r"v\d+\.\d+", s):
            positions.append((float(tm[4]), float(tm[5])))

    page.extract_text(visitor_text=visit)
    content = ContentStream(page.get_contents(), page.pdf)
    ops = content.operations
    keep = []
    i = 0
    while i < len(ops):
        if ops[i][1] != b"BT":
            keep.append(ops[i])
            i += 1
            continue
        j = i + 1
        while j < len(ops) and ops[j][1] != b"ET":
            j += 1
        if j == len(ops):
            raise AssertionError("Unterminated text")
        block = ops[i : j + 1]
        matrices = [args for args, op in block if op == b"Tm" and len(args) == 6]
        drop = any(abs(float(m[4]) - x) < 0.05 and abs(float(m[5]) - y) < 0.05 for m in matrices for x, y in positions)
        if not drop:
            keep.extend(block)
        i = j + 1
    content.operations = keep
    content._data = b""
    page.replace_contents(content)


def stamp(page, title, version, n, total, pagesize):
    w, h = pagesize
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=pagesize)
    c.setFillColor(colors.white)
    c.rect(0, h - 40, w, 40, fill=1, stroke=0)
    c.rect(0, 0, w, 36, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#526478"))
    c.setFont("DraftArial", 7)
    c.drawString(48, h - 22, f"Optimus - {title} v{version} | {LABEL}")
    c.drawRightString(w - 48, 22, f"{n} / {total}")
    c.drawString(48, 22, FOOTER)
    c.save()
    page.merge_page(PdfReader(BytesIO(buf.getvalue())).pages[0])


def register_fonts():
    pdfmetrics.registerFont(TTFont("DraftArial", r"C:\Windows\Fonts\arial.ttf"))
    pdfmetrics.registerFont(TTFont("DraftArialBold", r"C:\Windows\Fonts\arialbd.ttf"))
    pdfmetrics.registerFont(TTFont("DraftArialItalic", r"C:\Windows\Fonts\ariali.ttf"))
    pdfmetrics.registerFont(TTFont("DraftArialBoldItalic", r"C:\Windows\Fonts\arialbi.ttf"))
    pdfmetrics.registerFontFamily("DraftArial", normal="DraftArial", bold="DraftArialBold", italic="DraftArialItalic", boldItalic="DraftArialBoldItalic")


def cover_text(key, title, prefix, predecessor_version, new_version, baseline_version):
    base_line = ""
    if baseline_version:
        base_line = (
            f"Native carried page bodies originate from {prefix}-v{baseline_version}.pdf (SHA-256 {BASELINE_SHA[key]}), exactly as "
            f"v{predecessor_version} carried them; corrected bodies are replaced in place and the new status section is appended. "
            "Every v" + predecessor_version + " page position is accounted for in the correction map.\n\n"
        )
    else:
        base_line = "This edition is rendered entirely from its Markdown source; v10 (a WeasyPrint rendering) had no source in the repository.\n\n"
    return (
        f"# Optimus - {title}\n\n"
        f"**Version {new_version} — capability and evidence correction, 2026-10-15; reviewed local filing candidate.**\n\n"
        f"Predecessor: {prefix}-v{predecessor_version}.pdf; SHA-256 {PREDECESSOR_SHA[key]}. "
        + ("v" + predecessor_version + " was filed locally on 2026-10-05 and merged to main through PR #276 (c509fc8, 2026-10-08). " if baseline_version else "v10 dates from the repository's initial commit. ")
        + "\n\n"
        + base_line
        + f"**What this edition changes.** For every material capability it separates what is implemented, what has been verified and how, and what is active, at the inspected source {PIN} (origin/main, 2026-10-15). It changes no accepted requirement, number or historical record. Each correction is listed with its source reference in the correction map filed with the sources (docs/sources/capability-evidence-correction/).\n\n"
        f"**Inspected production facts at 91fd64a.** ENFORCEMENT_ACTIVE is False and trusted_snapshot() returns None; no production path constructs ContextAttachment; the shipped alias claude-haiku resolves to anthropic/claude-haiku-4.5; the Gateway web-search provider is Tavily with a Gateway-only key; package/OSV routes still depend on that search configuration; no PyTestArch, maintainability-index, DeepEval, Ragas, PyRIT, Tirith or Vercel dependency, import or test exists; no Rust source exists.\n\n"
        "**Historical acceptance stays attached to its pins.** Offline implementation candidate cf9bb9d (Codex review 2026-10-04); documentation filing 5ee081e; operator acceptance of the offline delivery through 2068366 (2026-10-08); merge c509fc8 (PR #276). The deferred live obligations (Luna route/estimator qualification, genuine summary-quality receipt, real-editor Task 13) remain UNRUN under Plan 12.2 ownership (issue #237). Offline acceptance is not production acceptance, a full CP4 pass or permission to remove the shipped model default.\n\n"
        "**Authority.** Prepared by Claude under the operator's documentation-correction request; Fable 5.1 and Codex review at the plan's checkpoints. This document grants no paid or live calls, activation, push, PR or merge authority, and it was produced without running any product suite.\n"
    )


def build_doc(key, repo: Path, bundle: Path, out: Path, updates, manifest):
    prefix, baseline_version, predecessor_version, new_version, title, appended, pagesize = DOCS[key]
    basefile = repo / "docs" / "archive" / f"{prefix}-v{baseline_version}.pdf"
    if sha256(basefile) != BASELINE_SHA[key]:
        raise AssertionError(f"baseline hash mismatch for {basefile}")
    predecessor = repo / "docs" / f"{prefix}-v{predecessor_version}.pdf"
    if not predecessor.exists():
        predecessor = repo / "docs" / "archive" / f"{prefix}-v{predecessor_version}.pdf"
    if sha256(predecessor) != PREDECESSOR_SHA[key]:
        raise AssertionError(f"predecessor hash mismatch for {predecessor}")
    reader = PdfReader(basefile)
    writer = PdfWriter()
    mapping = []
    edits = updates[key]
    for p in markdown_pdf(cover_text(key, title, prefix, predecessor_version, new_version, baseline_version), pagesize).pages:
        writer.add_page(p)
    mapping.append({"baseline_page": 1, "action": "replace-cover", "successor_pages": [1, len(writer.pages)]})
    for i, page in enumerate(reader.pages, start=1):
        if i == 1:
            continue
        start = len(writer.pages) + 1
        if str(i) in edits:
            for replacement_page in markdown_pdf(edits[str(i)], pagesize).pages:
                writer.add_page(replacement_page)
            action = "replace-body"
        else:
            writer.add_page(page)
            remove_controls(writer.pages[-1])
            action = "carry-body"
        mapping.append({"baseline_page": i, "action": action, "successor_pages": [start, len(writer.pages)]})
    for source in appended:
        start = len(writer.pages) + 1
        text = (bundle / "sources" / source).read_text(encoding="utf-8")
        for p in markdown_pdf(text, pagesize).pages:
            writer.add_page(p)
        mapping.append({"baseline_page": None, "action": "new-section", "source": source, "successor_pages": [start, len(writer.pages)]})
    total = len(writer.pages)
    for n, p in enumerate(writer.pages, start=1):
        stamp(p, title, new_version, n, total, pagesize)
    writer.add_metadata({
        "/Title": f"Optimus {title} v{new_version} - capability and evidence correction (reviewed local filing candidate)",
        "/Author": "Claude - correction author; Fable 5.1 and Codex review at checkpoints",
        "/Subject": "Capability, verification and activation correction of 2026-10-15; publication and activation separate",
        "/CreationDate": "D:20261015000000+0530",
    })
    target = out / f"{prefix}-v{new_version}.pdf"
    with target.open("wb") as f:
        writer.write(f)
    # predecessor page map: v(predecessor) page -> v(new) pages, via the shared baseline positions
    pred_map = {}
    for base_page, (a, b) in PREDECESSOR_MAP[key].items():
        if base_page is None:
            continue
        new_range = next(m["successor_pages"] for m in mapping if m["baseline_page"] == base_page)
        for pp in range(a, b + 1):
            pred_map[str(pp)] = new_range
    appended_pred = PREDECESSOR_MAP[key][None]
    new_sections = [m for m in mapping if m["baseline_page"] is None]
    pred_map[f"{appended_pred[0]}-{appended_pred[1]}"] = [new_sections[0]["successor_pages"][0], new_sections[0]["successor_pages"][1]]
    manifest["documents"][key] = {
        "file": target.name, "pages": total, "sha256": sha256(target), "predecessor": predecessor.name,
        "predecessor_sha256": PREDECESSOR_SHA[key], "baseline": basefile.name, "baseline_sha256": BASELINE_SHA[key],
        "mapping": mapping, "predecessor_page_map": pred_map,
        "appended_sources": {s: hashlib.sha256((bundle / "sources" / s).read_bytes()).hexdigest() for s in appended},
    }


def build_roadmap(repo: Path, bundle: Path, out: Path, manifest):
    prefix, _, predecessor_version, new_version, title, appended, pagesize = ROADMAP
    predecessor = repo / "docs" / f"{prefix}-v{predecessor_version}.pdf"
    if not predecessor.exists():
        predecessor = repo / "docs" / "archive" / f"{prefix}-v{predecessor_version}.pdf"
    if sha256(predecessor) != PREDECESSOR_SHA["roadmap"]:
        raise AssertionError("roadmap predecessor hash mismatch")
    writer = PdfWriter()
    text = (bundle / "sources" / appended[0]).read_text(encoding="utf-8")
    for p in markdown_pdf(text, pagesize).pages:
        writer.add_page(p)
    total = len(writer.pages)
    for n, p in enumerate(writer.pages, start=1):
        stamp(p, title, new_version, n, total, pagesize)
    writer.add_metadata({
        "/Title": f"Optimus {title} v{new_version} - capability and evidence correction (reviewed local filing candidate)",
        "/Author": "Claude - correction author; Fable 5.1 and Codex review at checkpoints",
        "/Subject": "Capability, verification and activation correction of 2026-10-15; publication and activation separate",
        "/CreationDate": "D:20261015000000+0530",
    })
    target = out / f"{prefix}-v{new_version}.pdf"
    with target.open("wb") as f:
        writer.write(f)
    manifest["documents"]["roadmap"] = {
        "file": target.name, "pages": total, "sha256": sha256(target), "predecessor": predecessor.name,
        "predecessor_sha256": PREDECESSOR_SHA["roadmap"], "baseline": None, "mapping": [{"baseline_page": None, "action": "new-document", "source": appended[0], "successor_pages": [1, total]}],
        "predecessor_page_map": {"1-2": [1, total]},
        "appended_sources": {appended[0]: hashlib.sha256((bundle / "sources" / appended[0]).read_bytes()).hexdigest()},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("out")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bundle = repo / "docs" / "sources" / "capability-evidence-correction"
    register_fonts()
    updates = json.loads((bundle / "sources" / "page-updates.json").read_text(encoding="utf-8"))
    manifest = {"inspected_source": PIN, "built": "2026-10-15", "label": LABEL, "footer": FOOTER, "page_updates_sha256": sha256(bundle / "sources" / "page-updates.json"), "documents": {}}
    for key in DOCS:
        build_doc(key, repo, bundle, out, updates, manifest)
    build_roadmap(repo, bundle, out, manifest)
    (out / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: {"pages": v["pages"], "sha256": v["sha256"]} for k, v in manifest["documents"].items()}, indent=2))


if __name__ == "__main__":
    main()
