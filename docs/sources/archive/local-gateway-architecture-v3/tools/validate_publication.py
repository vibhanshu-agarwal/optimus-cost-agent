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

from pypdf import PdfReader

logging.disable(logging.WARNING)

SVG_NS = "http://www.w3.org/2000/svg"
TOKEN_RE = re.compile(r"[A-Za-z]|-?\d+(?:\.\d+)?")
FONT_RE = re.compile(r"\.([\w-]+)\s*\{[^}]*font:\s*(?:(\d+)\s+)?(\d+)px", re.DOTALL)

BACKTICK_MARKER_RE = re.compile(r"`([^`\n]+)`")
IDENTIFIER_MARKER_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9]*(?:Policy|Registry|Manifest|Guard|Controller|Validator|Event|Ledger|State|"
    r"Request|Result|Settings|Usage|Client|Evaluator|Catalog|Scanner|Decision|Invocation|Service|Reason)\b"
)
FIELD_MARKER_RE = re.compile(
    r"\b(?:[A-Za-z][A-Za-z0-9]*_){1,}[A-Za-z][A-Za-z0-9]*\b"
)
SPECIAL_IDENTIFIER_RE = re.compile(
    r"\b(?:[A-Z]{2,}[A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)+|coverage\.py|pytest-cov)\b"
)
UPPERCASE_MARKER_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
ENDPOINT_MARKER_RE = re.compile(r"/(?:v1|api)/[A-Za-z0-9_./-]+")
HYPHENATED_CODE_MARKER_RE = re.compile(r"\b[A-Z][A-Za-z0-9]+-[A-Za-z0-9][A-Za-z0-9-]+\b")
HEADING_MARKER_RE = re.compile(
    r"^\s*(?:#+\s*)?"
    r"(?P<section>(?:\d{1,2}(?:\.\d+|[A-Z])+(?:\.)?|\d{1,2}\.|[A-Z]\.))"
    r"(?:\s+|$)"
)
SVG_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)]+\.svg)(?:\{[^}]*\})?\)")


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


@dataclass(frozen=True)
class InventoryDiff:
    """Bidirectional difference between source and candidate content markers."""

    missing: frozenset[str]
    added: frozenset[str]
    source: frozenset[str]
    candidate: frozenset[str]


def _normalized_marker(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip(".,;:"))


def _marker_value(marker: str) -> str:
    return marker.split(":", 1)[1] if ":" in marker else marker


def _marker_present_in_text(marker: str, text: str) -> bool:
    """Allow source code markers to survive PDF extraction without Markdown ticks."""

    value = _normalized_marker(_marker_value(marker))
    if not value or value.casefold() == "none":
        return True
    normalized_text = _normalized_marker(text)
    if value in normalized_text:
        return True
    # Some PDF extractors insert spaces at font-subset boundaries inside identifiers.
    compact_value = re.sub(r"\s+", "", value)
    compact_text = re.sub(r"\s+", "", normalized_text)
    return compact_value in compact_text


def extract_inventory(text: str) -> frozenset[str]:
    """Extract stable heading and component/identifier markers from a document."""

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"data-[A-Za-z-]+\s*=\s*\"[^\"]*\"", " ", text)
    # pypdf can split a glyph run inside words (for example ``T ool`` or
    # ``PyT estArch``) when a font subset changes. Rejoin only a single
    # uppercase glyph followed by a lowercase run; normal word spacing is
    # unaffected.
    text = re.sub(r"\b([A-Z])\s+(?=[a-z])", r"\1", text)
    markers: set[str] = set()
    for line in text.splitlines():
        if re.match(r"^\s*(?:Page\s+\d+\s+of\s+\d+|data-page=|data-total=)", line):
            continue
        heading = HEADING_MARKER_RE.match(line)
        if heading and heading.group("section"):
            markers.add(f"heading:{heading.group('section').rstrip('.')}" )
    for match in BACKTICK_MARKER_RE.finditer(text):
        value = _normalized_marker(match.group(1))
        if (
            len(value) >= 3
            and "=" not in value
            and "<" not in value
            and ">" not in value
            and not re.search(r"\s|:", value)
            and not re.fullmatch(r"[\d.]+", value)
        ):
            markers.add(f"identifier:{value}")
    for pattern in (
        IDENTIFIER_MARKER_RE,
        FIELD_MARKER_RE,
        UPPERCASE_MARKER_RE,
        ENDPOINT_MARKER_RE,
        HYPHENATED_CODE_MARKER_RE,
    ):
        for match in pattern.finditer(text):
            value = _normalized_marker(match.group(0))
            if len(value) >= 3 and value not in {"NONE", "None"}:
                markers.add(f"identifier:{value}")
    for match in SPECIAL_IDENTIFIER_RE.finditer(text):
        value = _normalized_marker(match.group(0))
        markers.add(f"identifier:{value}")
    return frozenset(markers)


