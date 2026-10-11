"""Assemble Plan 11.13 reversion pages and stamp new document controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

logging.disable(logging.WARNING)

FRAGMENT_NAMES = {
    "HLD": "hld.pdf",
    "LLD": "lld.pdf",
    "Test Strategy": "test.pdf",
    "Guardrails": "guard.pdf",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fragment-dir", type=Path, required=True)
    parser.add_argument("--font-dir", type=Path, required=True)
    return parser.parse_args()


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def version_from_filename(path: str) -> str:
    match = re.search(r"-v(\d+\.\d+)\.pdf$", path)
    if not match:
        raise AssertionError(f"Version not present in PDF filename: {path}")
    return match.group(1)


def register_fonts(font_dir: Path) -> None:
    pdfmetrics.registerFont(
        TTFont("PublicationDejaVuOblique", font_dir / "DejaVuSans-Oblique.ttf")
    )
    pdfmetrics.registerFont(
        TTFont("PublicationDejaVu", font_dir / "DejaVuSans.ttf")
    )
    pdfmetrics.registerFont(
        TTFont("PublicationLatoItalic", font_dir / "Lato-Italic.ttf")
    )


def page_overlay(
    header: str,
    guardrails: bool,
    inline_replacements: list[dict[str, object]],
    client_note: str | None = None,
) -> bytes:
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=letter)
    pdf.setFillColor(white)
    pdf.rect(48.18897675, 754, 515.62204725, 24, fill=1, stroke=0)
    pdf.setStrokeColor(HexColor("#b8c9dc"))
    pdf.setLineWidth(0.7)
    pdf.line(48.18897675, 755.73, 563.811024, 755.73)
    pdf.setFillColor(HexColor("#677387"))
    pdf.setFont(
        "PublicationLatoItalic" if guardrails else "PublicationDejaVuOblique",
        7.5,
    )
    pdf.drawRightString(563.811024, 762.7, header)
    if client_note:
        pdf.setFillColor(HexColor("#173b6c"))
        pdf.setFont("PublicationDejaVu", 6.3)
        pdf.drawString(48.18897675, 742.0, client_note)
    for replacement in inline_replacements:
        x = float(replacement["x"])
        y = float(replacement["y"])
        width = float(replacement["erase_width"])
        height = float(replacement["erase_height"])
        pdf.setFillColor(white)
        pdf.rect(x - 0.5, y - 2.5, width, height, fill=1, stroke=0)
        pdf.setFillColor(HexColor("#1a1a1a"))
        pdf.setFont("PublicationDejaVu", float(replacement["font_size"]))
        pdf.drawString(x, y, str(replacement["text"]))
    pdf.showPage()
    pdf.save()
    return stream.getvalue()


def matrix_values(operands: list[object]) -> tuple[float, ...]:
    return tuple(float(value) for value in operands)


def is_old_header_block(
    block: list[tuple[list[object], bytes]],
    *,
    inline_positions: list[tuple[float, float]],
) -> bool:
    matrices = [
        matrix_values(operands)
        for operands, operator in block
        if operator == b"Tm" and len(operands) == 6
    ]
    header_block = bool(matrices) and all(
        matrix[3] > 0 and matrix[4] > 300 and matrix[5] > 740
        or matrix[3] < 0 and matrix[4] > 350 and matrix[5] < 110
        for matrix in matrices
    )
    inline_replacement_block = any(
        any(
            math.isclose(matrix[4], x, abs_tol=0.1)
            and math.isclose(matrix[5], y, abs_tol=0.1)
            for x, y in inline_positions
        )
        for matrix in matrices
    )
    return header_block or inline_replacement_block


def remove_old_header_text(
    page: object,
    *,
    inline_positions: list[tuple[float, float]],
) -> int:
    content = ContentStream(page.get_contents(), page.pdf)
    operations = content.operations
    retained: list[tuple[list[object], bytes]] = []
    removed = 0
    index = 0
    while index < len(operations):
        if operations[index][1] != b"BT":
            retained.append(operations[index])
            index += 1
            continue
        end = index + 1
        while end < len(operations) and operations[end][1] != b"ET":
            end += 1
        if end >= len(operations):
            raise AssertionError("Unterminated PDF text block")
        block = operations[index : end + 1]
        if is_old_header_block(
            block,
            inline_positions=inline_positions,
        ):
            removed += 1
        else:
            retained.extend(block)
        index = end + 1
    content.operations = retained
    content._data = b""
    page.replace_contents(content)
    return removed


def assemble_document(
    root: Path,
    document: dict[str, object],
    fragment_dir: Path,
) -> str:
    name = str(document["name"])
    guardrails = name == "Guardrails"
    source = PdfReader(root / str(document["source_pdf"]))
    changed = PdfReader(fragment_dir / FRAGMENT_NAMES[name])
    replacement_pages = [int(value) for value in document["replacement_pages"]]
    if len(changed.pages) != len(replacement_pages):
        raise AssertionError(
            f"{name}: {len(changed.pages)} rendered pages for "
            f"{len(replacement_pages)} replacement positions"
        )
    # The first replacement is a new title/control page. Every other replacement restores
    # the byte-authored pre-amendment page body from the declared historical predecessor;
    # this reverses only amendment text without retyping unrelated authority.
    reversion_source = PdfReader(root / str(document["reversion_pdf"]))
    replacements = {replacement_pages[0]: changed.pages[0]}
    replacements.update(
        {
            page_number: reversion_source.pages[page_number - 1]
            for page_number in replacement_pages[1:]
        }
    )
    all_inline_replacements = [
        dict(value) for value in document.get("inline_text_replacements", [])
    ]
    writer = PdfWriter()
    removed_blocks = 0
    carried_pages = 0
    client_notes = {
        int(page): str(note)
        for page, note in dict(document.get("client_note_pages", {})).items()
    }
    for page_number, source_page in enumerate(source.pages, start=1):
        if page_number in replacements:
            if page_number == replacement_pages[0]:
                writer.add_page(replacements[page_number])
                continue
            source_page = replacements[page_number]
        else:
            carried_pages += 1
        inline_replacements = [
            value
            for value in all_inline_replacements
            if int(value["page"]) == page_number
        ]
        inline_positions = [
            (float(value["x"]), float(value["y"]))
            for value in inline_replacements
        ]
        page_writer = PdfWriter()
        page_writer.add_page(source_page)
        carried_page = page_writer.pages[0]
        removed = remove_old_header_text(
            carried_page,
            inline_positions=inline_positions,
        )
        if removed < 1:
            raise AssertionError(f"{name} page {page_number}: old header block not found")
        removed_blocks += removed
        overlay_bytes = page_overlay(
            str(document["page_header"]),
            guardrails,
            inline_replacements,
            client_notes.get(page_number),
        )
        overlay_page = PdfReader(BytesIO(overlay_bytes)).pages[0]
        carried_page.merge_page(overlay_page, over=True)
        page_stream = BytesIO()
        page_writer.write(page_stream)
        page_stream.seek(0)
        writer.add_page(PdfReader(page_stream).pages[0])
    metadata = {
        str(key): str(value)
        for key, value in (source.metadata or {}).items()
        if value is not None
    }
    metadata["/Title"] = str(document["metadata_title"])
    metadata["/Producer"] = (
        "Pandoc 3.1.3 + WeasyPrint 61.1 + ReportLab header stamp + pypdf reversion assembly"
    )
    writer.add_metadata(metadata)
    output = root / str(document["output_pdf"])
    with output.open("wb") as stream:
        writer.write(stream)
    digest = hashlib.sha256(output.read_bytes()).hexdigest().upper()
    print(
        f"{name}: {len(writer.pages)} pages; {carried_pages} carried pages stamped; "
        f"{removed_blocks} old header text blocks removed; SHA256={digest}"
    )
    return digest


def main() -> None:
    args = parse_args()
    register_fonts(args.font_dir)
    root = repository_root()
    manifest_path = root / (
        "docs/sources/gateway-mcp-authoritative-document-reversal/build-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for document in manifest["documents"]:
        document["sha256"] = assemble_document(root, document, args.fragment_dir)
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
