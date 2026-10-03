"""Local secret-scan adapter: strict UTF-8 validation before delegating to the pinned detect-secrets hook.

Why this exists (local-hook UTF-8 repair, 2026-09-06): the pinned ``detect_secrets`` file reader
opens files in the process locale and silently yields no lines on ``UnicodeDecodeError``. Under the
Windows CP1252 default a valid UTF-8 file containing a code point outside CP1252 is skipped entirely,
and in UTF-8 mode an invalid-UTF-8 file is skipped entirely (CP1252 can read byte FF; the failure
depends on the decoding mode), so the hook can pass a file it never read. This adapter

1. requires the interpreter to run in UTF-8 mode (the configured entry passes ``-X utf8``),
2. strictly decodes the baseline and every selected file, whole file, in chunks: as UTF-16 when the
   file starts with a UTF-16 byte-order mark (the frozen Plan 11.7 custody transcripts; scanner
   decoding repair, 2026-10-03), as UTF-8 otherwise,
3. rejects with status 2 and a path/offset/reason diagnostic before the scanner is imported or the
   baseline can be touched, and
4. otherwise delegates the original arguments to ``detect_secrets.pre_commit_hook.main``, in their
   original order, and returns its status (0 clean, 1 findings, 3 baseline maintenance) as-is. The
   scanner's file reader is wrapped so that a BOM-marked UTF-16 file is read as UTF-16, under its
   own path and without touching its bytes, so plugins, filters and baseline identities see the
   same file they always did; every other file is read by the pinned reader exactly as before.

The one argument it drops is a byte-identical archive move (docs archive convention, 2026-09-29):
a regular file moved from a ``docs/`` folder into the ``archive/`` beside it (the destination is
the not-yet-archived source path with one ``archive`` folder inserted) without changing a byte or
its mode, which Git reports as a staged R100 rename with identical blob ids. Frozen documents
cannot take inline allowlist pragmas, so without this they could never be archived. Every other
move, any changed byte and any copy is scanned as before. If Git fails, or any part of its output
is not exactly what these flags produce, nothing is dropped.

It does not enumerate directories, rewrite or re-encode any file on disk, or decode with
replacement characters. A UTF-16 file without a byte-order mark is not recognised as UTF-16: it is
validated as UTF-8 like any other selected file. The literal ``src`` argument that the configured
entry carries is a compatibility marker for the scanner's positional interface: it is validated as
an existing directory and passed through, never scanned recursively by this adapter (pre-commit
supplies the selected filenames).
"""

from __future__ import annotations

import codecs
import os
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path, PurePath
from typing import IO

CHUNK_BYTES = 64 * 1024
STATUS_VALIDATION_FAILED = 2
DIRECTORY_MARKER = "src"
PROGRAM = "local-secret-scan"
UTF16_BOMS = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
_ENCODING_LABELS = {"utf-8": "UTF-8", "utf-16": "UTF-16"}

LineReader = Callable[[str], Iterator[list[str]]]


class ValidationError(Exception):
    """A selected input could not be validated; carries the user-facing diagnostic."""


def _utf8_mode_enabled() -> bool:
    return bool(sys.flags.utf8_mode)


def _delegate(argv: list[str]) -> int:
    """Import the pinned scanner only after validation succeeded, reading UTF-16 reports as UTF-16."""
    from detect_secrets.core import scan
    from detect_secrets.pre_commit_hook import main as hook_main

    if not hasattr(scan._get_lines_from_file, "pinned"):
        scan._get_lines_from_file = _utf16_aware_reader(scan._get_lines_from_file)
    result = hook_main(argv)
    return int(result or 0)


def _encoding_of(handle: IO[bytes]) -> str:
    """``utf-16`` for a file that starts with a UTF-16 byte-order mark, ``utf-8`` otherwise; rewinds."""
    marker = handle.read(len(UTF16_BOMS[0]))
    handle.seek(0)
    return "utf-16" if marker in UTF16_BOMS else "utf-8"


