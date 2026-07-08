from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

_READ_DIRECTIVE = re.compile(r"^READ\s+(\S+)\s*$")
_WRITE_DIRECTIVE = re.compile(r"^WRITE\s+(\S+)\s*$")
_TEST_DIRECTIVE = re.compile(r"^TEST\s+(.+)$")
_SHELL_METACHARACTERS = re.compile(r"[;|&`$<>]|&&|\|\||\$\(")
_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]|^/")


class AgentDirectiveParseError(ValueError):
    pass


@dataclass(frozen=True)
class AgentWriteDirective:
    path: str
    content: str


@dataclass(frozen=True)
class AgentPlanDirectives:
    read_paths: tuple[str, ...]
    write: AgentWriteDirective | None
    tests: tuple[tuple[str, ...], ...]


def parse_agent_plan(plan_text: str) -> AgentPlanDirectives:
    read_paths: list[str] = []
    tests: list[tuple[str, ...]] = []
    write: AgentWriteDirective | None = None
    lines = _unwrap_markdown_code_fence(plan_text).splitlines()
    index = 0

    while index < len(lines):
        line = _normalize_directive_line(lines[index])
        read_match = _READ_DIRECTIVE.match(line)
        if read_match is not None:
            path = read_match.group(1)
            _validate_relative_path(path)
            read_paths.append(path)
            index += 1
            continue

        write_match = _WRITE_DIRECTIVE.match(line)
        if write_match is not None:
            if write is not None:
                raise AgentDirectiveParseError("multiple WRITE directives are not supported")
            path = write_match.group(1)
            _validate_relative_path(path)
            index += 1
            content_lines = []
            while index < len(lines) and not _is_directive_line(lines[index]):
                content_lines.append(lines[index])
                index += 1
            write = AgentWriteDirective(path=path, content="\n".join(content_lines))
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


def _is_directive_line(line: str) -> bool:
    normalized = _normalize_directive_line(line)
    return (
        _READ_DIRECTIVE.match(normalized) is not None
        or _WRITE_DIRECTIVE.match(normalized) is not None
        or _TEST_DIRECTIVE.match(normalized) is not None
    )


def _unwrap_markdown_code_fence(plan_text: str) -> str:
    stripped = plan_text.strip()
    if not stripped.startswith("```"):
        return plan_text
    lines = stripped.splitlines()
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
