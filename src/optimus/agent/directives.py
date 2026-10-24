from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

# #410 R1: directive syntax, EDIT's included, is separated by spaces and tabs only.
_READ_DIRECTIVE = re.compile(r"^READ[ \t]+(\S+)[ \t]*$")
_WRITE_DIRECTIVE = re.compile(r"^WRITE[ \t]+(\S+)[ \t]*$")
_EDIT_PREFIX = re.compile(r"^EDIT(?:[ \t]|$)")
_EDIT_DIRECTIVE = re.compile(r"^EDIT[ \t]+(\S+)(?:[ \t]+base_sha256=(\S*))?[ \t]*$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_CR_LF = re.compile(r"\r\n|\n|\r")
_CR_LF_LINE = re.compile(r"[^\r\n]*(?:\r\n|\n|\r)|[^\r\n]+\Z")
# Reserved whole lines that delimit EDIT blocks (#407). A bare "=======" would collide with RST headings.
EDIT_OLD_MARKER = "<<<<<<< OLD"
EDIT_NEW_MARKER = "======= NEW"
EDIT_END_MARKER = ">>>>>>> END"
_EDIT_MARKERS = frozenset({EDIT_OLD_MARKER, EDIT_NEW_MARKER, EDIT_END_MARKER})
_TEST_DIRECTIVE = re.compile(r"^TEST[ \t]+(.+)$")
_MCP_LIST_DIRECTIVE = re.compile(r"^MCP_LIST[ \t]+(\S+)[ \t]*$")
_MCP_CALL_DIRECTIVE = re.compile(r"^MCP_CALL[ \t]+(\S+)[ \t]+(\S+)[ \t]+(\{.*\})[ \t]*$")
_MCP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHELL_METACHARACTERS = re.compile(r"[;|&`$<>]|&&|\|\||\$\(")
_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]|^/")


class AgentDirectiveParseError(ValueError):
    pass


@dataclass(frozen=True)
class AgentWriteDirective:
    path: str
    content: str


@dataclass(frozen=True)
class AgentEditBlock:
    """Whole lines, without terminators: OLD must match the file exactly once; NEW replaces it (#407)."""

    old_lines: tuple[str, ...]
    new_lines: tuple[str, ...]


@dataclass(frozen=True)
class AgentEditDirective:
    path: str
    blocks: tuple[AgentEditBlock, ...]
    # Bound by the harness before approval, never by the model: the sha256 of the evidence the model saw.
    base_sha256: str | None = None


# How a caller treats an EDIT's base: a model's plan must not carry one, a stored (approved) plan must.
EditBase = Literal["forbidden", "required", "any"]


@dataclass(frozen=True)
class AgentPlanDirectives:
    read_paths: tuple[str, ...]
    # The plan's one mutation directive: a whole-file WRITE or an EDIT of an existing file.
    write: AgentWriteDirective | AgentEditDirective | None
    tests: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class AgentMcpListDirective:
    server: str


@dataclass(frozen=True)
class AgentMcpCallDirective:
    server: str
    tool: str
    arguments: dict[str, object]


