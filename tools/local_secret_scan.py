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
4. otherwise delegates the original arguments to ``detect_secrets.pre_commit_hook.main``, in their
   original order, and returns its status (0 clean, 1 findings, 3 baseline maintenance) as-is.

The one argument it drops is a byte-identical archive move (docs archive convention, 2026-09-29):
a file moved from a ``docs/`` folder into the ``archive/`` beside it (the destination is the source
path with one ``archive`` folder inserted) without changing a byte, which Git reports as a staged
R100 rename with identical blob ids. Frozen documents cannot take inline allowlist pragmas, so
without this they could never be archived. Every other move, any changed byte and any copy is
scanned as before. If Git fails, or its output cannot be parsed exactly, nothing is dropped.

It does not enumerate directories, convert encodings, or decode with replacement characters. The
literal ``src`` argument that the configured entry carries is a compatibility marker for the
scanner's positional interface: it is validated as an existing directory and passed through, never
scanned recursively by this adapter (pre-commit supplies the selected filenames).
"""

from __future__ import annotations

import codecs
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path, PurePath, PurePosixPath

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


ARCHIVE_ROOT = "docs"
ARCHIVE_DIRNAME = "archive"
_HEX = frozenset("0123456789abcdef")
_OCTAL = frozenset("01234567")


def _is_archive_move(old: str, new: str) -> bool:
    """``new`` is ``old`` with exactly one ``archive`` folder inserted, below ``docs/``."""
    old_parts, new_parts = PurePosixPath(old).parts, PurePosixPath(new).parts
    if len(new_parts) != len(old_parts) + 1 or not old_parts or old_parts[0] != ARCHIVE_ROOT:
        return False
    return any(
        new_parts[index] == ARCHIVE_DIRNAME
        and new_parts[:index] == old_parts[:index]
        and new_parts[index + 1 :] == old_parts[index:]
        for index in range(1, len(old_parts))
    )


def _is_identical_rename(meta: bytes) -> bool:
    """``:<mode> <mode> <blob> <blob> R100`` with two equal, non-null, full-length blob ids."""
    if not meta.startswith(b":"):
        return False
    fields = meta[1:].decode("ascii", errors="replace").split(" ")
    if len(fields) != 5 or fields[4] != "R100":
        return False
    old_mode, new_mode, old_blob, new_blob, _status = fields
    modes_ok = all(len(mode) == 6 and set(mode) <= _OCTAL for mode in (old_mode, new_mode))
    blob_ok = len(new_blob) in (40, 64) and set(new_blob) <= _HEX and set(new_blob) != {"0"}
    return modes_ok and blob_ok and old_blob == new_blob


def _byte_identical_archive_moves() -> frozenset[str]:
    """Destination paths of staged byte-identical archive moves; empty unless Git says so exactly."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--raw", "-z", "--no-abbrev", "-M100%", "--diff-filter=R"],
            capture_output=True,
            check=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    fields = result.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 3:
        return frozenset()  # not whole records: parse nothing rather than guess
    moves: set[str] = set()
    for index in range(0, len(fields), 3):
        meta, old_raw, new_raw = fields[index : index + 3]
        try:
            old, new = old_raw.decode("utf-8"), new_raw.decode("utf-8")
        except UnicodeDecodeError:
            return frozenset()
        if _is_identical_rename(meta) and _is_archive_move(old, new):
            moves.add(new)
    return frozenset(moves)


def _without_identical_moves(argv: Sequence[str], candidates: Sequence[str]) -> list[str]:
    moves = _byte_identical_archive_moves()
    dropped = {
        candidate
        for candidate in candidates
        if candidate != DIRECTORY_MARKER and PurePath(candidate).as_posix() in moves
    }
    return [token for token in argv if token not in dropped]


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
    return delegate(_without_identical_moves(argv, candidates))


def main(argv: list[str] | None = None) -> int:
    return run(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
