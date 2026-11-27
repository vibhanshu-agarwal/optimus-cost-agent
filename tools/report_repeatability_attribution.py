"""Render repeatability attribution from two supplied files without running probes."""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Never

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]



class UsageError(ValueError):
    """The requested invocation does not match the CLI contract."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise UsageError(message)


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def _destination(path: Path, input_file: Path, manifest_file: Path) -> Path:
    literal = path.absolute()
    if os.path.lexists(literal):
        raise FileExistsError("output directory must be absent")
    destination = literal.parent.resolve(strict=True) / literal.name
    reports = REPOSITORY_ROOT / "reports"
    inputs = (input_file, manifest_file)
    lexical_output = Path(os.path.abspath(literal))
    lexical_roots = (reports, *(Path(os.path.abspath(file)).parent for file in inputs))
    real_roots = (reports.resolve(), *(file.resolve(strict=True).parent for file in inputs))
    if any(lexical_output.is_relative_to(root) for root in lexical_roots) or any(
        destination.is_relative_to(root) for root in real_roots
    ):
        raise PermissionError("output directory is in a protected input or reports tree")
    if os.path.lexists(destination):
        raise FileExistsError("resolved output directory must be absent")
    return destination


def _rename_absent(stage: Path, destination: Path) -> None:
    """Publish on one volume without replacing a racing empty directory."""
    if sys.platform == "win32":
        # Windows rename fails if the destination exists, including an empty directory.
        stage.rename(destination)
        return
    if sys.platform == "linux":
        # Ordinary POSIX rename can replace an empty directory. Linux's flag makes the
        # absence check part of the rename instead of a racy userspace check.
        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, "renameat2", None)
        if rename is not None:
            rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
            rename.restype = ctypes.c_int
            at_fdcwd, rename_noreplace = -100, 1
            if rename(at_fdcwd, os.fsencode(stage), at_fdcwd, os.fsencode(destination), rename_noreplace) == 0:
                return
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    raise OSError(errno.ENOTSUP, "host does not offer supported no-replace directory rename")


def _publish(destination: Path, json_data: bytes, markdown_data: bytes) -> None:
    stage = Path(tempfile.mkdtemp(prefix=".repeatability-stage-", dir=destination.parent))
    try:
        (stage / "composite.json").write_bytes(json_data)
        (stage / "composite.md").write_bytes(markdown_data)
        _rename_absent(stage, destination)
    except OSError:
        if stage.parent == destination.parent and stage.exists():
            # Removal is limited to the staging directory allocated by this invocation.
            shutil.rmtree(stage)
        raise


def main(argv: list[str] | None = None) -> int:
    from tools.plan1126_runtime_audit.composite_repeatability import InputParseError, classify_composite, parse_input
    from tools.plan1126_runtime_audit.composite_report import render_json, render_markdown
    try:
        args = _args(argv)
    except UsageError:
        print("diagnostic_kind=USAGE: supply --input, --manifest and --output-dir", file=sys.stderr)
        return 2
    try:
        payload = args.input.read_bytes()
        manifest = args.manifest.read_bytes()
        parsed = parse_input(payload, manifest)
        result = classify_composite(parsed.observations, parsed.specs)
        buffers = render_json(result, parsed), render_markdown(result, parsed)
        _publish(_destination(args.output_dir, args.input, args.manifest), *buffers)
    except InputParseError as exc:
        print(f"diagnostic_kind=PARSE: {exc}", file=sys.stderr)
        return 2
    except RecursionError:
        print("diagnostic_kind=PARSE: input nesting exceeds supported JSON depth", file=sys.stderr)
        return 2
    except (OSError, RuntimeError):
        print("diagnostic_kind=IO: could not read the inputs or publish the report pair", file=sys.stderr)
        return 1
    if parsed.diagnostics or result.input_validity == "INVALID":
        print("diagnostic_kind=VALIDATION: report retains invalid observations or provenance", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    if __package__ in (None, ""):
        sys.path.insert(0, str(REPOSITORY_ROOT))
    raise SystemExit(main())
