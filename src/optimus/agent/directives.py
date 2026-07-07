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
    lines = plan_text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
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
                raise AgentDirectiveParseError("no valid agent directives")
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
    return (
        _READ_DIRECTIVE.match(line) is not None
        or _WRITE_DIRECTIVE.match(line) is not None
        or _TEST_DIRECTIVE.match(line) is not None
    )


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
