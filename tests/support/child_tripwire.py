"""Tripwire for a child process that a test launches: did it reach the real known-folder adapter?

Test support only. A test adds `PRELUDE` as the first line of the child's own program and passes
`environment(...)` to the launch it already makes. In the child, `install()` runs before any product
import. It replaces the product's real Windows known-folder adapter, as soon as that module is
imported, with a function that records the call and raises: the real folders are never resolved.

The parent reads the result with `observed()`. A result is trusted only if the child recorded that
the tripwire loaded, and loaded before the trusted-path module was imported. Records hold event
names and a process ID only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

FILE_VARIABLE = "OPTIMUS_TEST_CHILD_TRIPWIRE_FILE"
PRELUDE = "import tests.support.child_tripwire as _child_tripwire; _child_tripwire.install()\n"
REFUSAL = "TEST_CHILD_TRIPWIRE_REAL_ADAPTER"
_TARGET = "optimus.acp.trusted_paths"


def environment(base: dict[str, str], record: Path) -> dict[str, str]:
    """The launch environment the test already built, plus where the child records."""
    return {**base, FILE_VARIABLE: str(record)}


def observed(record: Path) -> dict[str, object]:
    """What the child recorded: whether the tripwire loaded in time, and every real-adapter call."""
    events = [json.loads(line)["event"] for line in record.read_text(encoding="utf-8").splitlines()] if record.is_file() else []
    return {
        "loaded": events.count("loaded"),
        "loaded_after_product_import": events.count("loaded_after_product_import"),
        "trusted_paths_imported": "trusted_paths_imported" in events,
        "real_adapter_calls": events.count("real_adapter_call"),
    }


def assert_no_real_adapter_access(record: Path) -> dict[str, object]:
    """Fail unless the tripwire provably loaded first and the child never asked for the real folders."""
    seen = observed(record)
    assert seen["loaded"] == 1 and seen["loaded_after_product_import"] == 0, f"tripwire did not load first: {seen}"
    assert seen["real_adapter_calls"] == 0, f"the child asked for the real known folders: {seen}"
    return seen


def _note(event: str) -> None:
    with open(os.environ[FILE_VARIABLE], "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": event, "pid": os.getpid()}) + "\n")


def _refuse() -> object:
    _note("real_adapter_call")
    raise RuntimeError(REFUSAL)


def _arm(module: object) -> None:
    module._real_windows_known_folders = _refuse  # type: ignore[attr-defined]  # noqa: SLF001
    _note("trusted_paths_imported")


class _Finder:
    """Arms the tripwire at the moment the trusted-path module finishes importing."""

    _busy = False

    def find_spec(self, name: str, path: object = None, target: object = None) -> object:
        if name != _TARGET or self._busy:
            return None
        import importlib.util

        self._busy = True
        try:
            spec = importlib.util.find_spec(name)
        finally:
            self._busy = False
        if spec is None or spec.loader is None:
            return None
        execute = spec.loader.exec_module

        def exec_module(module: object) -> None:
            execute(module)
            _arm(module)

        spec.loader.exec_module = exec_module  # type: ignore[method-assign]
        return spec


def install() -> None:
    """Child side. Fails closed: without a record file the child does not run its program."""
    if FILE_VARIABLE not in os.environ:
        raise RuntimeError("TEST_CHILD_TRIPWIRE_NOT_CONFIGURED")
    if getattr(sys, "_main5_guard_activated", False):
        # The MAIN-5 guard already refuses and records this in the child, and checks its own
        # adapter patch. It is left in force; this tripwire only reports that it ran.
        _note("loaded")
        return
    if _TARGET in sys.modules:
        _arm(sys.modules[_TARGET])
        _note("loaded_after_product_import")
        return
    sys.meta_path.insert(0, _Finder())
    _note("loaded")
