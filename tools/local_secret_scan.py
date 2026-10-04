"""Local secret-scan adapter: strict UTF-8 validation before delegating to the pinned detect-secrets hook.

Why this exists (local-hook UTF-8 repair, 2026-09-06): the pinned ``detect_secrets`` file reader
opens files in the process locale and silently yields no lines on ``UnicodeDecodeError``. Under the
Windows CP1252 default a valid UTF-8 file containing a code point outside CP1252 is skipped entirely,
and in UTF-8 mode an invalid-UTF-8 file is skipped entirely (CP1252 can read byte FF; the failure
depends on the decoding mode), so the hook can pass a file it never read. This adapter

1. requires the interpreter to run in UTF-8 mode (the configured entry passes ``-X utf8``),
2. strictly decodes the baseline and every selected file, whole file, in chunks: as UTF-16 when the
   file lies in the frozen Plan 11.7 custody namespace (``reports/plan-11-7-server-custody-artifacts/``)
   and starts with a UTF-16 byte-order mark (scanner decoding repair, 2026-10-03), as UTF-8
   everywhere else, the baseline included,
3. rejects with status 2 and a path/offset/reason diagnostic before the scanner is imported or the
   baseline can be touched, and
4. otherwise delegates the original arguments to ``detect_secrets.pre_commit_hook.main``, in their
   original order, and returns its status (0 clean, 1 findings, 3 baseline maintenance) as-is. The
   scanner's file reader is replaced by one that reads a file once, validates exactly those bytes by
   the same rules and hands the decoded text to the scanner's transformers under the original path,
   so plugins, filters and baseline identities see the same file they always did and a BOM-marked
   report is scanned as UTF-16 without touching its bytes. The pinned reader opens files in the
   locale codec and yields nothing for one it cannot decode, and ``scan_file`` swallows ``IOError``
   and skips a file that stopped existing; the replacement raises ``ValidationError``, which the
   scanner does not catch, so a file that became unreadable, vanished or changed shape after
   validation fails the hook (status 2) instead of scanning as clean.

The one argument it drops is a byte-identical archive move (docs archive convention, 2026-09-29):
a regular file moved from a ``docs/`` folder into the ``archive/`` beside it (the destination is
the not-yet-archived source path with one ``archive`` folder inserted) without changing a byte or
its mode, which Git reports as a staged R100 rename with identical blob ids. Frozen documents
cannot take inline allowlist pragmas, so without this they could never be archived. Every other
move, any changed byte and any copy is scanned as before. If Git fails, or any part of its output
is not exactly what these flags produce, nothing is dropped.

It does not enumerate directories, rewrite or re-encode any file on disk, or decode with
replacement characters. A UTF-16 file outside the custody namespace, or one without a byte-order
mark, is not recognised as UTF-16: it is validated as UTF-8 like any other selected file. There is no
snapshot: a file is read for validation and read again for the scan, and each read is validated
on its own, so the scanner never sees bytes that were not; and a selected file the scanner's own
filters dropped without the reader ever reading it fails the hook unless it is still a regular
file (a configured filename exclusion). The literal ``src`` argument that the configured
entry carries is a compatibility marker for the scanner's positional interface: it is validated as
an existing directory and passed through, never scanned recursively by this adapter (pre-commit
supplies the selected filenames).
"""

from __future__ import annotations

import codecs
import io
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
UTF16_REPORT_NAMESPACE = ("reports", "plan-11-7-server-custody-artifacts")
_ENCODING_LABELS = {"utf-8": "UTF-8", "utf-16": "UTF-16"}

LineReader = Callable[[str], Iterator[list[str]]]


class ValidationError(Exception):
    """A selected input could not be validated; carries the user-facing diagnostic."""


def _utf8_mode_enabled() -> bool:
    return bool(sys.flags.utf8_mode)


def _delegate(argv: list[str]) -> int:
    """Import the pinned scanner only after validation succeeded, with its file reading made strict."""
    from detect_secrets.core import scan
    from detect_secrets.pre_commit_hook import main as hook_main

    if not getattr(scan.scan_file, "strict", False):
        read_by_reader: list[str] = []
        scan._get_lines_from_file = _strict_reader(read_by_reader)
        scan.scan_file = _strict_scan_file(scan.scan_file, read_by_reader)
    result = hook_main(argv)
    return int(result or 0)


def _is_utf16_report(path: str) -> bool:
    """A relative path strictly below the frozen custody namespace, with ordinary components only."""
    pure = PurePath(path)
    parts = pure.as_posix().split("/")
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in parts):
        return False
    return len(parts) > len(UTF16_REPORT_NAMESPACE) and tuple(parts[: len(UTF16_REPORT_NAMESPACE)]) == UTF16_REPORT_NAMESPACE


def _encoding_for(path: str, head: bytes) -> str:
    """``utf-16`` only for a BOM-marked file inside the custody namespace; ``utf-8`` for everything else."""
    return "utf-16" if head[: len(UTF16_BOMS[0])] in UTF16_BOMS and _is_utf16_report(path) else "utf-8"


