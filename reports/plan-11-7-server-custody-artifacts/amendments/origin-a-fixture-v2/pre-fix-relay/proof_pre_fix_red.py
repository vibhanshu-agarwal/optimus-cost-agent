#!/usr/bin/env python3
"""Prove Task 2 relay read1 regression against an isolated HEAD (pre-fix) copy.

Does not mutate the shared worktree tools/plan117_custody_relay.py.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
PRE_FIX = Path(__file__).resolve().parent / "plan117_custody_relay.py"
WORKTREE = ROOT / "tools" / "plan117_custody_relay.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _source_assertions(label: str, source: str) -> list[str]:
    failures: list[str] = []
    if "parent_in.read(READ_CHUNK)" in source:
        failures.append(f"{label}: blocking parent_in.read(READ_CHUNK) present")
    if "child_stdout.read(READ_CHUNK)" in source:
        failures.append(f"{label}: blocking child_stdout.read(READ_CHUNK) present")
    if "_read_pipe_chunk(parent_in, READ_CHUNK)" not in source:
        failures.append(f"{label}: missing _read_pipe_chunk(parent_in, READ_CHUNK)")
    if "_read_pipe_chunk(child_stdout, READ_CHUNK)" not in source:
        failures.append(f"{label}: missing _read_pipe_chunk(child_stdout, READ_CHUNK)")
    if "read1" not in source:
        failures.append(f"{label}: missing read1 preference")
    return failures


def _prefer_read1_behavior(mod) -> None:
    class _Stream:
        def __init__(self) -> None:
            self.read1_calls = 0
            self.read_calls = 0

        def read1(self, size: int) -> bytes:
            self.read1_calls += 1
            return b"x" * min(size, 3)

        def read(self, size: int) -> bytes:
            self.read_calls += 1
            return b"y" * size

    stream = _Stream()
    if not hasattr(mod, "_read_pipe_chunk"):
        raise AssertionError("pre-fix module has no _read_pipe_chunk helper")
    chunk = mod._read_pipe_chunk(stream, 64)  # type: ignore[arg-type]
    assert chunk == b"xxx", f"expected partial read1 bytes, got {chunk!r}"
    assert stream.read1_calls == 1, f"read1_calls={stream.read1_calls}"
    assert stream.read_calls == 0, f"read_calls={stream.read_calls} (blocking read used)"


def main() -> int:
    pre_source = PRE_FIX.read_text(encoding="utf-8")
    wt_source = WORKTREE.read_text(encoding="utf-8")

    print("=== pre-fix source facts ===")
    print(f"path={PRE_FIX}")
    print(f"bytes={PRE_FIX.stat().st_size}")
    print(f"has_read1={'read1' in pre_source}")
    print(f"has__read_pipe_chunk={'_read_pipe_chunk' in pre_source}")
    print(f"blocking_parent={'parent_in.read(READ_CHUNK)' in pre_source}")
    print(f"blocking_child={'child_stdout.read(READ_CHUNK)' in pre_source}")

    print("\n=== worktree source facts (must already be fixed; not reverted) ===")
    print(f"path={WORKTREE}")
    print(f"has_read1={'read1' in wt_source}")
    print(f"has__read_pipe_chunk={'_read_pipe_chunk' in wt_source}")
    print(f"blocking_parent={'parent_in.read(READ_CHUNK)' in wt_source}")
    print(f"blocking_child={'child_stdout.read(READ_CHUNK)' in wt_source}")

    pre_source_fails = _source_assertions("pre-fix", pre_source)
    wt_source_fails = _source_assertions("worktree", wt_source)
    print("\n=== source assertion results ===")
    print(f"pre_fix_source_failures={len(pre_source_fails)}")
    for item in pre_source_fails:
        print(f"  FAIL: {item}")
    print(f"worktree_source_failures={len(wt_source_fails)}")
    for item in wt_source_fails:
        print(f"  FAIL: {item}")

    print("\n=== behavior: prefer read1 over blocking read ===")
    pre_mod = _load_module(PRE_FIX, "plan117_custody_relay_pre_fix")
    behavior_failed = False
    try:
        _prefer_read1_behavior(pre_mod)
        print("UNEXPECTED PASS against pre-fix module")
    except Exception as exc:  # noqa: BLE001 — proof records exact failure
        behavior_failed = True
        print(f"EXPECTED FAIL against pre-fix: {type(exc).__name__}: {exc}")
        traceback.print_exc()

    wt_mod = _load_module(WORKTREE, "plan117_custody_relay_worktree")
    try:
        _prefer_read1_behavior(wt_mod)
        print("worktree prefer-read1: PASS")
        wt_behavior_ok = True
    except Exception as exc:  # noqa: BLE001
        wt_behavior_ok = False
        print(f"worktree prefer-read1 UNEXPECTED FAIL: {type(exc).__name__}: {exc}")
        traceback.print_exc()

    print("\n=== summary ===")
    red_ok = bool(pre_source_fails) and behavior_failed and not wt_source_fails and wt_behavior_ok
    print(f"pre_fix_red_proven={red_ok}")
    print("shared_worktree_relay_untouched_by_this_proof=True")
    return 0 if red_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
