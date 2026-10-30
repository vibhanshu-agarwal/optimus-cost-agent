"""The one includable-files policy (Plan 12.6 Task 1, ADR-031): which workspace files automatic context, a future
index and anchor reads may open.

Every purpose shares the security denials, judged from path metadata before any content is opened: skipped tool
folders, the reserved runtime tree, secret files (#385, `secret_paths`), an unresolvable target and a target outside
the workspace. Then `.gitignore` and `.optimusignore` (Git wildmatch syntax, nested files, `.optimusignore` read after
`.gitignore` in each folder, the last match wins, and nothing under an excluded folder is re-included); then empty,
binary and, for indexing only, oversized files. A denial can never be negated by an ignore file. Decisions carry a
rule id, never file content, and the policy revision binds the ignore files that judged them.
"""

from __future__ import annotations

import hashlib
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
_CASE_INSENSITIVE = sys.platform == "win32"  # as Git's core.ignorecase on NTFS; it only ever narrows access

ALLOWED = "allowed"
REASON_TEXT = {
    "deny.invalid_path": "not a workspace-relative path",
    "deny.skipped_dir": "inside a skipped tool folder",
    "deny.runtime_tree": "inside the Optimus runtime folder",
    "deny.secret": "a secret or credential file",  # pragma: allowlist secret - a reason label
    "deny.unresolvable": "its target cannot be resolved",
    "deny.outside_workspace": "its target is outside the workspace",
    "deny.identity_changed": "it changed while being read",
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
    sha256: str


class FilePolicy:
    def __init__(self, workspace_root: Path, *, max_index_file_bytes: int = DEFAULT_MAX_INDEX_FILE_BYTES) -> None:
        self._root = workspace_root.resolve()
        self._max_index_file_bytes = max_index_file_bytes
        self._ignore_files: dict[tuple[str, ...], tuple[_IgnoreFile, ...]] = {}

    @property
    def root(self) -> Path:
        return self._root

    def revision(self) -> str:
        """The policy version bound to every ignore file consulted so far."""
        entries = sorted(
            ("/".join((*folder, item.name)), item.sha256) for folder, items in self._ignore_files.items() for item in items
        )
        digest = hashlib.sha256(repr(entries).encode("utf-8")).hexdigest()[:16]
        return f"{POLICY_VERSION}:{digest}"

    def path_denial(self, relative_path: str) -> str | None:
        """A security denial judged from the spelling alone, so a path that does not exist can still be refused."""
        parts = _relative_parts(relative_path)
        if parts is None:
            return "deny.invalid_path"
        if any(part in SKIP_DIR_NAMES for part in parts):
            return "deny.skipped_dir"
        if has_runtime_component(parts):
            return "deny.runtime_tree"
        if is_secret_path("/".join(parts)):
            return "deny.secret"
        return None

    def decide(self, relative_path: str, *, purpose: FilePurpose) -> FileDecision:
        return self._evaluate(relative_path, purpose)[0]

    def read(self, relative_path: str, *, purpose: FilePurpose) -> tuple[FileDecision, bytes | None]:
        """Decide, read, then recheck the target's identity; content comes back only for an allowed, unchanged file."""
        decision, data = self._evaluate(relative_path, purpose)
        if not decision.allowed:
            return decision, None
        target = resolve_target(self._root / relative_path)
        if target is None or _relative_identity(target, self._root) != decision.resolved_identity:
            return self._decision(relative_path, "deny.identity_changed", ()), None
        return decision, data

    def walk(self, *, purpose: FilePurpose) -> Iterator[FileDecision]:
        """Every file under the workspace in sorted order, with its decision (exclusions are coverage)."""
        for path in sorted(self._root.rglob("*")):
            if path.is_file():
                yield self.decide(path.relative_to(self._root).as_posix(), purpose=purpose)

    def _evaluate(self, relative_path: str, purpose: FilePurpose) -> tuple[FileDecision, bytes | None]:
        denial = self.path_denial(relative_path)
        if denial is not None:
            return self._decision(relative_path, denial, ()), None
        parts = _relative_parts(relative_path) or ()
        path = self._root.joinpath(*parts)
        if not path.is_file():
            return self._decision(relative_path, "excluded.not_found", ()), None
        target = resolve_target(path)
        if target is None:
            return self._decision(relative_path, "deny.unresolvable", ()), None
        if target_reserved(target, self._root):
            return self._decision(relative_path, "deny.runtime_tree", ()), None
        if target_secret(target, self._root):
            return self._decision(relative_path, "deny.secret", ()), None
        identity = _relative_identity(target, self._root)
        if identity is None:
            return self._decision(relative_path, "deny.outside_workspace", ()), None
        target_parts = tuple(identity.split("/"))
        chains = (parts, target_parts)
        for chain in chains:
            ignored = self._ignored(chain)
            if ignored is not None:
                return self._decision(relative_path, ignored, chains), None
        if purpose is FilePurpose.INDEX:
            try:
                too_large = path.stat().st_size > self._max_index_file_bytes
            except OSError:
                return self._decision(relative_path, "excluded.not_found", chains), None
            if too_large:
                return self._decision(relative_path, "excluded.too_large", chains), None
        try:
            data = path.read_bytes()
        except OSError:
            return self._decision(relative_path, "excluded.not_found", chains), None
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
                for item in self._ignore_files.get(chain[:depth], ())
            }
        )
        digest = hashlib.sha256(repr(entries).encode("utf-8")).hexdigest()[:16]
        return f"{POLICY_VERSION}:{digest}"

    def _ignored(self, parts: tuple[str, ...]) -> str | None:
        # Git: nothing under an excluded folder is re-included, so each ancestor folder is judged first.
        for end in range(1, len(parts)):
            verdict = self._match(parts[:end], is_dir=True)
            if verdict is not None:
                return verdict
        return self._match(parts, is_dir=False)

    def _match(self, parts: tuple[str, ...], *, is_dir: bool) -> str | None:
        verdict: str | None = None
        for depth in range(len(parts)):  # the root's ignore files first, so deeper ones override them
            candidate = "/".join(parts[depth:]) + ("/" if is_dir else "")
            if _CASE_INSENSITIVE:
                candidate = candidate.casefold()
            for item in self._load(parts[:depth]):
                result = item.spec.check_file(candidate)
                if result.include is not None:
                    verdict = f"ignored{item.name}" if result.include else None  # "ignored.gitignore"
        return verdict

    def _load(self, folder: tuple[str, ...]) -> tuple[_IgnoreFile, ...]:
        cached = self._ignore_files.get(folder)
        if cached is not None:
            return cached
        loaded: list[_IgnoreFile] = []
        for name in IGNORE_FILE_NAMES:
            path = self._root.joinpath(*folder, name)
            try:
                if not path.is_file() or path.stat().st_size > _MAX_IGNORE_FILE_BYTES:
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            text = data.decode("utf-8", errors="replace")
            lines = text.casefold().splitlines() if _CASE_INSENSITIVE else text.splitlines()
            spec = pathspec.GitIgnoreSpec.from_lines(lines)
            loaded.append(_IgnoreFile(name=name, spec=spec, sha256=hashlib.sha256(data).hexdigest()))
        self._ignore_files[folder] = tuple(loaded)
        return self._ignore_files[folder]


def describe(reason: str) -> str:
    return REASON_TEXT.get(reason, reason)


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