class _NamedText(io.StringIO):
    """Decoded file content carrying the ``name`` the scanner's transformers key on."""

    def __init__(self, text: str, name: str) -> None:
        super().__init__(text)
        self.name = name


def _strict_scan_file(
    pinned_scan_file: Callable[[str], Iterator[object]], read_by_reader: list[str]
) -> Callable[[str], Iterator[object]]:
    """Make sure a selected file is either read by the strict reader or fails the hook.

    ``scan_file`` first runs filename filters before any reader is involved. One of them,
    ``is_invalid_file``, drops a path that is not a regular file, so a selected file that vanished
    or turned into a directory would be skipped as if clean. Two checks close that: the file is
    read and validated right before the scanner sees it, and after the scanner is done the wrapper
    confirms the strict reader actually read it; if it did not and the path is not a regular file
    any more, the hook fails. A path the reader did not read but that is still a regular file was
    skipped by a configured filename filter (the baseline, lock files, swagger paths), which is
    honoured. The one path meant to be dropped is the literal compatibility directory marker,
    which the scanner has always received and skipped as "not a file".
    """

    def scan_file(filename: str) -> Iterator[object]:
        if filename == DIRECTORY_MARKER:
            yield from pinned_scan_file(filename)
            return
        _read_strictly(filename)
        read_by_reader.clear()
        yield from pinned_scan_file(filename)
        if filename not in read_by_reader and not os.path.isfile(filename):
            reason = "unexpected directory argument" if os.path.isdir(filename) else "file not found"
            raise ValidationError(f"cannot read {filename}: {reason} when the scanner looked for it")

    scan_file.strict = True  # type: ignore[attr-defined]  # marks the wrapper; keeps installation idempotent
    return scan_file


def _strict_reader(read_by_reader: list[str] | None = None) -> LineReader:
    """The scanner's file reader, built on ``_read_strictly``.

    Mirrors the pinned reader of detect-secrets 1.5.0 (``detect_secrets.core.scan._get_lines_from_file``:
    the file's transformer, else its lines, then the eager transformers) and differs only in how the
    text is obtained: bytes read once and validated by the rules above, newlines translated as the
    pinned ``open`` did, instead of a locale-codec ``open`` whose decode failure the pinned reader
    swallows as "no lines". Each file it read is recorded in ``read_by_reader`` for ``scan_file``.
    """
    from detect_secrets.transformers import get_transformed_file

    def _lines_from_file(filename: str) -> Iterator[list[str]]:
        text = _read_strictly(filename)
        if read_by_reader is not None:
            read_by_reader.append(filename)
        handle = _NamedText(text.replace("\r\n", "\n").replace("\r", "\n"), filename)
        yield get_transformed_file(handle) or handle.readlines()
        handle.seek(0)
        lines = get_transformed_file(handle, use_eager_transformers=True)
        if lines:
            yield lines

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


def _read_strictly(path: str) -> str:
    """Read the whole file and strictly decode exactly those bytes; every failure is a ``ValidationError``.

    Used before delegation and again by the scanner's reader, so nothing the scanner sees has
    escaped these rules, and nothing it cannot read or decode can pass as clean.
    """
    file_path = Path(path)
    if file_path.is_dir():
        raise ValidationError(f"unexpected directory argument: {path}")
    try:
        with open(file_path, "rb") as handle:
            head = handle.read(len(UTF16_BOMS[0]))
            handle.seek(0)
            return _decode_strictly(path, handle, _encoding_for(path, head))
    except FileNotFoundError:
        raise ValidationError(f"cannot read {path}: file not found") from None
    except IsADirectoryError:
        raise ValidationError(f"unexpected directory argument: {path}") from None
    except PermissionError as exc:
        raise ValidationError(f"cannot read {path}: permission denied ({exc.strerror})") from None
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc.strerror or exc}") from None


def _decode_strictly(path: str, handle: IO[bytes], encoding: str) -> str:
    """Decode every byte of ``handle`` with the strict incremental codec, reporting the first bad offset.

    UTF-16 text additionally may not contain U+0000: a NUL code unit is what a UTF-32 file, or any
    other mislabelled byte stream, decodes to, and such a file would otherwise scan as "clean".
    """
    label = _ENCODING_LABELS[encoding]
    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    consumed = 0
    decoded_bytes = len(UTF16_BOMS[0]) if encoding == "utf-16" else 0  # bytes behind the decoded text
    pieces: list[str] = []

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
        pieces.append(text)
    buffered_at_eof = len(decoder.getstate()[0])
    try:
        pieces.append(decoder.decode(b"", final=True))
    except UnicodeDecodeError as exc:
        raise failure(consumed - buffered_at_eof + exc.start, exc.reason) from None
    return "".join(pieces)


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
    _read_strictly(baseline)
    for candidate in candidates:
        if candidate == DIRECTORY_MARKER:
            if not os.path.isdir(candidate):
                raise ValidationError(f"expected the compatibility directory marker {DIRECTORY_MARKER!r} to be an existing directory")
            continue
        _read_strictly(candidate)


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
