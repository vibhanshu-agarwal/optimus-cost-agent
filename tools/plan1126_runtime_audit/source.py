"""Read-only source views for working with files or immutable Git blobs."""

from __future__ import annotations

import ast
import hashlib
import io
import os
import subprocess
import tarfile
import threading
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Mapping


def _validate_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ValueError("path must be repository-relative")
    return pure.as_posix()


class SourceTree:
    """A deterministic in-memory source tree, primarily for offline fixtures."""

    def __init__(self, files: Mapping[str, str]) -> None:
        self._files = {_validate_relative_path(path): text for path, text in files.items()}

    def paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._files))

    def read_text(self, path: str) -> str:
        return self._files[_validate_relative_path(path)]


# Plan 11.30 Task 4: a session export cache. A read-only export of a whole commit is reused only by a reader
# of the same repository, resolved commit, path set and exporting tool/configuration, in the same thread,
# until the session ends (the root conftest clears it). Bounded: each thread holds only its most recent
# export, as one live reader already does. A failed export is never cached.
_EXPORT_ARGUMENTS = ("archive", "--format=tar")
_WHOLE_TREE = "*"  # the path set every export covers
# Environment that changes what an export of a fixed commit contains: attributes, replace objects, and which
# repository and object store git actually reads, whatever the working directory.
_EXPORT_ENVIRONMENT = (
    "GIT_ATTR_NOSYSTEM", "GIT_ATTR_SOURCE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE",
    "GIT_DIR", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)
_exported = threading.local()


class _Unreusable(ValueError):
    """An export whose bytes are not fixed by any keyed input (a filter driver or export-subst in effect): never
    reused."""


def clear_export_cache() -> None:
    """End this thread's export reuse: called when a test session starts and when it ends."""
    _exported.__dict__.clear()