def inventory_diff(source: str, candidate: str) -> InventoryDiff:
    source_markers = extract_inventory(source)
    candidate_markers = extract_inventory(candidate)
    return InventoryDiff(
        missing=frozenset(
            marker
            for marker in source_markers - candidate_markers
            if not _marker_present_in_text(marker, candidate)
        ),
        added=frozenset(candidate_markers - source_markers),
        source=source_markers,
        candidate=candidate_markers,
    )


def assert_inventory_complete(
    source: str,
    candidate: str,
    *,
    exceptions: list[dict[str, str]],
    known_entry_ids: set[str],
    forbidden_markers: set[str] | None = None,
) -> InventoryDiff:
    """Fail unless every source/candidate marker difference is redline-owned."""

    allowed: set[str] = set()
    for exception in exceptions:
        entry_id = str(exception.get("entry_id", ""))
        if entry_id not in known_entry_ids:
            raise AssertionError(f"unknown redline entry {entry_id!r} in completeness exception")
        marker = str(exception.get("marker", ""))
        if not marker:
            raise AssertionError(f"redline entry {entry_id!r} has an empty completeness marker")
        allowed.add(marker)
    diff = inventory_diff(source, candidate)
    forbidden = set(forbidden_markers or ())
    present_forbidden = forbidden & (set(diff.source) | set(diff.candidate))
    if present_forbidden:
        raise AssertionError(
            "forbidden inventory markers present: " + ", ".join(sorted(present_forbidden))
        )
    unresolved_missing = diff.missing - allowed
    unresolved_added = diff.added - allowed
    if unresolved_missing or unresolved_added:
        details: list[str] = []
        if unresolved_missing:
            details.append("missing=" + ", ".join(sorted(unresolved_missing)))
        if unresolved_added:
            details.append("added=" + ", ".join(sorted(unresolved_added)))
        raise AssertionError("publication completeness failed: " + "; ".join(details))
    return diff


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


def redline_entry_ids(root: Path) -> set[str]:
    report = root / "docs/superpowers/reports/2026-07-27-local-gateway-architecture-document-redline-v3.md"
    text = report.read_text(encoding="utf-8")
    return set(re.findall(r"^###\s+([A-Z][A-Z0-9-]*-\d+)\b", text, re.MULTILINE))


def pdf_text(reader: PdfReader, pages: set[int] | None = None) -> str:
    selected = (
        enumerate(reader.pages, start=1)
        if pages is None
        else ((number, reader.pages[number - 1]) for number in sorted(pages))
    )
    return "\n".join(page.extract_text() or "" for _, page in selected)


def effective_source_text(root: Path, document: dict[str, object]) -> str:
    """Combine corrected changed-page Markdown with the pinned carried-page source text."""

    changed_source = root / str(document["changed_source"])
    source_pdf = PdfReader(root / str(document["source_pdf"]))
    replacement_pages = {int(value) for value in document["replacement_pages"]}
    carried_pages = set(range(1, len(source_pdf.pages) + 1)) - replacement_pages
    changed_text = changed_source.read_text(encoding="utf-8")
    linked_assets: list[str] = []
    for relative_asset in SVG_LINK_RE.findall(changed_text):
        asset_path = changed_source.parent / relative_asset
        linked_assets.append(asset_path.read_text(encoding="utf-8"))
    carried_text = pdf_text(source_pdf, carried_pages)
    return changed_text + "\n" + "\n".join(linked_assets) + "\n" + carried_text


def validate_source_completeness(
    root: Path,
    document: dict[str, object],
    known_entry_ids: set[str],
) -> None:
    output_path = root / str(document["output_pdf"])
    candidate_text = pdf_text(PdfReader(output_path))
    source_text = effective_source_text(root, document)
    completeness = dict(document.get("completeness", {}))
    exceptions = [dict(item) for item in completeness.get("exceptions", [])]
    forbidden = {
        str(marker) for marker in completeness.get("forbidden_markers", [])
    }
    diff = assert_inventory_complete(
        source_text,
        candidate_text,
        exceptions=exceptions,
        known_entry_ids=known_entry_ids,
        forbidden_markers=forbidden,
    )
    print(
        f"PASS {document['name']}: source/candidate inventory complete; "
        f"{len(diff.source)} markers, {len(diff.missing)} authorized missing, "
        f"{len(diff.added)} authorized added"
    )


def validate_pdf_versions(root: Path) -> None:
    source_dir = root / "docs/sources/local-gateway-architecture-v3"
    manifest = json.loads((source_dir / "build-manifest.json").read_text(encoding="utf-8"))
    known_entry_ids = redline_entry_ids(root)
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
        validate_source_completeness(root, document, known_entry_ids)


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
    from PIL import ImageFont

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
