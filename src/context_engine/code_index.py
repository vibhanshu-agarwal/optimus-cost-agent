"""From one file's bytes to the records the index may keep (Plan 12.10 Task 3; ADR-037). Neutral: no host, Gateway or security import.

B1 decides what can leave this module. A record holds identifiers, a signature with its string literals masked, a deterministic
structural description, a relative path and hashes, and for documentation its prose with code blocks removed. It never holds a
source body, comment, docstring or literal. The text to embed may include all of those: it stays in RAM on `embed_text`, is sent
only to the local embedder, and only its vector persists. That vector carries the inversion risk the design records.

Parsing is lazy, so importing the engine needs no optional package. Languages without a parser get a file record, listing
coverage and no parsed lines.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Final

PARSER_VERSION: Final = "code-index-v1"
MAX_SIGNATURE_CHARS: Final = 2048
MAX_PROSE_CHARS: Final = 8000
MAX_TERMS_CHARS: Final = 16000
MAX_EMBED_CHARS: Final = 8000
MAX_IMPORTS: Final = 64
_MASK: Final = '"..."'
_LANGUAGES: Final = {".py": "python", ".java": "java", ".md": "markdown", ".markdown": "markdown", ".rst": "markdown", ".txt": "text"}
_IDENTIFIER_NODES: Final = frozenset({"identifier", "type_identifier", "field_identifier", "dotted_name"})
_LITERAL_NODES: Final = frozenset({"string", "string_literal", "character_literal", "text_block", "concatenated_string"})
_IMPORTED_NAME_NODES: Final = frozenset({"dotted_name", "scoped_identifier", "aliased_import", "identifier"})
_COMMENT_NODES: Final = frozenset({"comment", "line_comment", "block_comment"})
_PYTHON_SCOPES: Final = {"function_definition": "function", "class_definition": "class"}
_JAVA_SCOPES: Final = {"class_declaration": "class", "interface_declaration": "interface", "enum_declaration": "enum", "record_declaration": "record",
                       "annotation_type_declaration": "annotation", "method_declaration": "method", "constructor_declaration": "constructor"}
_CONTAINERS: Final = frozenset({"class", "interface", "enum", "record", "annotation"})
_IMPORT_NODES: Final = frozenset({"import_statement", "import_from_statement", "import_declaration"})
_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_INDENTED_MARKDOWN = re.compile(r"^(?: {4}|\t)")
_INDENTED_ANY = re.compile(r"^\s+\S")
_CODE_LINE = re.compile(r"^\s*(?:>>>|\.\.\s)")
# Inline spans and HTML blocks; a stray backtick then takes the rest of its line. A false match costs prose, never leaks code.
_INLINE_CODE = re.compile(r"(`+)[\s\S]*?\1|<(pre|code)\b[\s\S]*?(?:</\2>|\Z)", re.IGNORECASE)
_STRAY_BACKTICK = re.compile(r"`.*$", re.MULTILINE)
_CODE_LITERAL = re.compile(
    r'''("""[\s\S]*?(?:"""|\Z)|\'\'\'[\s\S]*?(?:\'\'\'|\Z)|/\*[\s\S]*?(?:\*/|\Z)|<!--[\s\S]*?(?:-->|\Z)'''
    r'''|"(?:\\.|[^"\\\n])*(?:"|$)|\'(?:\\.|[^\'\\\n])*(?:\'|$)|`[^`\n]*(?:`|$)|\#.*$|//.*$|--\s.*$)''',
    re.MULTILINE,
)


@dataclass(frozen=True)
class IndexRecord:
    id: str
    kind: str
    path: str
    path_id: str
    file_hash: str
    language: str
    terms: str
    symbol: str | None = None
    signature: str | None = None
    description: str | None = None
    prose: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    modified: int | None = None
    embed_text: str | None = field(default=None, repr=False)  # RAM only; never part of `wire`

    def wire(self) -> dict[str, Any]:
        """What may leave the engine, without the vector, which the caller adds."""
        body: dict[str, Any] = {"id": self.id, "kind": self.kind, "path": self.path, "path_id": self.path_id, "file_hash": self.file_hash,
                                "language": self.language, "terms": self.terms}
        for name in ("symbol", "signature", "description", "prose", "start_line", "end_line", "modified"):
            value = getattr(self, name)
            if value is not None:
                body[name] = value
        return body


@dataclass(frozen=True)
class ParsedFile:
    file_hash: str
    language: str
    parsed_lines: int  # non-blank lines this parser understood; zero for a language it does not parse
    records: tuple[IndexRecord, ...]
    parse_errors: bool = False


def digest(text: str | bytes) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def path_id(path: str) -> str:
    return digest(path)


def language_for(path: str) -> str:
    suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return _LANGUAGES.get(suffix, "unsupported")


def split_terms(words: Any) -> str:
    """Lowercase search terms: each identifier whole and split at snake and camel boundaries. Sorted and deduplicated, so the
    original order, which would begin to spell the source, is gone."""
    terms: set[str] = set()
    for word in words:
        for token in _WORD.findall(word):
            lowered = token.lower()
            if len(lowered) <= 64:
                terms.add(lowered)
            for part in _CASE_BOUNDARY.sub("_", token).split("_"):
                if 1 < len(part) <= 64:
                    terms.add(part.lower())
    text = " ".join(sorted(terms))
    return text[:MAX_TERMS_CHARS].rsplit(" ", 1)[0] if len(text) > MAX_TERMS_CHARS else text


def _record_id(kind: str, path: str, file_hash: str, ordinal: int, label: str) -> str:
    return digest(f"{PARSER_VERSION}\0{kind}\0{path}\0{file_hash}\0{ordinal}\0{label}")


def parse_file(path: str, data: bytes, *, modified: int | None = None) -> ParsedFile:
    file_hash = digest(data)
    language = language_for(path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _listed_only(path, file_hash, modified)
    if language == "python":
        return _parse_code(path, data, text, file_hash, modified, language, _PYTHON_SCOPES)
    if language == "java":
        return _parse_code(path, data, text, file_hash, modified, language, _JAVA_SCOPES)
    if language in {"markdown", "text"}:
        return _parse_document(path, text, file_hash, modified, language)
    return _listed_only(path, file_hash, modified)


def _listed_only(path: str, file_hash: str, modified: int | None) -> ParsedFile:
    return ParsedFile(file_hash, "unsupported", 0, (_file_record(path, file_hash, "unsupported", modified, split_terms([path]), None),))


def _file_record(path: str, file_hash: str, language: str, modified: int | None, terms: str, imports: str | None) -> IndexRecord:
    return IndexRecord(id=_record_id("file", path, file_hash, 0, ""), kind="file", path=path, path_id=path_id(path), file_hash=file_hash,
                       language=language, terms=terms, description=imports, modified=modified)


def _parsers(language: str) -> Any:
    import tree_sitter  # noqa: PLC0415 - optional package, imported only when a file of this language is parsed

    if language == "python":
        import tree_sitter_python  # noqa: PLC0415

        return tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))
    import tree_sitter_java  # noqa: PLC0415

    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_java.language()))


def _walk(node: Any) -> Any:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _node_text(data: bytes, node: Any) -> str:
    return data[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _identifiers(data: bytes, node: Any) -> list[str]:
    return [_node_text(data, n) for n in _walk(node) if n.type in _IDENTIFIER_NODES]


def _signature(data: bytes, node: Any) -> str:
    """The declaration up to its body, literals masked and comments dropped, so a default value, an annotation's string or a
    trailing comment stays out."""
    body = node.child_by_field_name("body")
    end = body.start_byte if body is not None else node.end_byte
    pieces: list[bytes] = []
    cursor = node.start_byte
    for child in _walk(node):
        if child.type in _LITERAL_NODES | _COMMENT_NODES and child.start_byte >= cursor and child.end_byte <= end:
            pieces += [data[cursor:child.start_byte], _MASK.encode("utf-8") if child.type in _LITERAL_NODES else b""]
            cursor = child.end_byte
    pieces.append(data[cursor:end])
    text = " ".join(b"".join(pieces).decode("utf-8", "replace").split()).rstrip(":{ ")
    return text[:MAX_SIGNATURE_CHARS]


def _parse_code(path: str, data: bytes, text: str, file_hash: str, modified: int | None, language: str, scopes: dict[str, str]) -> ParsedFile:
    root = _parsers(language).parse(data).root_node
    records: list[IndexRecord] = []
    imports: list[str] = []
    file_words: list[str] = [path]

    def visit(node: Any, owner: tuple[str, ...]) -> None:
        for child in node.children:
            if child.type in _IMPORT_NODES:
                module = child.child_by_field_name("module_name")
                named = [module] if module is not None else [n for n in child.named_children if n.type in _IMPORTED_NAME_NODES]
                imports.extend(_node_text(data, n) for n in named)
                continue
            kind = scopes.get(child.type)
            if kind is None:
                visit(child, owner)
                continue
            name_node = child.child_by_field_name("name")
            name = _node_text(data, name_node) if name_node is not None else "<anonymous>"
            qualified = (*owner, name)
            symbol = ".".join(qualified)
            file_words.append(name)
            start, end = child.start_point[0] + 1, child.end_point[0] + 1
            signature = _signature(data, child)
            description = f"{kind} {symbol} in {path}, lines {start}-{end}"
            records.append(IndexRecord(
                id=_record_id("symbol", path, file_hash, len(records) + 1, symbol), kind="symbol", path=path, path_id=path_id(path), file_hash=file_hash,
                language=language, terms=split_terms([path, *_identifiers(data, child)]), symbol=symbol[:256], signature=signature,
                description=description[:2048], start_line=start, end_line=end, modified=modified,
                # A container's body would repeat its members, which embed on their own: its names are enough, and far cheaper.
                embed_text=(f"{path}\n{signature}\n" + (" ".join(sorted(set(_identifiers(data, child)))) if kind in _CONTAINERS else _node_text(data, child)))[:MAX_EMBED_CHARS],
            ))
            body = child.child_by_field_name("body")
            if body is not None:
                visit(body, qualified)

    visit(root, ())
    unique_imports = sorted(set(imports))[:MAX_IMPORTS]
    described = "imports: " + " ".join(unique_imports) if unique_imports else None
    file_record = _file_record(path, file_hash, language, modified, split_terms(file_words), described[:2048] if described else None)
    lines = sum(1 for line in text.splitlines() if line.strip())
    return ParsedFile(file_hash, language, lines, (file_record, *records), parse_errors=root.has_error)


def _parse_document(path: str, text: str, file_hash: str, modified: int | None, language: str) -> ParsedFile:
    """Documentation prose may persist; a code block keeps only its pointer, terms and vector (Option A). Whatever may be code counts
    as code, so unusual layout loses prose rather than keeping a body: indented blocks, literal blocks and directives, doctests, inline
    spans and HTML blocks as well as fences. Only Markdown has a form of indented text that is common enough to spare."""
    records: list[IndexRecord] = []
    heading, start, prose, code, line_number = "", 1, [], [], 0  # type: tuple[str, int, list[str], list[str], int]
    fence: tuple[str, int] | None = None
    indented = _INDENTED_MARKDOWN if language == "markdown" and not path.lower().endswith(".rst") else _INDENTED_ANY

    def without_inline_code(text_with_spans: str) -> str:
        def keep(match: re.Match[str]) -> str:
            code.append(match.group(0))
            return " "

        return _STRAY_BACKTICK.sub(keep, _INLINE_CODE.sub(keep, text_with_spans))

    def flush(end: int) -> None:
        body = without_inline_code("\n".join(prose)).strip()
        block = "\n".join(code)
        if not body and not block:
            return
        for piece_number, offset in enumerate(range(0, max(len(body), 1), MAX_PROSE_CHARS)):
            piece = body[offset:offset + MAX_PROSE_CHARS]
            words = [path, heading, piece, _CODE_LITERAL.sub(" ", block)]  # a code block's names, not its strings or comments
            records.append(IndexRecord(
                id=_record_id("section", path, file_hash, len(records) + 1, f"{heading}\0{piece_number}"), kind="section", path=path, path_id=path_id(path),
                file_hash=file_hash, language=language, terms=split_terms(words), symbol=heading[:256] or None, prose=piece or None,
                description=f"section in {path}, lines {start}-{end}" + (", with code" if block else ""), start_line=start, end_line=end, modified=modified,
                embed_text=f"{path}\n{heading}\n{piece}\n{block}"[:MAX_EMBED_CHARS],
            ))

    for line_number, line in enumerate(text.splitlines(), start=1):
        marker = _FENCE.match(line)
        if fence is not None:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= fence[1] and not marker.group(2).strip():
                fence = None
            else:
                code.append(line)
            continue
        if marker and not (marker.group(1)[0] == "`" and "`" in marker.group(2)):
            fence = (marker.group(1)[0], len(marker.group(1)))
            continue
        if indented.match(line) or _CODE_LINE.match(line):
            code.append(line)
            continue
        match = _HEADING.match(line) if language == "markdown" else None
        if match:
            flush(line_number - 1)
            prose, code = [], []
            heading, start = without_inline_code(match.group(2)).strip(), line_number
            continue
        prose.append(line)
    flush(line_number)
    file_record = _file_record(path, file_hash, language, modified, split_terms([path]), None)
    lines = sum(1 for line in text.splitlines() if line.strip())
    return ParsedFile(file_hash, language, lines, (file_record, *records))
