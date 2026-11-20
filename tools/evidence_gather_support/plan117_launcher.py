"""Render Plan 11.7 launchers and define their path-independent public identity."""

from __future__ import annotations

import hashlib
from pathlib import Path

MODULE_CLOSURE_SCHEMA = "plan-11-7-v5-module-closure-report-v1"

_LAUNCHER_TEMPLATE = '''"""Plan 11.7 v5 throwaway isolated launcher (Task 0 source only; never production)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

_SOURCE = Path({source!r}).resolve()
_REPORT = Path({report!r})
sys.path.insert(0, str(_SOURCE / "src"))


def _write_module_closure_report() -> None:
    entries = []
    failures = []
    for name, module in sorted(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        try:
            Path(module_file).resolve().relative_to(_SOURCE)
        except ValueError:
            continue  # outside the isolated source root: not part of the closure
        try:
            resolved = Path(module_file).resolve(strict=True)
            relative = resolved.relative_to(_SOURCE)
            payload = resolved.read_bytes()
        except (OSError, ValueError):
            failures.append(name)  # in-root but not inspectable: the closure is incomplete
            continue
        entries.append({{"module_name": name, "resolved_path": str(resolved), "source_relative_path": relative.as_posix(),
                         "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}})
    report = {{"schema": {schema!r}, "pid": os.getpid(), "monotonic_ns": time.monotonic_ns(),
               "entrypoint_module": "optimus.acp.__main__", "source_root": str(_SOURCE), "entries": entries, "inspection_failures": failures}}
    partial = _REPORT.with_name(_REPORT.name + ".partial")
    partial.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    os.replace(partial, _REPORT)


def _install_module_closure_hook() -> None:
    from optimus.acp.server import AcpStreamServer

    reported = []

    def wrap(original):
        async def serve_with_report(self, *args, **kwargs):
            if not reported:
                reported.append(True)
                _write_module_closure_report()
            return await original(self, *args, **kwargs)

        return serve_with_report

    AcpStreamServer.serve = wrap(AcpStreamServer.serve)
    AcpStreamServer.serve_ndjson = wrap(AcpStreamServer.serve_ndjson)


_install_module_closure_hook()

from optimus.acp.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
'''


def render_launcher_bytes(source_root: Path, report_path: Path) -> bytes:
    """A launcher whose hook reports the in-root module closure before the server reads stdin."""
    return _LAUNCHER_TEMPLATE.format(source=str(source_root), report=str(report_path), schema=MODULE_CLOSURE_SCHEMA).encode("utf-8")


_PUBLIC_LAUNCHER = render_launcher_bytes(Path("ISOLATED_SOURCE"), Path("MODULE_CLOSURE_REPORT"))
PUBLIC_LAUNCHER_IDENTITY = (hashlib.sha256(_PUBLIC_LAUNCHER).hexdigest(), len(_PUBLIC_LAUNCHER))
