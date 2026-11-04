"""The host's side of the context index (Plan 12.10 Task 3; ADR-037): it binds the scope and authorizes every read.

Scope comes only from here: the registered project, this worktree, its branch and the versions that change what a record means.
The model cannot name one. Reads go through `FilePolicy` for the index purpose, so an excluded file is never parsed. Storage goes
through the Gateway's route with the host's existing URL and key; this process holds no Redis secret. The embedder loads the
configured artifact from disk with no network and no new credential; without it, the feature reports why and keeps today's context.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from context_engine.index_worker import SCHEMA_VERSION, IndexSource, SourceFile, StorageRefusedError, StorageUnavailableError
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context.project_registry import ProjectRegistration
from optimus.guardrails.file_policy import POLICY_VERSION, FilePolicy, FilePurpose, reachable_path
from optimus.usage.savings_report import ReportTransportError, gateway_post
from optimus_security import memory_index_contract as mic
from optimus_security.memory_index_config import ARTIFACTS_NAME, EmbeddingConfig, artifact_digest

_GIT_SECONDS = 10.0
_DETACHED = "(detached)"
_NO_GIT = "(no-git)"


class EmbedderUnavailableError(RuntimeError):
    """The configured artifact cannot be used. `code` is stable."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _git(root: Path, *args: str) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run([git, "-c", "core.longpaths=true", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=_GIT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def current_branch(root: Path) -> str:
    """The branch name, a marker for a detached HEAD, or a marker outside Git. Two branches never share a scope."""
    head = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    if head:
        return head.strip()
    return _DETACHED if _git(root, "rev-parse", "HEAD") else _NO_GIT


def index_scope(registration: ProjectRegistration, *, branch: str, embedding: str, parser_version: str) -> str:
    """One index line. Clones have different registrations, worktrees and branches different inputs, so they stay apart; changing a
    version starts a new line rather than mixing meanings. Revision and dirty state are published inside the line, and a changed
    ignore file is reconciled inside it, so editing one does not rebuild the index."""
    material = {"project": registration.project_id, "worktree": registration.worktree, "branch": branch, "embedding": embedding,
                "file_policy": POLICY_VERSION, "parser": parser_version, "schema": SCHEMA_VERSION}
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


class WorkspaceIndexSource(IndexSource):
    def __init__(self, policy: FilePolicy) -> None:
        self._policy = policy
        self._unreachable = 0
        self._listing: tuple[str, ...] | None = None

    def files(self) -> Iterable[SourceFile]:
        unreachable = 0
        listed: list[str] = []
        for decision in self._policy.walk(purpose=FilePurpose.INDEX):
            if decision.allowed:
                listed.append(decision.relative_path)
                yield SourceFile(decision.relative_path, self._modified(decision.relative_path))
            elif decision.reason == "excluded.unreadable":
                unreachable += 1
        self._unreachable = unreachable
        self._listing = tuple(listed)

    def listing(self, *, fresh: bool = False) -> tuple[str, ...]:
        """The admitted files as of the last whole walk, or a walk now if there has been none or `fresh` asks for one. Paths only."""
        if fresh or self._listing is None:
            self._listing = tuple(decision.relative_path for decision in self._policy.walk(purpose=FilePurpose.INDEX) if decision.allowed)
        return self._listing

    def unreachable(self) -> int:
        return self._unreachable

    def _modified(self, path: str) -> int | None:
        try:
            return int(os.stat(reachable_path(self._policy.root / path)).st_mtime)
        except OSError:
            return None

    def read(self, path: str) -> bytes | None:
        decision, data = self._policy.read(path, purpose=FilePurpose.INDEX)
        return data if decision.allowed else None

    def revision(self) -> tuple[str, bool]:
        """What a pass read, and whether it differs from a commit. Git's status names changed paths, not their contents, so each admitted
        file's size and modified time go in too; the worker's own check of the bytes is what decides `complete`. Inside a repository Git
        cannot read, including from a folder beneath its root, the answer is new each time, so no pass there is called complete."""
        root = self._policy.root
        status = _git(root, "status", "--porcelain=v1", "--untracked-files=normal")
        if status is None and any((folder / ".git").exists() for folder in (root, *root.resolve().parents)):
            return secrets.token_hex(32), True
        head = (_git(root, "rev-parse", "HEAD") or "").strip()
        contents = hashlib.sha256()
        for item in self.files():
            try:
                facts = os.stat(reachable_path(root / item.path))
            except OSError:
                continue
            contents.update(f"{item.path}\0{facts.st_size}\0{facts.st_mtime_ns}\0".encode())
        return hashlib.sha256(f"{head}\0{status}\0{contents.hexdigest()}".encode()).hexdigest(), status is None or bool(status.strip())


class GatewayIndexStorage:
    """The route, through the host's own Gateway URL and key, so the attach identity binds this traffic too."""

    def __init__(self, settings: OptimusGatewaySettings, *, scope: str, post: Callable[..., Callable[[bytes], tuple[int, Any]]] = gateway_post) -> None:
        self._scope = scope
        self._post = post(settings, timeout=mic.DEADLINE_SECONDS + 2.0, path=mic.PATH)

    def call(self, op: str, **fields: Any) -> dict[str, Any]:
        body = json.dumps({"op": op, "scope": fields.pop("scope", self._scope), **fields}, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        try:
            status, reply = self._post(body)
        except (ReportTransportError, OSError) as exc:
            raise StorageUnavailableError("the index route cannot be reached") from exc
        if status == 200 and isinstance(reply, Mapping):
            return dict(reply)
        code = reply.get("error") if isinstance(reply, Mapping) else None
        if status in {502, 503, 504} or code is None:
            raise StorageUnavailableError(str(code or f"status {status}"))
        raise StorageRefusedError(str(code))


class FastembedEmbedder:
    """The configured artifact, loaded offline and checked against its digest first. Two native threads at most."""

    def __init__(self, memory_root: Path, config: EmbeddingConfig, *, directory: str, threads: int = 2) -> None:
        artifact = memory_root / ARTIFACTS_NAME / directory
        if not artifact.is_dir():
            raise EmbedderUnavailableError("EMBEDDING_ARTIFACT_MISSING")
        if artifact_digest(artifact) != config.artifact_sha256:
            raise EmbedderUnavailableError("EMBEDDING_ARTIFACT_CHANGED")
        try:
            from fastembed import TextEmbedding  # noqa: PLC0415 - optional package
        except ImportError as exc:
            raise EmbedderUnavailableError("MEMORY_PACKAGES_MISSING") from exc
        self.identity = f"{config.model}@{config.revision[:12]}"
        self.dimensions = config.dimensions
        self._model = TextEmbedding(config.model, cache_dir=str(memory_root / ARTIFACTS_NAME), specific_model_path=str(artifact), threads=threads, local_files_only=True)

    def embed(self, texts: Sequence[str]) -> list[bytes]:
        vectors = list(self._model.embed(list(texts), batch_size=len(texts) or 1))
        return [vector.astype("<f4").tobytes() for vector in vectors]
