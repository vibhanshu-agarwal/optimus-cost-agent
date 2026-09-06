"""Local secret-scan adapter: strict UTF-8 validation before delegating to the pinned detect-secrets hook.

Why this exists (local-hook UTF-8 repair, 2026-09-06): the pinned ``detect_secrets`` file reader
opens files in the process locale and silently yields no lines on ``UnicodeDecodeError``. Under the
Windows CP1252 default a valid UTF-8 file containing a code point outside CP1252 is skipped entirely,
and in UTF-8 mode an invalid-UTF-8 file is skipped entirely (CP1252 can read byte FF; the failure
depends on the decoding mode), so the hook can pass a file it never read. This adapter

1. requires the interpreter to run in UTF-8 mode (the configured entry passes ``-X utf8``),
2. strictly decodes the baseline and every selected file as UTF-8, whole file, in chunks,
3. rejects with status 2 and a path/offset/reason diagnostic before the scanner is imported or the
   baseline can be touched, and
4. otherwise delegates the *original* arguments, unchanged, to ``detect_secrets.pre_commit_hook.main``
   and returns its status (0 clean, 1 findings, 3 baseline maintenance) as-is.

It does not enumerate directories, convert encodings, or decode with replacement characters. The
literal ``src`` argument that the configured entry carries is a compatibility marker for the
scanner's positional interface: it is validated as an existing directory and passed through, never
scanned recursively by this adapter (pre-commit supplies the selected filenames).
"""

from __future__ import annotations

import codecs
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

CHUNK_BYTES = 64 * 1024
STATUS_VALIDATION_FAILED = 2
DIRECTORY_MARKER = "src"
PROGRAM = "local-secret-scan"


class ValidationError(Exception):
    """A selected input could not be validated; carries the user-facing diagnostic."""


def _utf8_mode_enabled() -> bool:
    return bool(sys.flags.utf8_mode)


def _delegate(argv: list[str]) -> int:
    """Import the pinned scanner only after validation succeeded."""
    from detect_secrets.pre_commit_hook import main as hook_main

    result = hook_main(argv)
    return int(result or 0)


def _parse(argv: Sequence[str]) -> tuple[str, list[str]]:
    """Return (baseline path, candidate arguments) without reordering anything.

    Only ``--baseline <path>`` is recognised as an option. Any other option-shaped argument is
    rejected: the adapter is a fixed configured entry, not a general command line.
    """
    baseline: str | None = None
    candidates: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--baseline":
            if baseline is not None or index + 1 >= len(argv):
                raise ValidationError("malformed arguments: --baseline must appear once and take a path")
            baseline = argv[index + 1]
            index += 2
            continue
        if token.startswith("-"):
            raise ValidationError(f"malformed arguments: unsupported option {token!r}")
        candidates.append(token)
        index += 1
    if baseline is None:
        raise ValidationError("malformed arguments: --baseline <path> is required")
    return baseline, candidates


def _validate_utf8_file(path: str) -> None:
    """Strictly decode the whole file as UTF-8, chunk by chunk, reporting the first bad offset."""
    file_path = Path(path)
    if file_path.is_dir():
        raise ValidationError(f"unexpected directory argument: {path}")
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    consumed = 0
    try:
        with open(file_path, "rb") as handle:
            while True:
                chunk = handle.read(CHUNK_BYTES)
                if not chunk:
                    break
                # The incremental decoder prepends bytes it buffered from the previous chunk (an
                # incomplete multi-byte sequence) to this chunk, and ``exc.start`` is relative to that
                # combined input; the file offset is therefore anchored at ``consumed - buffered``.
                buffered_before = len(decoder.getstate()[0])
                try:
                    decoder.decode(chunk, final=False)
                except UnicodeDecodeError as exc:
                    raise ValidationError(
                        f"cannot decode {path} as UTF-8 at byte offset {consumed - buffered_before + exc.start}: {exc.reason}"
                    ) from None
                consumed += len(chunk)
            buffered_at_eof = len(decoder.getstate()[0])
            try:
                decoder.decode(b"", final=True)
            except UnicodeDecodeError as exc:
                raise ValidationError(
                    f"cannot decode {path} as UTF-8 at byte offset {consumed - buffered_at_eof + exc.start}: {exc.reason}"
                ) from None
    except FileNotFoundError:
        raise ValidationError(f"cannot read {path}: file not found") from None
    except IsADirectoryError:
        raise ValidationError(f"unexpected directory argument: {path}") from None
    except PermissionError as exc:
        raise ValidationError(f"cannot read {path}: permission denied ({exc.strerror})") from None
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc.strerror or exc}") from None


def _validate(baseline: str, candidates: Sequence[str]) -> None:
    _validate_utf8_file(baseline)
    for candidate in candidates:
        if candidate == DIRECTORY_MARKER:
            if not os.path.isdir(candidate):
                raise ValidationError(f"expected the compatibility directory marker {DIRECTORY_MARKER!r} to be an existing directory")
            continue
        _validate_utf8_file(candidate)


def run(argv: Sequence[str], *, delegate: Callable[[list[str]], int] = _delegate, stderr=None) -> int:
    err = stderr or sys.stderr
    if not _utf8_mode_enabled():
        print(
            f"{PROGRAM}: the interpreter is not in UTF-8 mode; invoke as 'python -X utf8 tools/local_secret_scan.py ...'",
            file=err,
        )
        return STATUS_VALIDATION_FAILED
    try:
        baseline, candidates = _parse(argv)
        _validate(baseline, candidates)
    except ValidationError as exc:
        print(f"{PROGRAM}: {exc}", file=err)
        return STATUS_VALIDATION_FAILED
    return delegate(list(argv))


def main(argv: list[str] | None = None) -> int:
    return run(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
