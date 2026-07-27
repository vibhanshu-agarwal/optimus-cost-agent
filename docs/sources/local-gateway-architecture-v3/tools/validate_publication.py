"""Mechanical publication checks for the local Gateway architecture PDF set."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont
from pypdf import PdfReader

logging.disable(logging.WARNING)

SVG_NS = "http://www.w3.org/2000/svg"
TOKEN_RE = re.compile(r"[A-Za-z]|-?\d+(?:\.\d+)?")
FONT_RE = re.compile(r"\.([\w-]+)\s*\{[^}]*font:\s*(?:(\d+)\s+)?(\d+)px", re.DOTALL)


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    label: str

    def expanded(self, amount: float) -> Box:
        return Box(
            self.x0 - amount,
            self.y0 - amount,
            self.x1 + amount,
            self.y1 + amount,
            self.label,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--font-dir",
        type=Path,
        required=True,
        help="Directory containing DejaVuSans.ttf and DejaVuSans-Bold.ttf",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--pdf-only", action="store_true")
    mode.add_argument("--svg-only", action="store_true")
    return parser.parse_args()


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def version_from_filename(path: str) -> str:
    match = re.search(r"-v(\d+\.\d+)\.pdf$", path)
    if not match:
        raise AssertionError(f"Version not present in PDF filename: {path}")
    return match.group(1)


def validate_pdf_versions(root: Path) -> None:
    source_dir = root / "docs/sources/local-gateway-architecture-v3"
    manifest = json.loads((source_dir / "build-manifest.json").read_text(encoding="utf-8"))
    for document in manifest["documents"]:
        old_version = version_from_filename(document["source_pdf"])
        target_version = version_from_filename(document["output_pdf"])
        allowed_historical_pages = {
            int(value)
            for value in document.get("allowed_historical_version_pages", [])
        }
        output_path = root / document["output_pdf"]
        reader = PdfReader(output_path)
        if len(reader.pages) != int(document["expected_pages"]):
            raise AssertionError(
                f"{document['name']}: expected {document['expected_pages']} pages, "
                f"found {len(reader.pages)}"
            )
        if (reader.metadata.title or "") != document["metadata_title"]:
            raise AssertionError(
                f"{document['name']}: embedded title does not match manifest"
            )
        page_sizes = {
            (round(float(page.mediabox.width), 3), round(float(page.mediabox.height), 3))
            for page in reader.pages
        }
        if page_sizes != {(612.0, 792.0)}:
            raise AssertionError(
                f"{document['name']}: expected US Letter pages, found {page_sizes}"
            )
        digest = hashlib.sha256(output_path.read_bytes()).hexdigest().upper()
        if digest != document["sha256"]:
            raise AssertionError(
                f"{document['name']}: SHA-256 {digest} does not match manifest"
            )
        document_text: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = re.sub(r"\s+", " ", page.extract_text() or "")
            document_text.append(text)
            if target_version not in text:
                raise AssertionError(
                    f"{document['name']} page {page_number}: target version {target_version} absent"
                )
            if old_version in text and page_number not in allowed_historical_pages:
                raise AssertionError(
                    f"{document['name']} page {page_number}: superseded version {old_version} remains"
                )
        normalized_document = " ".join(document_text)
        missing_anchors = [
            anchor
            for anchor in document.get("critical_text", [])
            if anchor not in normalized_document
        ]
        if missing_anchors:
            raise AssertionError(
                f"{document['name']}: critical text absent: {missing_anchors}"
            )
        print(
            f"PASS {document['name']}: {len(reader.pages)} US Letter pages, metadata and "
            f"SHA-256 match; target {target_version} on every page; superseded "
            f"{old_version} absent outside explicit history"
        )


def css_fonts(root: ET.Element) -> dict[str, tuple[int, int]]:
    style = root.find(f".//{{{SVG_NS}}}style")
    if style is None or style.text is None:
        raise AssertionError("SVG has no embedded font styles")
    fonts: dict[str, tuple[int, int]] = {}
    for class_name, weight, size in FONT_RE.findall(style.text):
        fonts[class_name] = (int(weight or "400"), int(size))
    return fonts


def text_box(
    element: ET.Element,
    fonts: dict[str, tuple[int, int]],
    regular_font: Path,
    bold_font: Path,
) -> Box:
    class_name = element.get("class", "")
    if class_name not in fonts:
        raise AssertionError(f"Text class {class_name!r} has no parsed font declaration")
    weight, size = fonts[class_name]
    font = ImageFont.truetype(str(bold_font if weight >= 600 else regular_font), size=size)
    text = "".join(element.itertext()).strip()
    if not text:
        raise AssertionError("Empty SVG text element")
    x = float(element.get("x", "0"))
    y = float(element.get("y", "0"))
    measured = font.getbbox(text, anchor="ls")
    width = measured[2] - measured[0]
    anchor = element.get("text-anchor", "start")
    if anchor == "middle":
        x0 = x - width / 2
    elif anchor == "end":
        x0 = x - width
    else:
        x0 = x
    return Box(x0, y + measured[1], x0 + width, y + measured[3], text)


def path_points(path_data: str) -> list[tuple[float, float]]:
    tokens = TOKEN_RE.findall(path_data)
    points: list[tuple[float, float]] = []
    index = 0
    command = ""
    current = (0.0, 0.0)
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        if command == "M" or command == "L":
            current = (float(tokens[index]), float(tokens[index + 1]))
            points.append(current)
            index += 2
            command = "L"
        elif command == "H":
            current = (float(tokens[index]), current[1])
            points.append(current)
            index += 1
        elif command == "V":
            current = (current[0], float(tokens[index]))
            points.append(current)
            index += 1
        elif command == "C":
            start = current
            control_1 = (float(tokens[index]), float(tokens[index + 1]))
            control_2 = (float(tokens[index + 2]), float(tokens[index + 3]))
            end = (float(tokens[index + 4]), float(tokens[index + 5]))
            for step in range(1, 41):
                t = step / 40
                inverse = 1 - t
                x = (
                    inverse**3 * start[0]
                    + 3 * inverse**2 * t * control_1[0]
                    + 3 * inverse * t**2 * control_2[0]
                    + t**3 * end[0]
                )
                y = (
                    inverse**3 * start[1]
                    + 3 * inverse**2 * t * control_1[1]
                    + 3 * inverse * t**2 * control_2[1]
                    + t**3 * end[1]
                )
                points.append((x, y))
            current = end
            index += 6
        else:
            raise AssertionError(f"Unsupported SVG path command {command!r} in {path_data!r}")
    return points


def orientation(
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
) -> int:
    value = (second[1] - first[1]) * (third[0] - second[0]) - (
        second[0] - first[0]
    ) * (third[1] - second[1])
    if math.isclose(value, 0.0, abs_tol=1e-6):
        return 0
    return 1 if value > 0 else 2


def segments_intersect(
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
    fourth: tuple[float, float],
) -> bool:
    return (
        orientation(first, second, third) != orientation(first, second, fourth)
        and orientation(third, fourth, first) != orientation(third, fourth, second)
    )


def segment_intersects_box(
    start: tuple[float, float],
    end: tuple[float, float],
    box: Box,
) -> bool:
    if (
        box.x0 <= start[0] <= box.x1
        and box.y0 <= start[1] <= box.y1
        or box.x0 <= end[0] <= box.x1
        and box.y0 <= end[1] <= box.y1
    ):
        return True
    corners = [
        (box.x0, box.y0),
        (box.x1, box.y0),
        (box.x1, box.y1),
        (box.x0, box.y1),
    ]
    return any(
        segments_intersect(start, end, corners[index], corners[(index + 1) % 4])
        for index in range(4)
    )


def validate_svg(path: Path, regular_font: Path, bold_font: Path) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    width = float(root.get("viewBox", "0 0 0 0").split()[2])
    height = float(root.get("viewBox", "0 0 0 0").split()[3])
    fonts = css_fonts(root)
    text_boxes = [
        text_box(element, fonts, regular_font, bold_font)
        for element in root.findall(f".//{{{SVG_NS}}}text")
    ]
    rectangles = [
        Box(
            float(element.get("x", "0")),
            float(element.get("y", "0")),
            float(element.get("x", "0")) + float(element.get("width", "0")),
            float(element.get("y", "0")) + float(element.get("height", "0")),
            element.get("id", element.get("class", "rect")),
        )
        for element in root.findall(f".//{{{SVG_NS}}}rect")
    ]
    for box in text_boxes:
        if box.x0 < 0 or box.y0 < 0 or box.x1 > width or box.y1 > height:
            raise AssertionError(f"{path.name}: text outside canvas: {box.label!r}")
        for rectangle in rectangles:
            crosses_vertical = (
                box.y1 > rectangle.y0
                and box.y0 < rectangle.y1
                and (
                    box.x0 < rectangle.x0 < box.x1
                    or box.x0 < rectangle.x1 < box.x1
                )
            )
            crosses_horizontal = (
                box.x1 > rectangle.x0
                and box.x0 < rectangle.x1
                and (
                    box.y0 < rectangle.y0 < box.y1
                    or box.y0 < rectangle.y1 < box.y1
                )
            )
            if crosses_vertical or crosses_horizontal:
                raise AssertionError(
                    f"{path.name}: text {box.label!r} crosses {rectangle.label!r} border"
                )
    edge_paths = [
        element
        for element in root.findall(f".//{{{SVG_NS}}}path")
        if "edge" in element.get("class", "").split()
    ]
    edge_lines = [
        element
        for element in root.findall(f".//{{{SVG_NS}}}line")
        if {
            "edge",
            "call",
            "return",
            "trace",
        }
        & set(element.get("class", "").split())
    ]
    if not edge_paths and not edge_lines:
        raise AssertionError(f"{path.name}: no connectors selected")
    for element in edge_paths:
        points = path_points(element.get("d", ""))
        for start, end in zip(points, points[1:], strict=False):
            for text in text_boxes:
                if segment_intersects_box(start, end, text.expanded(2)):
                    raise AssertionError(
                        f"{path.name}: connector intersects text {text.label!r}"
                    )
    for element in edge_lines:
        start = (float(element.get("x1", "0")), float(element.get("y1", "0")))
        end = (float(element.get("x2", "0")), float(element.get("y2", "0")))
        for text in text_boxes:
            if segment_intersects_box(start, end, text.expanded(2)):
                raise AssertionError(
                    f"{path.name}: connector intersects text {text.label!r}"
                )
    print(
        f"PASS {path.name}: {len(text_boxes)} text bounds and "
        f"{len(edge_paths) + len(edge_lines)} connectors are collision-free"
    )


def main() -> None:
    args = parse_args()
    regular_font = args.font_dir / "DejaVuSans.ttf"
    bold_font = args.font_dir / "DejaVuSans-Bold.ttf"
    if not regular_font.is_file() or not bold_font.is_file():
        raise SystemExit("DejaVuSans.ttf and DejaVuSans-Bold.ttf are required")
    root = repository_root()
    if not args.svg_only:
        validate_pdf_versions(root)
    if not args.pdf_only:
        for path in sorted(
            (root / "docs/sources/local-gateway-architecture-v3/assets").glob("*.svg")
        ):
            validate_svg(path, regular_font, bold_font)


if __name__ == "__main__":
    main()