class GitCommitSource:
    """A source tree read from immutable Git objects by bounded subprocesses."""

    _GIT_TIMEOUT_SECONDS = 10.0

    def __init__(self, commit: str, repository: Path | str = ".") -> None:
        self.repository = Path(repository).resolve()
        self._archive: Mapping[str, bytes] | None = None
        resolved = self._run("rev-parse", "--verify", f"{commit}^{{commit}} ".strip()).strip()
        if len(resolved) != 40 or any(ch not in "0123456789abcdef" for ch in resolved):
            raise ValueError("commit must resolve to an immutable commit object")
        self.commit = resolved

    def _run(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self._GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        return completed.stdout

    def _config_value(self, name: str) -> str:
        """One configuration value, or "" when it is unset (git exits 1); any other failure raises."""
        completed = subprocess.run(
            ["git", "config", "--get", name],
            cwd=self.repository, capture_output=True, text=True, encoding="utf-8",
            timeout=self._GIT_TIMEOUT_SECONDS, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        if completed.returncode == 1:
            return ""
        if completed.returncode != 0:
            raise subprocess.CalledProcessError(completed.returncode, completed.args)
        return completed.stdout.strip()

    def _located(self, path: str) -> Path:
        return Path(path) if Path(path).is_absolute() else self.repository / path

    def _content(self, path: str) -> str:
        located = self._located(path)
        return hashlib.sha256(located.read_bytes()).hexdigest() if located.is_file() else "absent"

    def _git_bytes(self, *args: str, stdin: bytes | None = None) -> bytes:
        """Raw git output: tree paths are bytes and need not be UTF-8."""
        return subprocess.run(
            ["git", *args], input=stdin, cwd=self.repository, check=True, capture_output=True,
            timeout=self._GIT_TIMEOUT_SECONDS, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        ).stdout

    def _attributes_in_effect(self, external: tuple[str, ...]) -> bytes:
        """The raw bytes of every attribute source that may name a filter or export-subst: the external sources and
        every .gitattributes blob of the exported tree, at any depth and in any mode (archive reads a symlink's blob
        as rules too), never only what `git grep` chooses to print (Fable C7). Paths are compared as bytes; a blob
        whose header is not `<id> <type> <size>` (missing, ambiguous) raises ValueError, so the key is None."""
        found = b"".join(self._located(path).read_bytes() for path in external if self._located(path).is_file())
        objects = b"".join(entry.split(b"\t", 1)[0].split(b" ")[2] + b"\n"
                           for entry in self._git_bytes("ls-tree", "-r", "-z", self.commit).split(b"\0")
                           if entry and entry.split(b"\t", 1)[1].rsplit(b"/", 1)[-1] == b".gitattributes")
        if not objects:
            return found
        batch, at = self._git_bytes("cat-file", "--batch", stdin=objects), 0
        while at < len(batch):
            end = batch.index(b"\n", at)
            header = batch[at:end].split(b" ")
            if len(header) != 3:
                raise ValueError("an attribute blob of the exported tree cannot be read")
            size = int(header[2])
            found += batch[end + 1:end + 1 + size]
            at = end + 1 + size + 1
        return found

    def _export_rules(self) -> str:
        """Every mutable input `git archive` applies to a fixed commit id, by CONTENT (configuration text is keyed
        separately). Attributes: the repository's info/attributes, the global file (core.attributesFile or its
        default location) and the system file, and an attribute tree (attr.tree / GIT_ATTR_SOURCE) by the tree it
        resolves to now. Replace refs, which substitute objects inside the exported commit. Plus the environment
        switches that disable or redirect these. The supported export passes no --worktree-attributes, so the
        working tree's .gitattributes never applies. Inputs only export-subst placeholders read (where HEAD points,
        refs, history, mailmap sources, the wall clock) are not keyed: an export they may shape is never reused."""
        lines = [f"{name}={os.environ.get(name, '')}" for name in _EXPORT_ENVIRONMENT]
        for label, named in (
            ("attr.tree", self._config_value("attr.tree")),
            ("GIT_ATTR_SOURCE", os.environ.get("GIT_ATTR_SOURCE", "")),
        ):
            if named:  # may name a moving ref: bind the tree it resolves to now
                lines.append(f"{label} {named}\0{self._run('rev-parse', '--verify', '--end-of-options', named + '^{tree}').strip()}")
        base = os.environ.get("GIT_REPLACE_REF_BASE") or "refs/replace/"
        lines.append("replace\0" + self._run("for-each-ref", "--format=%(refname) %(objectname)", base))
        external: list[str] = []
        for query in (("rev-parse", "--git-path", "info/attributes"), ("var", "GIT_ATTR_GLOBAL"), ("var", "GIT_ATTR_SYSTEM")):
            path = self._run(*query).strip()
            external.append(path)
            lines.append(f"{' '.join(query)}\0{path}\0{self._content(path)}")
        lines.append("git-dir\0" + self._run("rev-parse", "--absolute-git-dir").strip())
        in_effect = self._attributes_in_effect(tuple(external))
        drivers = [line for line in self._run("config", "--list").splitlines()
                   if line.startswith("filter.") and (".smudge=" in line or ".process=" in line)]
        if b"filter=" in in_effect and drivers:
            raise _Unreusable("a filter driver may shape this export")
        if b"export-subst" in in_effect:  # placeholders read where HEAD points, refs, history and the wall clock (%cr)
            raise _Unreusable("export-subst placeholders may shape this export")
        return "\n".join(lines)

    def _export_key(self) -> tuple[str, str, str, str] | None:
        """Repository, resolved commit, path set, and the exporting tool invocation, configuration and every
        export-rule input. None when an input cannot be established: that export is then never reused."""
        try:
            rules = self._export_rules()
            tool = "\0".join((*_EXPORT_ARGUMENTS, self._run("version"), self._run("config", "--list"), rules))
        except (OSError, ValueError, subprocess.SubprocessError):  # ValueError: undecodable git output
            return None
        return (str(self.repository), self.commit, _WHOLE_TREE, hashlib.sha256(tool.encode("utf-8")).hexdigest())

    def _load_archive(self) -> Mapping[str, bytes]:
        if self._archive is None:
            key = self._export_key()
            if key is not None and getattr(_exported, "key", None) == key:
                self._archive = _exported.archive
                return self._archive
            completed = subprocess.run(
                ["git", *_EXPORT_ARGUMENTS, self.commit],
                cwd=self.repository,
                check=True,
                capture_output=True,
                timeout=self._GIT_TIMEOUT_SECONDS,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            )
            archive: dict[str, bytes] = {}
            with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as bundle:
                for member in bundle.getmembers():
                    if not member.isfile():
                        continue
                    handle = bundle.extractfile(member)
                    if handle is not None:
                        archive[_validate_relative_path(member.name)] = handle.read()
            # Read-only, so one reader cannot change what another reads; held only once complete.
            self._archive = MappingProxyType(archive)
            if key is not None:
                _exported.key, _exported.archive = key, self._archive
        return self._archive

    def paths(self) -> tuple[str, ...]:
        output = self._run("ls-tree", "-r", "--name-only", self.commit)
        return tuple(sorted(line for line in output.splitlines() if line))

    def read_text(self, path: str) -> str:
        relative = _validate_relative_path(path)
        text = self._load_archive()[relative].decode("utf-8")
        return text.replace("\r\n", "\n").replace("\r", "\n")


class ExecutingSourceMismatch(RuntimeError):
    """The module a probe is about to execute is not the source the record is bound to.

    Raised, never downgraded to a skip or a success. A fresh dynamic measurement taken
    against today's installed module is evidence about *today's* source; recording it
    under a record bound to a different revision would file a current measurement as
    historical evidence.
    """


class SymbolCitationError(RuntimeError):
    """A citation could not be resolved to exactly one symbol in the bound source.

    Raised for a missing symbol and for an ambiguous one. A citation that silently kept
    a stale line number would be worse than either: it would keep pointing somewhere,
    just not at the thing it names.
    """


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def source_fingerprint(source: "SourceTree | GitCommitSource", paths: tuple[str, ...]) -> str:
    """A stable digest of exactly the paths an inventory was built from.

    Pairing this with an inventory is what stops a caller from discovering a contract
    from one tree and then measuring a different one: identity of the executing modules
    alone does not establish that the inventory describes them.
    """
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_normalize(source.read_text(path)).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def resolve_symbol_citation(
    source: "SourceTree | GitCommitSource",
    path: str,
    symbol: str,
) -> str:
    """Resolve ``symbol`` to ``path:line:symbol`` in the BOUND source, by identity.

    ``symbol`` is a dotted name relative to the module, e.g. ``RedisRuntime.from_url``
    or ``sync_await``. A moved definition yields a moved citation; a definition that no
    longer exists, or one that exists more than once, raises rather than leaving a
    literal line number that now points at unrelated code.
    """
    tree = ast.parse(_normalize(source.read_text(path)))
    wanted = symbol.split(".")
    matches: list[int] = []

    def _walk(nodes, prefix: list[str]) -> None:
        for node in nodes:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            qualified = [*prefix, node.name]
            if qualified == wanted:
                matches.append(node.lineno)
            if isinstance(node, ast.ClassDef):
                _walk(node.body, qualified)

    _walk(tree.body, [])
    if not matches:
        raise SymbolCitationError(f"{path}: symbol {symbol!r} is not defined in the bound source")
    if len(matches) > 1:
        raise SymbolCitationError(f"{path}: symbol {symbol!r} is defined {len(matches)} times in the bound source")
    return f"{path}:{matches[0]}:{symbol}"


def _symbol_span(source: "SourceTree | GitCommitSource", path: str, symbol: str) -> tuple[int, int]:
    tree = ast.parse(_normalize(source.read_text(path)))
    wanted = symbol.split(".")
    matches: list[tuple[int, int]] = []

    def _walk(nodes, prefix: list[str]) -> None:
        for node in nodes:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            qualified = [*prefix, node.name]
            if qualified == wanted:
                matches.append((node.lineno, node.end_lineno or node.lineno))
            if isinstance(node, ast.ClassDef):
                _walk(node.body, qualified)

    _walk(tree.body, [])
    if not matches:
        raise SymbolCitationError(f"{path}: symbol {symbol!r} is not defined in the bound source")
    if len(matches) > 1:
        raise SymbolCitationError(f"{path}: symbol {symbol!r} is defined {len(matches)} times in the bound source")
    return matches[0]


def verify_symbol_citation(source: "SourceTree | GitCommitSource", citation: str) -> str:
    """Check that ``path:line:symbol`` still lands inside ``symbol`` in the BOUND source.

    A finding often cites a specific line *within* a definition -- the one that shows the
    defect, such as the connect timeout that bounds only connection setup -- rather than
    the ``def`` line. Re-resolving such a citation to the definition would silently
    discard the evidence it was pointing at, which is how a correct citation gets
    "repaired" into a useless one.

    So the line is preserved and CHECKED: it must fall within the span of the named
    symbol in the source this record is bound to. A moved or deleted definition makes the
    check fail loudly, which is the only outcome worse than neither -- a stale line
    number quietly pointing at unrelated code -- was meant to prevent.
    """
    path, _, remainder = citation.partition(":")
    line_text, _, symbol = remainder.partition(":")
    if not path or not line_text.isdigit() or not symbol:
        raise SymbolCitationError(f"{citation!r} is not a path:line:symbol citation")
    line = int(line_text)
    start, end = _symbol_span(source, path, symbol)
    if not start <= line <= end:
        raise SymbolCitationError(
            f"{path}: citation line {line} for {symbol!r} is outside that symbol, which spans "
            f"lines {start}-{end} in the bound source; the cited evidence has moved"
        )
    return citation


def executing_module_digest(module: object) -> str:
    """Digest the file the module is loaded from, normalized for line endings."""
    executing_file = getattr(module, "__file__", None)
    if executing_file is None:
        raise ExecutingSourceMismatch("the executing module exposes no __file__, so its identity cannot be verified")
    return hashlib.sha256(_normalize(Path(executing_file).read_text(encoding="utf-8")).encode("utf-8")).hexdigest()


def verify_executing_module(source: "SourceTree | GitCommitSource", path: str, module: object) -> None:
    """Verify that ``module`` is loaded from exactly the bound source for ``path``.

    Both operands are normalized for line endings only -- a Windows checkout and a
    Git blob must not disagree for that reason alone. Nothing else is normalized: a
    real difference in the executing code is exactly what this exists to catch.
    """
    executing_file = getattr(module, "__file__", None)
    if executing_file is None:
        raise ExecutingSourceMismatch(
            f"{path}: the executing module exposes no __file__, so its identity cannot be verified"
        )
    try:
        bound_text = source.read_text(path)
    except KeyError as exc:
        raise ExecutingSourceMismatch(f"{path}: the bound source does not contain this path") from exc
    executing_text = Path(executing_file).read_text(encoding="utf-8")
    if _normalize(executing_text) != _normalize(bound_text):
        raise ExecutingSourceMismatch(
            f"{path}: the executing module at {executing_file} does not match the bound source. "
            "A fresh measurement here would be recorded against a revision it was not taken from; "
            "re-execute in an isolated checkout of the bound revision instead."
        )
