"""The one includable-files policy (Plan 12.6 Task 1, ADR-031): which workspace files automatic context, a future
index and anchor reads may open.

Every purpose shares the security denials, judged from path metadata before any content is read, on both the spelling
and the workspace-relative real target: skipped tool folders, the reserved runtime tree, secret files (#385,
`secret_paths`), an unresolvable target and a target outside the workspace. Then `.gitignore` and `.optimusignore` (Git
wildmatch syntax, nested files, `.optimusignore` read after `.gitignore` in each folder, the last match wins, and
nothing under an excluded folder is re-included). An ignore file that exists but cannot be evaluated (an alias, a
denied target, unreadable or too large) makes every decision it would judge unavailable, never more permissive. Then
empty, binary and, for indexing only, oversized files. A denial can never be negated by an ignore file.

Content is read only from the validated target, through a handle whose file identity must equal the one validated,
and the target is rechecked after reading, so an alias swapped or a file replaced meanwhile is refused. Decisions carry
a rule id, never content, and the policy revision binds the ignore files that judged them.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

import pathspec

from optimus.guardrails.runtime_tree import has_runtime_component, resolve_target, target_reserved
from optimus.guardrails.secret_paths import is_secret_path, target_secret

POLICY_VERSION = "file-policy-v1"
DEFAULT_MAX_INDEX_FILE_BYTES = 1024 * 1024
IGNORE_FILE_NAMES = (".gitignore", ".optimusignore")
SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv", "node_modules", ".idea"})
_MAX_IGNORE_FILE_BYTES = 1024 * 1024
# NTFS and APFS treat names case-insensitively, and Git's core.ignorecase there depends on the repository. A file is
# ignored if either the exact or the case-folded rules ignore it, so neither reading can make more files eligible.
_CASE_INSENSITIVE = sys.platform in ("win32", "darwin")

ALLOWED = "allowed"
REASON_TEXT = {
    "deny.invalid_path": "not a workspace-relative path",
    "deny.skipped_dir": "inside a skipped tool folder",
    "deny.runtime_tree": "inside the Optimus runtime folder",
    "deny.secret": "a secret or credential file",  # pragma: allowlist secret - a reason label
    "deny.unresolvable": "its target cannot be resolved",
    "deny.outside_workspace": "its target is outside the workspace",
    "deny.identity_changed": "it changed while being read",
    "deny.ignore_unavailable": "an ignore file that applies to it cannot be evaluated",
    "ignored.gitignore": "excluded by .gitignore",
    "ignored.optimusignore": "excluded by .optimusignore",
    "excluded.not_found": "not a file",
    "excluded.empty": "empty",
    "excluded.binary": "not UTF-8 text",
    "excluded.too_large": "larger than the indexing file limit",
}


class FilePurpose(StrEnum):
    AUTOMATIC = "automatic"
    INDEX = "index"
    ANCHOR = "anchor"


@dataclass(frozen=True)
class FileDecision:
    relative_path: str
    allowed: bool
    reason: str
    policy_revision: str
    resolved_identity: str | None = None  # the workspace-relative real target, once path checks pass


@dataclass(frozen=True)
class _IgnoreFile:
    name: str
    spec: pathspec.GitIgnoreSpec
    folded_spec: pathspec.GitIgnoreSpec
    sha256: str


class FilePolicy:
    def __init__(self, workspace_root: Path, *, max_index_file_bytes: int = DEFAULT_MAX_INDEX_FILE_BYTES) -> None:
        self._root = workspace_root.resolve()
        self._max_index_file_bytes = max_index_file_bytes
        self._ignore_files: dict[tuple[str, ...], tuple[_IgnoreFile, ...] | None] = {}

    @property
    def root(self) -> Path:
        return self._root

    def revision(self) -> str:
        """The policy version bound to every ignore file consulted so far."""
        entries = sorted(
            ("/".join((*folder, item.name)), item.sha256)
            for folder, items in self._ignore_files.items()
            for item in items or ()
        )
        unavailable = sorted("/".join(folder) for folder, items in self._ignore_files.items() if items is None)
        digest = hashlib.sha256(repr((entries, unavailable)).encode("utf-8")).hexdigest()[:16]
        return f"{POLICY_VERSION}:{digest}"

    def path_denial(self, relative_path: str) -> str | None:
        """A security denial judged from the spelling alone, so a path that does not exist can still be refused."""
        parts = _relative_parts(relative_path)
        return "deny.invalid_path" if parts is None else _parts_denial(parts)

    def decide(self, relative_path: str, *, purpose: FilePurpose) -> FileDecision:
        return self._evaluate(relative_path, purpose)[0]

    def read(self, relative_path: str, *, purpose: FilePurpose) -> tuple[FileDecision, bytes | None]:
        """Decide and read in one validated step; content comes back only for an allowed, unchanged file."""
        return self._evaluate(relative_path, purpose)

    def walk(self, *, purpose: FilePurpose) -> Iterator[FileDecision]:
        """Every file under the workspace in sorted order, with its decision (exclusions are coverage)."""
        for path in sorted(self._root.rglob("*")):
            if path.is_file():
                yield self.decide(path.relative_to(self._root).as_posix(), purpose=purpose)

    def _evaluate(self, relative_path: str, purpose: FilePurpose) -> tuple[FileDecision, bytes | None]:
        parts = _relative_parts(relative_path)
        if parts is None:
            return self._decision(relative_path, "deny.invalid_path", ()), None
        denial = _parts_denial(parts)
        if denial is not None:
            return self._decision(relative_path, denial, ()), None
        path = self._root.joinpath(*parts)
        if not path.is_file():
            return self._decision(relative_path, "excluded.not_found", ()), None
        target = resolve_target(path)
        if target is None:
            return self._decision(relative_path, "deny.unresolvable", ()), None
        identity = _relative_identity(target, self._root)
        if identity is None:
            outside = "deny.runtime_tree" if target_reserved(target, self._root) else None
            outside = outside or ("deny.secret" if target_secret(target, self._root) else "deny.outside_workspace")
            return self._decision(relative_path, outside, ()), None
        target_parts = tuple(identity.split("/"))
        denial = _parts_denial(target_parts)
        if denial is not None:
            return self._decision(relative_path, denial, ()), None
        chains = (parts, target_parts)
        for chain in chains:
            ignored = self._ignored(chain)
            if ignored is not None:
                return self._decision(relative_path, ignored, chains), None
        limit = self._max_index_file_bytes if purpose is FilePurpose.INDEX else None
        outcome, data = _read_validated(path, target, limit)
        if outcome != ALLOWED:
            return self._decision(relative_path, outcome, chains), None
        assert data is not None
        if not data:
            return self._decision(relative_path, "excluded.empty", chains), None
        if b"\x00" in data or not _is_utf8(data):
            return self._decision(relative_path, "excluded.binary", chains), None
        return self._decision(relative_path, ALLOWED, chains, identity), data

    def _decision(
        self, relative_path: str, reason: str, chains: tuple[tuple[str, ...], ...], identity: str | None = None
    ) -> FileDecision:
        return FileDecision(
            relative_path=relative_path,
            allowed=reason == ALLOWED,
            reason=reason,
            policy_revision=self._chain_revision(chains),
            resolved_identity=identity,
        )

    def _chain_revision(self, chains: tuple[tuple[str, ...], ...]) -> str:
        entries = sorted(
            {
                ("/".join((*chain[:depth], item.name)), item.sha256)
                for chain in chains
                for depth in range(len(chain))
                for item in self._ignore_files.get(chain[:depth]) or ()
            }
        )
        digest = hashlib.sha256(repr(entries).encode("utf-8")).hexdigest()[:16]
        return f"{POLICY_VERSION}:{digest}"

    def _ignored(self, parts: tuple[str, ...]) -> str | None:
        modes = (False, True) if _CASE_INSENSITIVE else (False,)
        # Git: nothing under an excluded folder is re-included. Each folder is judged by its ancestors' rules before
        # its own ignore files are opened, so an excluded folder's ignore files are never read.
        for end in range(len(parts)):
            for folded in modes if end else ():
                verdict = self._match(parts[:end], is_dir=True, folded=folded)
                if verdict is not None:
                    return verdict
            if self._load(parts[:end]) is None:
                return "deny.ignore_unavailable"
        for folded in modes:
            verdict = self._match(parts, is_dir=False, folded=folded)
            if verdict is not None:
                return verdict
        return None

    def _match(self, parts: tuple[str, ...], *, is_dir: bool, folded: bool) -> str | None:
        verdict: str | None = None
        for depth in range(len(parts)):  # the root's ignore files first, so deeper ones override them
            candidate = "/".join(parts[depth:]) + ("/" if is_dir else "")
            for item in self._load(parts[:depth]) or ():
                spec = item.folded_spec if folded else item.spec
                result = spec.check_file(candidate.casefold() if folded else candidate)
                if result.include is not None:
                    verdict = f"ignored{item.name}" if result.include else None  # "ignored.gitignore"
        return verdict

    def _load(self, folder: tuple[str, ...]) -> tuple[_IgnoreFile, ...] | None:
        """The folder's ignore files, or None when one exists but cannot be evaluated safely."""
        if folder in self._ignore_files:
            return self._ignore_files[folder]
        loaded: list[_IgnoreFile] | None = []
        for name in IGNORE_FILE_NAMES:
            state, data = self._read_ignore_file(folder, name)
            if state == "unavailable":
                loaded = None
                break
            if state == "absent" or data is None or loaded is None:
                continue
            text = data.decode("utf-8", errors="replace")
            loaded.append(
                _IgnoreFile(
                    name=name,
                    spec=pathspec.GitIgnoreSpec.from_lines(text.splitlines()),
                    folded_spec=pathspec.GitIgnoreSpec.from_lines(text.casefold().splitlines()),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
        self._ignore_files[folder] = None if loaded is None else tuple(loaded)
        return self._ignore_files[folder]

    def _read_ignore_file(self, folder: tuple[str, ...], name: str) -> tuple[str, bytes | None]:
        """("absent", None), ("present", bytes), or ("unavailable", None) when it exists but cannot be evaluated: an
        alias (Git does not follow one either), a denied target, unreadable or over the size cap."""
        path = self._root.joinpath(*folder, name)
        if not os.path.lexists(path):
            return "absent", None
        parent = resolve_target(path.parent)
        target = resolve_target(path)
        if path.is_symlink() or not path.is_file() or parent is None or target is None or target != parent / name:
            return "unavailable", None
        identity = _relative_identity(target, self._root)
        if identity is None or _parts_denial(tuple(identity.split("/"))) is not None:
            return "unavailable", None
        outcome, data = _read_validated(path, target, _MAX_IGNORE_FILE_BYTES)
        if outcome != ALLOWED or data is None:
            return "unavailable", None
        return "present", data


def describe(reason: str) -> str:
    return REASON_TEXT.get(reason, reason)


def _parts_denial(parts: tuple[str, ...]) -> str | None:
    names = tuple(part.casefold() for part in parts) if _CASE_INSENSITIVE else parts
    if any(name in SKIP_DIR_NAMES for name in names):
        return "deny.skipped_dir"
    if has_runtime_component(parts):
        return "deny.runtime_tree"
    if is_secret_path("/".join(parts)):
        return "deny.secret"
    return None


def _read_validated(path: Path, target: Path, limit: int | None) -> tuple[str, bytes | None]:
    """Read ``target`` only once the opened handle is proven to be the validated file: the operating system's real
    path of the handle must be the validated target (so a folder swapped after validation is caught before any byte
    is read) and its file identity must equal the one stat'd. After the read, the alias must still resolve there and
    the file be unchanged. ``limit``: the size cap, if any.

    shortcut: where the OS cannot report a handle's path (a filesystem without final-path support, a BSD), only the
    file-identity checks apply; extend _handle_path when such a platform matters."""
    try:
        before = os.stat(target)
        if limit is not None and before.st_size > limit:
            return "excluded.too_large", None
        with open(target, "rb") as handle:
            real = _handle_path(handle.fileno())
            if real is not None and os.path.normcase(real) != os.path.normcase(target):
                return "deny.identity_changed", None  # a folder on the way was swapped: nothing is read
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                return "deny.identity_changed", None  # replaced after validation: nothing is read
            data = handle.read() if limit is None else handle.read(limit + 1)
        after = os.stat(target)
    except OSError:
        return "excluded.not_found", None
    if limit is not None and len(data) > limit:
        return "excluded.too_large", None
    unchanged = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) == (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
    )
    if not unchanged or resolve_target(path) != target:
        return "deny.identity_changed", None
    return ALLOWED, data


def _handle_path(fd: int) -> str | None:
    """The real path of an open file as the operating system reports it, or None where it cannot."""
    try:
        if sys.platform == "win32":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            get_final_path = ctypes.windll.kernel32.GetFinalPathNameByHandleW
            get_final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
            get_final_path.restype = wintypes.DWORD
            buffer = ctypes.create_unicode_buffer(32768)
            length = get_final_path(msvcrt.get_osfhandle(fd), buffer, len(buffer), 0)
            if not 0 < length < len(buffer):
                return None
            text = buffer.value
            if text.startswith("\\\\?\\UNC\\"):
                return "\\\\" + text[8:]
            return text[4:] if text.startswith("\\\\?\\") else text
        if sys.platform == "darwin":
            import fcntl

            raw = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024))
            return os.fsdecode(raw.split(b"\x00", 1)[0])
        return os.readlink(f"/proc/self/fd/{fd}")
    except (OSError, AttributeError, ValueError):
        return None


def _relative_parts(relative_path: str) -> tuple[str, ...] | None:
    text = relative_path.replace("\\", "/")
    if not text or text.startswith("/") or ":" in text:
        return None
    parts = tuple(part for part in PurePosixPath(text).parts if part != ".")
    if not parts or ".." in parts:
        return None
    return parts


def _relative_identity(target: Path, root: Path) -> str | None:
    try:
        return target.relative_to(root).as_posix()
    except ValueError:
        return None


def _is_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