def parse_canonical_json_object(text: str) -> dict[str, object]:
    """Parse a JSON object that must already be in canonical dump form."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentDirectiveParseError("MCP_CALL arguments must be valid JSON") from exc
    if not isinstance(value, dict):
        raise AgentDirectiveParseError("MCP_CALL arguments must be a JSON object")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if canonical != text:
        raise AgentDirectiveParseError("MCP_CALL arguments must be canonical JSON")
    return value


def validate_mcp_name(name: str, *, label: str) -> str:
    if _MCP_NAME_RE.fullmatch(name) is None:
        raise AgentDirectiveParseError(f"unsafe MCP {label} name")
    return name


def parse_mcp_list_line(line: str) -> AgentMcpListDirective | None:
    match = _MCP_LIST_DIRECTIVE.match(_normalize_directive_line(line))
    if match is None:
        return None
    return AgentMcpListDirective(server=validate_mcp_name(match.group(1), label="server"))


def parse_mcp_call_line(line: str) -> AgentMcpCallDirective | None:
    match = _MCP_CALL_DIRECTIVE.match(_normalize_directive_line(line))
    if match is None:
        return None
    server = validate_mcp_name(match.group(1), label="server")
    tool = validate_mcp_name(match.group(2), label="tool")
    arguments = parse_canonical_json_object(match.group(3))
    return AgentMcpCallDirective(server=server, tool=tool, arguments=arguments)


def parse_agent_plan(plan_text: str, *, edit_base: EditBase = "any") -> AgentPlanDirectives:
    """
    Parses a plan text containing agent directives and translates it into structured
    data. The plan text may contain directives to read files, write content to a specific
    path, edit an existing file, or perform tests with given commands. This function
    validates and organizes the parsed data for further processing.

    :param plan_text: The raw input plan text that contains agent directives.
    :type plan_text: str
    :param edit_base: Whether an EDIT may (``"any"``), must not (``"forbidden"``, a model's
        plan) or must (``"required"``, a stored plan) carry its bound ``base_sha256``.
    :return: An instance of AgentPlanDirectives containing parsed read paths, the one
        mutation directive, and test commands.
    :rtype: AgentPlanDirectives
    :raises AgentDirectiveParseError: If the input contains invalid or improperly
        formatted directives, such as more than one WRITE or EDIT directive, a malformed
        EDIT block, or a lack of any valid directives.
    """
    # EDIT lines are exact: only CR, LF and CRLF end them (#407). So the exact split decides first. Every other plan
    # takes #410's R1 split: LF and CRLF lines that keep their terminators, so a WRITE body keeps its bytes. An EDIT
    # that exists only under that split is not one.
    exact_error: AgentDirectiveParseError | None = None
    try:
        exact = _parse_plan_lines(split_cr_lf(_unwrap_markdown_code_fence(plan_text, exact=True)), edit_base=edit_base, keepends=False)
    except AgentDirectiveParseError as exc:
        exact, exact_error = None, exc
    if exact is not None and isinstance(exact.write, AgentEditDirective):
        return exact
    plan = _parse_plan_lines(plan_lines(_unwrap_markdown_code_fence(plan_text)), edit_base=edit_base, keepends=True)
    if isinstance(plan.write, AgentEditDirective) or _invents_an_edit(plan_text):
        raise exact_error or AgentDirectiveParseError("malformed EDIT directive")
    return plan


def _invents_an_edit(plan_text: str) -> bool:
    """#407: an EDIT header that only `str.splitlines()` sees (it also breaks on U+2028, VT, FF and others), outside
    a WRITE body, makes the plan an error rather than one read some other way, whether or not that EDIT would parse
    or validate (Codex rounds 53-54). WRITE bodies stay opaque, as in the parser: a body ends at the next directive
    line, and an EDIT line is not one."""
    lines = _unwrap_markdown_code_fence(plan_text).splitlines()
    index = 0
    while index < len(lines):
        line = _normalize_directive_line(lines[index])
        if _WRITE_DIRECTIVE.match(line) is not None:
            index += 1
            while index < len(lines) and not _is_directive_line(lines[index]):
                index += 1
            continue
        if _EDIT_PREFIX.match(line) is not None:
            return True
        index += 1
    return False


def _parse_plan_lines(lines: list[str], *, edit_base: EditBase, keepends: bool) -> AgentPlanDirectives:
    """`keepends`: the lines carry their own terminators (#410's R1 split), otherwise they are #407's exact EDIT
    lines without them."""
    read_paths: list[str] = []
    tests: list[tuple[str, ...]] = []
    write: AgentWriteDirective | AgentEditDirective | None = None
    index = 0

    while index < len(lines):
        line = _normalize_directive_line(lines[index])
        if _MCP_LIST_DIRECTIVE.match(line) is not None or _MCP_CALL_DIRECTIVE.match(line) is not None:
            raise AgentDirectiveParseError("MCP directives are not valid in a final mutation plan")
        if lines[index].strip() in _EDIT_MARKERS:
            raise AgentDirectiveParseError("EDIT block marker outside an EDIT directive")

        read_match = _READ_DIRECTIVE.match(line)
        if read_match is not None:
            path = read_match.group(1)
            _validate_relative_path(path)
            read_paths.append(path)
            index += 1
            continue

        write_match = _WRITE_DIRECTIVE.match(line)
        if write_match is not None:
            if isinstance(write, AgentWriteDirective):
                raise AgentDirectiveParseError("multiple WRITE directives are not supported")
            if write is not None:
                raise AgentDirectiveParseError(_ONE_MUTATION)
            path = write_match.group(1)
            _validate_relative_path(path)
            index += 1
            content_lines = []
            while index < len(lines) and not _is_directive_line(lines[index]):
                content_lines.append(lines[index])
                index += 1
            if not keepends:  # an exact EDIT parse: a WRITE here is never returned (the plan is re-parsed)
                write = AgentWriteDirective(path=path, content="\n".join(content_lines))
                continue
            if index < len(lines) and content_lines and content_lines[-1] in ("\n", "\r\n"):
                content_lines.pop()  # #410 R2: one empty line before the next directive separates it from the body
            write = AgentWriteDirective(path=path, content="".join(content_lines))
            continue

        if _EDIT_PREFIX.match(line) is not None:
            if write is not None:
                raise AgentDirectiveParseError(_ONE_MUTATION)
            write, index = _parse_edit(lines, index, edit_base=edit_base)
            continue

        test_match = _TEST_DIRECTIVE.match(line)
        if test_match is not None:
            command = _parse_test_command(test_match.group(1))
            tests.append(command)
            index += 1
            continue

        index += 1

    if not read_paths and write is None and not tests:
        raise AgentDirectiveParseError("no valid agent directives")

    return AgentPlanDirectives(
        read_paths=tuple(read_paths),
        write=write,
        tests=tuple(tests),
    )


_ONE_MUTATION = "a plan may hold at most one WRITE or EDIT directive"


def bind_edit_base(plan_text: str, *, base_sha256: str) -> str:
    """Return the model's plan with its EDIT header bound to ``base_sha256``; every other byte is kept (#407)."""
    if _SHA256_HEX.match(base_sha256) is None:
        raise AgentDirectiveParseError("malformed EDIT base_sha256")
    edit = parse_agent_plan(plan_text, edit_base="forbidden").write
    if not isinstance(edit, AgentEditDirective):
        raise AgentDirectiveParseError("no EDIT directive to bind")
    lines = _CR_LF_LINE.findall(plan_text)
    for index, line in enumerate(lines):
        body = line.rstrip("\r\n")
        match = _EDIT_DIRECTIVE.match(_normalize_directive_line(body))
        if match is not None and match.group(1) == edit.path:
            lines[index] = f"{body.rstrip()} base_sha256={base_sha256}{line[len(body) :]}"
            break
    bound = "".join(lines)
    # The first matching line is the header; the re-parse proves it and that nothing else moved.
    if parse_agent_plan(bound, edit_base="required").write != replace(edit, base_sha256=base_sha256):
        raise AgentDirectiveParseError("EDIT header could not be bound")
    return bound


def _parse_edit(lines: list[str], index: int, *, edit_base: EditBase) -> tuple[AgentEditDirective, int]:
    match = _EDIT_DIRECTIVE.match(_normalize_directive_line(lines[index]))
    if match is None:
        raise AgentDirectiveParseError("malformed EDIT directive")
    path, base = match.group(1), match.group(2)
    _validate_relative_path(path)
    if base is not None and _SHA256_HEX.match(base) is None:
        raise AgentDirectiveParseError("malformed EDIT base_sha256")
    if base is not None and edit_base == "forbidden":
        raise AgentDirectiveParseError("a model's EDIT must not carry base_sha256")
    if base is None and edit_base == "required":
        raise AgentDirectiveParseError("a stored EDIT must carry base_sha256")
    index += 1
    blocks: list[AgentEditBlock] = []
    while True:
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index >= len(lines) or lines[index].strip() != EDIT_OLD_MARKER:
            break
        old_lines, index = _edit_block_lines(lines, index + 1, until=EDIT_NEW_MARKER)
        if not old_lines:
            raise AgentDirectiveParseError("an EDIT block's OLD must not be empty")
        new_lines, index = _edit_block_lines(lines, index + 1, until=EDIT_END_MARKER)
        blocks.append(AgentEditBlock(old_lines=old_lines, new_lines=new_lines))
        index += 1
    if not blocks:
        raise AgentDirectiveParseError("EDIT requires at least one OLD/NEW block")
    return AgentEditDirective(path=path, blocks=tuple(blocks), base_sha256=base), index


def _edit_block_lines(lines: list[str], index: int, *, until: str) -> tuple[tuple[str, ...], int]:
    body: list[str] = []
    while index < len(lines):
        marker = lines[index].strip()
        if marker == until:
            return tuple(body), index
        if marker in _EDIT_MARKERS:
            raise AgentDirectiveParseError("EDIT block markers are out of order")
        body.append(lines[index])
        index += 1
    raise AgentDirectiveParseError("unterminated EDIT block")


def _is_directive_line(line: str) -> bool:
    normalized = _normalize_directive_line(line)
    return (
        _READ_DIRECTIVE.match(normalized) is not None
        or _WRITE_DIRECTIVE.match(normalized) is not None
        or _TEST_DIRECTIVE.match(normalized) is not None
        or _MCP_LIST_DIRECTIVE.match(normalized) is not None
        or _MCP_CALL_DIRECTIVE.match(normalized) is not None
    )


_DIRECTIVE_BLANKS = " \t"  # #410 R1: the only padding stripped around directive syntax
# #410 R1: what `splitlines()` treats as a line break but a plan treats as content. A line holding one is never
# directive syntax, wherever it sits; a CR is content unless it begins a CRLF terminator.
_CONTENT_SEPARATORS = frozenset("\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029")
_REPLY_PADDING = re.compile(r"\A(?:[ \t]|\r?\n)+|(?:[ \t]|\r?\n)+\Z")


def plan_lines(text: str) -> list[str]:
    """#410 R1: lines end at LF only and keep their terminator (a CR before it makes CRLF); every other separator
    that `splitlines()` knows is content, so a WRITE body keeps its bytes. Every plan-line recognizer uses this."""
    *lines, tail = text.split("\n")
    return [line + "\n" for line in lines] + ([tail] if tail else [])


def plan_line_text(line: str) -> str:
    """A plan line without its own LF or CRLF terminator, and without spaces or tabs around it."""
    text = line[:-2] if line.endswith("\r\n") else line.removesuffix("\n")
    return text.strip(_DIRECTIVE_BLANKS)


def directive_text(line: str) -> str:
    """The text directive syntax is matched against: empty, so never a directive, when it holds a content separator."""
    text = plan_line_text(line)
    return "" if _CONTENT_SEPARATORS.intersection(text) else text


def strip_plan_text(text: str) -> str:
    """A reply without leading or trailing spaces, tabs and LF/CRLF breaks; a content separator there survives."""
    return _REPLY_PADDING.sub("", text)


def split_cr_lf(text: str) -> list[str]:
    """``str.splitlines()`` without its extra boundaries: only CRLF, LF and CR end a line (#407's EDIT lines)."""
    lines = _CR_LF.split(text)
    if lines[-1] == "":
        lines.pop()
    return lines


def split_cr_lf_keepends(text: str) -> list[str]:
    """#407's EDIT lines (CRLF, LF or CR ends one), each with its own terminator."""
    return _CR_LF_LINE.findall(text)


def _unwrap_markdown_code_fence(plan_text: str, *, exact: bool = False) -> str:
    """The fenced plan's inner text. `exact` uses #407's EDIT split (CRLF, LF and CR; the inner lines rejoined with
    LF); otherwise #410's R1 split, whose lines keep their own terminators."""
    stripped = plan_text.strip() if exact else strip_plan_text(plan_text)
    if not stripped.startswith("```"):
        return plan_text
    lines = split_cr_lf(stripped) if exact else plan_lines(stripped)
    if len(lines) < 2:
        return plan_text
    closing_index = len(lines) - 1
    while closing_index > 0 and not (lines[closing_index].strip() if exact else plan_line_text(lines[closing_index])).startswith("```"):
        closing_index -= 1
    if closing_index == 0:
        return plan_text
    return "\n".join(lines[1:closing_index]) if exact else "".join(lines[1:closing_index])


def _normalize_directive_line(line: str) -> str:
    normalized = directive_text(line)
    while True:
        for prefix in ("- ", "* ", "+ "):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].lstrip(_DIRECTIVE_BLANKS)
                break
        else:
            return normalized


def _validate_relative_path(path_text: str) -> None:
    if not path_text:
        raise AgentDirectiveParseError("no valid agent directives")
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        raise AgentDirectiveParseError("no valid agent directives")
    if _ABSOLUTE_PATH.match(path_text):
        raise AgentDirectiveParseError("no valid agent directives")


def _parse_test_command(command_text: str) -> tuple[str, ...]:
    if _SHELL_METACHARACTERS.search(command_text):
        raise AgentDirectiveParseError(f"unsafe TEST directive: {command_text}")
    try:
        tokens = tuple(shlex.split(command_text, posix=False))
    except ValueError as exc:
        raise AgentDirectiveParseError(f"unsafe TEST directive: {command_text}") from exc
    if not tokens or tokens[0] != "pytest":
        raise AgentDirectiveParseError(f"unsafe TEST directive: {command_text}")
    for token in tokens[1:]:
        if _SHELL_METACHARACTERS.search(token):
            raise AgentDirectiveParseError(f"unsafe TEST directive: {command_text}")
        if ".." in Path(token).parts or _ABSOLUTE_PATH.match(token):
            raise AgentDirectiveParseError(f"unsafe TEST directive: {command_text}")
    return tokens
