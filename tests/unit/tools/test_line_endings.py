"""#410: Agent-mode WRITE keeps the target's line endings, final newline and BOM, byte for byte (design v3, R3-R6).

Every assertion is on bytes, so each case means the same on Windows and Linux.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.tools.line_endings import WRITE_LINE_ENDINGS_MIXED, fit_body_to_file, line_ending_style
from optimus.tools.mutation_tools import WriteRefused, write_file, write_file_keeping_line_endings

BOM = "﻿"
BOM_BYTES = b"\xef\xbb\xbf"


def _approved() -> RuntimeContext:
    return RuntimeContext(
        execution_mode=ExecutionMode.AGENT, state=AgentState.EXECUTING, approval_granted=True, user_approval_id="approval-1"
    )


@pytest.mark.parametrize(
    ("data", "style"),
    [
        (b"a\r\nb\r\n", "crlf"),
        (b"a\nb\n", "lf"),
        (b"", "none"),
        (b"abc", "none"),
        (BOM_BYTES, "none"),
        (b"a\r\nb\n", "mixed"),
        (b"a\rb", "mixed"),
        (b"a\r\nb\r", "mixed"),
    ],
)
def test_the_style_comes_from_the_bytes(data: bytes, style: str) -> None:
    assert line_ending_style(data) == style


@pytest.mark.parametrize(
    ("existing", "body", "expected"),
    [
        (b"a\r\nb\r\n", "A\nb", "A\r\nb\r\n"),  # #387: the reply ends without a newline
        (b"a\r\nb\r\n", "A\nb\n", "A\r\nb\r\n"),
        (b"a\r\nb\r\n", "A\r\nb\r\n", "A\r\nb\r\n"),
        (b"x", "y\n\n", "y\n"),  # the last terminator goes, none is appended: line y, then an empty last line
        (b"x\n", "y", "y\n"),
        (b"x", "y\n", "y"),
        (b"x\n", "", ""),  # emptying a file gives zero bytes
        (b"x", "", ""),
        (b"\n", "\n", "\n"),  # a newline-only replacement survives (round 49, correction 1)
        (b"\r\n", "\n", "\r\n"),
        (b"a\nb\n", "A\n\nb", "A\n\nb\n"),  # earlier empty lines are content
        (b"a\r\n", "x\ry", "x\ry\r\n"),  # a lone CR in the body is content
        (b"one line", "two\nlines", "two\nlines"),  # no terminator: LF
    ],
)
def test_an_existing_file_keeps_its_style_and_final_newline(existing: bytes, body: str, expected: str) -> None:
    assert fit_body_to_file(body, existing) == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [("y", "y"), ("y\n", "y\n"), ("a\r\nb", "a\nb"), ("", ""), (BOM + "y", BOM + "y")],
)
def test_a_new_file_is_lf_and_ends_as_the_body_does(body: str, expected: str) -> None:
    assert fit_body_to_file(body, None) == expected


@pytest.mark.parametrize(
    ("existing", "body", "expected"),
    [
        (BOM_BYTES + b"a\n", "b", BOM + "b\n"),
        (BOM_BYTES, "", BOM),  # an existing BOM survives an otherwise empty replacement
        (BOM_BYTES + b"a\n", BOM + "b", BOM + "b\n"),  # a supplied BOM is not doubled
        (BOM_BYTES + b"\n", "\n", BOM + "\n"),
        (b"a\n", BOM + "b", BOM + "b\n"),  # a supplied U+FEFF is content
    ],
)
def test_the_bom_rules(existing: bytes, body: str, expected: str) -> None:
    assert fit_body_to_file(body, existing) == expected


@pytest.mark.parametrize("separator", ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "])
def test_other_separators_are_content(separator: str) -> None:
    assert fit_body_to_file(f"x{separator}y", b"a\r\n") == f"x{separator}y\r\n"


def test_a_mixed_file_is_never_fitted() -> None:
    with pytest.raises(ValueError):
        fit_body_to_file("y", b"a\r\nb\n")


def test_the_shared_write_is_exact(tmp_path: Path) -> None:
    """R6: no platform translation, for both callers of the primitive."""
    target = tmp_path / "exact.txt"
    write_file(target, "a\nb\r\nc", context=_approved(), guard=PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=()))
    assert target.read_bytes() == b"a\nb\r\nc"


def test_the_agent_write_fits_the_crlf_seed_byte_for_byte(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_bytes(b"# greeting\r\nprint('hello world')\r\n")
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())

    write_file_keeping_line_endings(target, "# hello optimus\nprint('hello world')", context=_approved(), guard=guard)

    assert target.read_bytes() == b"# hello optimus\r\nprint('hello world')\r\n"


def test_a_new_agent_file_is_lf(tmp_path: Path) -> None:
    target = tmp_path / "new.py"
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())

    write_file_keeping_line_endings(target, "a\r\nb\n", context=_approved(), guard=guard)

    assert target.read_bytes() == b"a\nb\n"


def test_a_mixed_target_is_refused_and_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "mixed.py"
    target.write_bytes(b"a\r\nb\n")
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())

    with pytest.raises(WriteRefused) as refused:
        write_file_keeping_line_endings(target, "z\n", context=_approved(), guard=guard)

    assert refused.value.code == WRITE_LINE_ENDINGS_MIXED
    assert target.read_bytes() == b"a\r\nb\n"


def test_a_denied_write_never_reads_the_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Round 48: the gate and the guard run before any metadata or bytes of the target are read."""
    target = tmp_path / "secret.py"
    target.write_bytes(b"a\r\n")
    reads: list[Path] = []
    original = Path.read_bytes

    def recording(self: Path) -> bytes:
        reads.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", recording)
    plan_mode = RuntimeContext(execution_mode=ExecutionMode.PLAN, state=AgentState.CHAT_ONLY)

    with pytest.raises(MutationForbidden):
        write_file_keeping_line_endings(target, "z", context=plan_mode)

    assert reads == []
    assert original(target) == b"a\r\n"
