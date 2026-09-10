"""Authenticated, read-only historical source snapshots for Plan 11.26 replay (Seam 2, R16-B).

Why this exists. The accepted audit artifact binds its historical findings to an OVERLAY commit that
is not an ancestor of ``main`` and is published on no branch: it exists only in the object stores of
the machines the audit was taken on. Every historical replay route (verify, render, the cumulative
artifact commands, successor verification) reads a fixed, declared set of source paths from that
commit through :class:`GitCommitSource`, so a fresh clone -- GitHub's included -- fails with
``git rev-parse`` exit 128. Publishing the historical branch merely to satisfy CI would disclose a
tree and history nobody has reviewed; repinning the artifact, mocking resolution or skipping the
tests would falsify the evidence.

What this is. Exactly the historical source paths those routes read, shipped as repository data
together with the proof that they are the bytes of THAT commit: the raw commit object, every tree
object on the path from the commit's root tree down to each blob, and the blobs themselves. Nothing
here is imported, executed or installed; it is source TEXT for static replay, and only for the one
identity pinned in :data:`HISTORICAL_SNAPSHOTS`.

How it is trusted. The snapshot identity -- commit id, root tree id, the manifest's SHA-256 and a
SHA-256 content digest over every (path, blob bytes) pair -- is pinned in THIS module, never taken
from the manifest or from an artifact. The manifest itself carries no digests (it lists paths, modes
and sizes), so no scanned text file holds a high-entropy string; every blob id is DERIVED from the
verified tree chain. On load, the manifest's bytes must hash to the pin; the commit object must hash
(the way Git hashes objects) to the pinned commit and name the pinned root tree; every requested path
is resolved by walking tree objects component by component, each tree object re-hashed to the id its
parent names and each entry's mode checked, and the final blob re-hashed to the tree entry's id; the
whole scope is additionally bound to the pinned content digest. A tampered byte, a swapped proof, an
omitted object, an extra or escaping path, or an unknown identity is refused -- there is no fallback
to a live repository and no partial answer.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "plan1126_runtime_audit" / "historical-source"
_SCHEMA = "plan1126-historical-source-snapshot/2"
_BLOB_MODES = frozenset({"100644", "100755"})


class HistoricalSourceError(LookupError):
    """The snapshot cannot supply a path with verified provenance. Never downgraded."""


@dataclass(frozen=True)
class SnapshotIdentity:
    """The reviewed identity of one snapshot, pinned in code."""

    commit: str
    tree: str
    manifest_sha256: str
    content_sha256: str
    directory: str


#: Every historical replay identity this repository can serve without live Git objects. Keyed by the
#: exact 40-hex commit id; :func:`historical_source` dispatches on this map and nothing else. The
#: values are commit-identity, tree-identity and snapshot-digest pins, not credentials.
_OVERLAY_COMMIT = "fac32284888850bacde93815265cbabe3afd4663"  # pragma: allowlist secret - historical commit-identity pin
HISTORICAL_SNAPSHOTS: Mapping[str, SnapshotIdentity] = {
    _OVERLAY_COMMIT: SnapshotIdentity(
        commit=_OVERLAY_COMMIT,
        tree="f7e79706f5487a7d853d60eff3f576c5dec59e72",  # pragma: allowlist secret - historical tree-identity pin
        manifest_sha256="9089cb06e9ef89ecc9d7fdd3910570ffca23004c16546937293b5e6362bb9868",  # pragma: allowlist secret - snapshot manifest pin
        content_sha256="c2e2862d73a8796aad9e1434da044a9e9d062c953cfaa45d0043ab5b19c5ade6",  # pragma: allowlist secret - snapshot content pin
        directory=_OVERLAY_COMMIT,
    ),
}


def _git_object_id(kind: str, content: bytes) -> str:
    return hashlib.sha1(f"{kind} {len(content)}".encode("ascii") + b"\0" + content).hexdigest()  # noqa: S324 - Git object identity, not a security digest


def _parse_tree(content: bytes) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    index = 0
    while index < len(content):
        separator = content.index(b"\0", index)
        mode, name = content[index:separator].decode("utf-8").split(" ", 1)
        entries.append((mode, name, content[separator + 1 : separator + 21].hex()))
        index = separator + 21
    return entries


def _validate_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts or not pure.parts:
        raise HistoricalSourceError(f"{path!r}: path must be repository-relative")
    return pure.as_posix()


class HistoricalSourceSnapshot:
    """A source tree served from an authenticated snapshot of ONE historical commit.

    Exposes the same read-only surface the replay routes use (``commit``, ``paths()``,
    ``read_text()``); ``paths()`` is the snapshot's declared scope, not the whole historical tree,
    and reading outside that scope is refused.
    """

    def __init__(self, identity: SnapshotIdentity, root: Path | None = None) -> None:
        self.identity = identity
        self.commit = identity.commit
        self._root = (root if root is not None else _FIXTURE_ROOT) / identity.directory
        # The manifest and the object files are text in the repository, so a checkout may rewrite
        # their line endings; identity is therefore taken over LF-normalized bytes (the manifest)
        # and over the base64 payload with surrounding whitespace removed (objects). The decoded
        # Git object bytes are never normalized -- they must hash to their ids exactly.
        manifest_bytes = self._read_file(self._root / "manifest.json").replace(b"\r\n", b"\n")
        if hashlib.sha256(manifest_bytes).hexdigest() != identity.manifest_sha256:
            raise HistoricalSourceError(f"{identity.commit}: snapshot manifest does not match its pinned identity")
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        if manifest.get("schema") != _SCHEMA:
            raise HistoricalSourceError(f"{identity.commit}: snapshot manifest has an unknown schema")
        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            raise HistoricalSourceError(f"{identity.commit}: snapshot declares no files")
        self._files: dict[str, Mapping[str, object]] = {}
        for path, row in files.items():
            relative = _validate_relative_path(path)
            if relative in self._files:
                raise HistoricalSourceError(f"{identity.commit}: duplicate snapshot path {relative!r}")
            self._files[relative] = row
        self._objects: dict[str, bytes] = {}
        self._root_tree = self._verify_commit()
        self._content_verified = False

    # -- provenance ---------------------------------------------------------------

    def _read_file(self, path: Path) -> bytes:
        try:
            return path.read_bytes()
        except OSError as exc:
            raise HistoricalSourceError(f"{self.commit}: snapshot file missing: {path.name}") from exc

    def _object(self, kind: str, object_id: str) -> bytes:
        cached = self._objects.get(object_id)
        if cached is not None:
            return cached
        if len(object_id) != 40 or any(ch not in "0123456789abcdef" for ch in object_id):
            raise HistoricalSourceError(f"{self.commit}: malformed object id {object_id!r}")
        encoded = self._read_file(self._root / "objects" / f"{object_id}.b64")
        try:
            content = base64.b64decode(encoded.strip(), validate=True)
        except (ValueError, TypeError) as exc:
            raise HistoricalSourceError(f"{self.commit}: snapshot object {object_id} is not valid base64") from exc
        if _git_object_id(kind, content) != object_id:
            raise HistoricalSourceError(f"{self.commit}: snapshot {kind} object {object_id} does not hash to its id")
        self._objects[object_id] = content
        return content

    def _verify_commit(self) -> str:
        content = self._object("commit", self.commit)
        first = content.split(b"\n", 1)[0].decode("utf-8", "replace")
        if not first.startswith("tree ") or first[5:] != self.identity.tree:
            raise HistoricalSourceError(f"{self.commit}: commit object does not name the pinned root tree")
        return self.identity.tree

    def _resolve(self, relative: str) -> tuple[str, str, bytes]:
        """Walk the verified tree chain for ``relative``; returns (mode, blob id, blob bytes)."""
        row = self._files.get(relative)
        if row is None:
            raise HistoricalSourceError(f"{self.commit}: {relative!r} is outside this snapshot's declared scope")
        tree_id = self._root_tree
        parts = relative.split("/")
        for depth, part in enumerate(parts):
            entries = [entry for entry in _parse_tree(self._object("tree", tree_id)) if entry[1] == part]
            if len(entries) != 1:
                raise HistoricalSourceError(f"{self.commit}: {relative!r} is not present exactly once in the historical tree")
            mode, _name, object_id = entries[0]
            if depth < len(parts) - 1:
                if mode != "40000":
                    raise HistoricalSourceError(f"{self.commit}: {relative!r} crosses a non-directory entry")
                tree_id = object_id
                continue
            if mode not in _BLOB_MODES or mode != row.get("mode"):
                raise HistoricalSourceError(f"{self.commit}: {relative!r} mode does not match the manifest")
            blob = self._object("blob", object_id)
            if len(blob) != row.get("size"):
                raise HistoricalSourceError(f"{self.commit}: {relative!r} size does not match the manifest")
            return mode, object_id, blob
        raise HistoricalSourceError(f"{self.commit}: {relative!r} could not be resolved")  # pragma: no cover - loop always returns or raises

    def _verify_content_digest(self) -> None:
        """Bind the WHOLE declared scope to the pinned SHA-256 content digest (independent of Git's SHA-1)."""
        if self._content_verified:
            return
        digest = hashlib.sha256()
        for path in self.paths():
            digest.update(path.encode("utf-8") + b"\0" + self._resolve(path)[2] + b"\0")
        if digest.hexdigest() != self.identity.content_sha256:
            raise HistoricalSourceError(f"{self.commit}: snapshot content does not match its pinned content digest")
        self._content_verified = True

    # -- the SourceTree surface -----------------------------------------------------

    def paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._files))

    def read_bytes(self, path: str) -> bytes:
        relative = _validate_relative_path(path)
        self._verify_content_digest()
        return self._resolve(relative)[2]

    def read_text(self, path: str) -> str:
        text = self.read_bytes(path).decode("utf-8")
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def verify_all(self) -> dict[str, str]:
        """Resolve every declared path with full provenance; returns path -> verified blob id."""
        self._verify_content_digest()
        return {path: self._resolve(path)[1] for path in self.paths()}


def historical_source(commit: str, repository: Path | str = ".", *, root: Path | None = None):
    """Explicit dispatch for historical replay identities.

    A commit that is a pinned snapshot identity is served from the authenticated snapshot -- whether
    or not a live repository could also resolve it, so Git-present and Git-absent runs read the same
    bytes. Anything else is an ordinary :class:`GitCommitSource`, strict as before; there is no
    fallback from a failed Git resolution to a snapshot.
    """
    from .source import GitCommitSource

    normalized = commit.strip().lower()
    identity = HISTORICAL_SNAPSHOTS.get(normalized)
    if identity is not None:
        return HistoricalSourceSnapshot(identity, root=root)
    return GitCommitSource(commit, repository=repository)