def _utf16_aware_reader(pinned: LineReader) -> LineReader:
    """Wrap the pinned scanner's file reader so a BOM-marked UTF-16 file is read as UTF-16.

    Every other file goes to the pinned reader untouched. The UTF-16 branch mirrors the pinned
    reader of detect-secrets 1.5.0 (``detect_secrets.core.scan._get_lines_from_file``: the file's
    transformer, else its lines, then the eager transformers) and differs in two ways only: the
    codec, and failing closed where the pinned reader silently yields nothing for a file it cannot
    decode. Validation already proved the file decodes; this guards the window in between.
    """
    from detect_secrets.transformers import get_transformed_file

    def _lines_from_file(filename: str) -> Iterator[list[str]]:
        with open(filename, "rb") as raw:
            encoding = _encoding_of(raw)
        if encoding != "utf-16":
            yield from pinned(filename)
            return
        try:
            with open(filename, encoding="utf-16", errors="strict") as handle:
                yield get_transformed_file(handle) or handle.readlines()
                handle.seek(0)
                lines = get_transformed_file(handle, use_eager_transformers=True)
                if lines:
                    yield lines
        except UnicodeDecodeError as exc:
            raise ValidationError(f"cannot decode {filename} as UTF-16 while scanning it: {exc.reason}") from None

    _lines_from_file.pinned = pinned  # type: ignore[attr-defined]  # marks the wrapper; keeps installation idempotent
    return _lines_from_file


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


def _validate_text_file(path: str) -> None:
    """Strictly decode the whole file, chunk by chunk, as UTF-16 (BOM-marked) or UTF-8."""
    file_path = Path(path)
    if file_path.is_dir():
        raise ValidationError(f"unexpected directory argument: {path}")
    try:
        with open(file_path, "rb") as handle:
            _decode_strictly(path, handle, _encoding_of(handle))
    except FileNotFoundError:
        raise ValidationError(f"cannot read {path}: file not found") from None
    except IsADirectoryError:
        raise ValidationError(f"unexpected directory argument: {path}") from None
    except PermissionError as exc:
        raise ValidationError(f"cannot read {path}: permission denied ({exc.strerror})") from None
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc.strerror or exc}") from None


def _decode_strictly(path: str, handle: IO[bytes], encoding: str) -> None:
    """Decode every byte of ``handle`` with the strict incremental codec, reporting the first bad offset.

    UTF-16 text additionally may not contain U+0000: a NUL code unit is what a UTF-32 file, or any
    other mislabelled byte stream, decodes to, and such a file would otherwise scan as "clean".
    """
    label = _ENCODING_LABELS[encoding]
    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    consumed = 0
    decoded_bytes = len(UTF16_BOMS[0]) if encoding == "utf-16" else 0  # bytes behind the decoded text

    def failure(offset: int, reason: str) -> ValidationError:
        return ValidationError(f"cannot decode {path} as {label} at byte offset {offset}: {reason}")

    while True:
        chunk = handle.read(CHUNK_BYTES)
        if not chunk:
            break
        # The incremental decoder prepends bytes it buffered from the previous chunk (an incomplete
        # multi-byte sequence) to this chunk, and ``exc.start`` is relative to that combined input;
        # the file offset is therefore anchored at ``consumed - buffered``.
        buffered_before = len(decoder.getstate()[0])
        try:
            text = decoder.decode(chunk, final=False)
        except UnicodeDecodeError as exc:
            raise failure(consumed - buffered_before + exc.start, exc.reason) from None
        consumed += len(chunk)
        if encoding == "utf-16":
            nul = text.find("\x00")
            if nul != -1:
                raise failure(decoded_bytes + len(text[:nul].encode("utf-16-le")), "NUL character")
            decoded_bytes += len(text.encode("utf-16-le"))
    buffered_at_eof = len(decoder.getstate()[0])
    try:
        decoder.decode(b"", final=True)
    except UnicodeDecodeError as exc:
        raise failure(consumed - buffered_at_eof + exc.start, exc.reason) from None


ARCHIVE_ROOT = "docs"
ARCHIVE_DIRNAME = "archive"
_HEX = frozenset("0123456789abcdef")
_OBJECT_ID_LENGTH = {"sha1": 40, "sha256": 64}
_REGULAR_FILE_MODES = frozenset({"100644", "100755"})


