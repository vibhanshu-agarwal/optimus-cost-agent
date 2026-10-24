from __future__ import annotations

import json
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

_READ_DIRECTIVE = re.compile(r"^READ\s+(\S+)\s*$")
_WRITE_DIRECTIVE = re.compile(r"^WRITE\s+(\S+)\s*$")
_EDIT_PREFIX = re.compile(r"^EDIT(?:\s|$)")
_EDIT_DIRECTIVE = re.compile(r"^EDIT\s+(\S+)(?:\s+base_sha256=(\S*))?\s*$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_CR_LF = re.compile(r"\r\n|\n|\r")
_CR_LF_LINE = re.compile(r"[^\r\n]*(?:\r\n|\n|\r)|[^\r\n]+\Z")
# Reserved whole lines that delimit EDIT blocks (#407). A bare "=======" would collide with RST headings.
EDIT_OLD_MARKER = "<<<<<<< OLD"
EDIT_NEW_MARKER = "======= NEW"
EDIT_END_MARKER = ">>>>>>> END"
_EDIT_MARKERS = frozenset({EDIT_OLD_MARKER, EDIT_NEW_MARKER, EDIT_END_MARKER})
_TEST_DIRECTIVE = re.compile(r"^TEST\s+(.+)$")
_MCP_LIST_DIRECTIVE = re.compile(r"^MCP_LIST\s+(\S+)\s*$")
_MCP_CALL_DIRECTIVE = re.compile(r"^MCP_CALL\s+(\S+)\s+(\S+)\s+(\{.*\})\s*$")
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
    directives = _parse_plan_lines(_unwrap_markdown_code_fence(plan_text).splitlines(), edit_base=edit_base)
    if isinstance(directives.write, AgentEditDirective):
        # EDIT lines are exact: only CR, LF and CRLF end them, where str.splitlines also breaks on U+2028, VT,
        # FF and others. A WRITE plan keeps the split it has always had.
        unwrapped = _unwrap_markdown_code_fence(plan_text, split=_split_cr_lf)
        directives = _parse_plan_lines(_split_cr_lf(unwrapped), edit_base=edit_base)
    return directives


def _parse_plan_lines(lines: list[str], *, edit_base: EditBase) -> AgentPlanDirectives:
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
            write = AgentWriteDirective(path=path, content="\n".join(content_lines))
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


def _split_cr_lf(text: str) -> list[str]:
    """``str.splitlines()`` without its extra boundaries: only CRLF, LF and CR end a line."""
    lines = _CR_LF.split(text)
    if lines[-1] == "":
        lines.pop()
    return lines


def _unwrap_markdown_code_fence(plan_text: str, *, split: Callable[[str], list[str]] = str.splitlines) -> str:
    stripped = plan_text.strip()
    if not stripped.startswith("```"):
        return plan_text
    lines = split(stripped)
    if len(lines) < 2:
        return plan_text
    closing_index = len(lines) - 1
    while closing_index > 0 and not lines[closing_index].strip().startswith("```"):
        closing_index -= 1
    if closing_index == 0:
        return plan_text
    return "\n".join(lines[1:closing_index])


def _normalize_directive_line(line: str) -> str:
    normalized = line.strip()
    while True:
        for prefix in ("- ", "* ", "+ "):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].lstrip()
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