class _UnparseableGitOutput(Exception):
    """Git's output is not exactly what these flags produce; nothing may be exempted."""


def _is_archive_move(old: str, new: str) -> bool:
    """``new`` is ``old`` with exactly one ``archive`` folder inserted, below ``docs/``.

    The source must not already be archived, and every component must be an ordinary name
    (no ``.``, ``..`` or empty component), so the destination provably stays below ``docs/``.
    """
    old_parts, new_parts = old.split("/"), new.split("/")
    if any(part in {"", ".", ".."} for part in (*old_parts, *new_parts)):
        return False
    if old_parts[0] != ARCHIVE_ROOT or ARCHIVE_DIRNAME in old_parts or len(new_parts) != len(old_parts) + 1:
        return False
    return any(
        new_parts[index] == ARCHIVE_DIRNAME
        and new_parts[:index] == old_parts[:index]
        and new_parts[index + 1 :] == old_parts[index:]
        for index in range(1, len(old_parts))
    )


def _identical_regular_file_rename(meta: bytes, object_id_length: int) -> bool:
    """Parse one ``:<mode> <mode> <blob> <blob> R<score>`` header.

    True for an identical regular-file rename (same regular mode, same full-length non-null blob,
    score 100). Raises ``_UnparseableGitOutput`` for anything that is not a well-formed rename
    header, so one malformed record disables every exemption in the invocation.
    """
    if not meta.startswith(b":"):
        raise _UnparseableGitOutput
    try:
        fields = meta[1:].decode("ascii").split(" ")
    except UnicodeDecodeError:
        raise _UnparseableGitOutput from None
    if len(fields) != 5:
        raise _UnparseableGitOutput
    old_mode, new_mode, old_blob, new_blob, status = fields
    for mode in (old_mode, new_mode):
        if len(mode) != 6 or not mode.isdigit() or set(mode) - set("01234567"):
            raise _UnparseableGitOutput
    for blob in (old_blob, new_blob):
        if len(blob) != object_id_length or set(blob) - _HEX:
            raise _UnparseableGitOutput
    if not (status.startswith("R") and status[1:].isdigit()):
        raise _UnparseableGitOutput
    return (
        status == "R100"
        and old_mode == new_mode
        and new_mode in _REGULAR_FILE_MODES
        and old_blob == new_blob
        and set(new_blob) != {"0"}
    )


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True, timeout=60).stdout


def _byte_identical_archive_moves() -> frozenset[str]:
    """Destination paths of staged byte-identical archive moves; empty unless Git says so exactly."""
    try:
        object_format = _git("rev-parse", "--show-object-format").decode("ascii").strip()
        output = _git("diff", "--cached", "--raw", "-z", "--no-abbrev", "-M100%", "--diff-filter=R")
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        return frozenset()
    object_id_length = _OBJECT_ID_LENGTH.get(object_format)
    if object_id_length is None or (output and not output.endswith(b"\0")):
        return frozenset()
    fields = output.split(b"\0")[:-1] if output else []
    if len(fields) % 3:
        return frozenset()  # not whole records: parse nothing rather than guess
    moves: set[str] = set()
    try:
        for index in range(0, len(fields), 3):
            meta, old_raw, new_raw = fields[index : index + 3]
            identical = _identical_regular_file_rename(meta, object_id_length)
            try:
                old, new = old_raw.decode("utf-8"), new_raw.decode("utf-8")
            except UnicodeDecodeError:
                raise _UnparseableGitOutput from None
            if identical and _is_archive_move(old, new):
                moves.add(new)
    except _UnparseableGitOutput:
        return frozenset()
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
    _validate_text_file(baseline)
    for candidate in candidates:
        if candidate == DIRECTORY_MARKER:
            if not os.path.isdir(candidate):
                raise ValidationError(f"expected the compatibility directory marker {DIRECTORY_MARKER!r} to be an existing directory")
            continue
        _validate_text_file(candidate)


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
        return delegate(_without_identical_moves(argv, candidates))
    except ValidationError as exc:
        print(f"{PROGRAM}: {exc}", file=err)
        return STATUS_VALIDATION_FAILED


def main(argv: list[str] | None = None) -> int:
    return run(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
