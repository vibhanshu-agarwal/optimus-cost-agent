"""Plan 12.10 Task 2: the host's binding of scope, its reading of the route's answers, and the embedder's refusals, without Redis or a model."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from context_engine.index_worker import StorageRefusedError, StorageUnavailableError
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context import memory_workspace
from optimus.context.memory_workspace import (
    EmbedderUnavailableError,
    FastembedEmbedder,
    GatewayIndexStorage,
    WorkspaceIndexSource,
    current_branch,
    index_scope,
)
from optimus.context.project_registry import ProjectRegistration
from optimus.guardrails import file_policy
from optimus.guardrails.file_policy import FilePolicy
from optimus.usage.savings_report import ReportTransportError
from optimus_security.memory_index_config import ARTIFACTS_NAME, EmbeddingConfig, artifact_digest

_SETTINGS = OptimusGatewaySettings.from_env({"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9", "OPTIMUS_API_KEY": "k"})


def _config(digest: str) -> EmbeddingConfig:
    return EmbeddingConfig(model="test/model", source="test", revision="abc", licence="MIT", dimensions=8, max_input_tokens=16, artifact_sha256=digest)


def _artifact(root: Path) -> Path:
    artifact = root / ARTIFACTS_NAME / "model"
    artifact.mkdir(parents=True)
    (artifact / "model.onnx").write_bytes(b"weights")
    return artifact


def test_every_input_that_changes_a_records_meaning_changes_the_scope() -> None:
    def scope(project: str = "p", worktree: str = "w", branch: str = "main", embedding: str = "e", parser: str = "1") -> str:
        return index_scope(ProjectRegistration(project, 1, f"git:{project}", worktree, created=False), branch=branch, embedding=embedding, parser_version=parser)

    variants = [scope(), scope(project="q"), scope(worktree="x"), scope(branch="other"), scope(embedding="f"), scope(parser="2")]
    assert len(set(variants)) == len(variants)
    assert scope() == variants[0]


def test_outside_git_a_branch_is_a_marker_and_not_an_error(tmp_path: Path) -> None:
    assert current_branch(tmp_path) == "(no-git)"


@pytest.mark.parametrize(
    ("status", "reply", "error", "code"),
    [
        (503, {"error": "INDEX_UNAVAILABLE"}, StorageUnavailableError, None),
        (502, "not json", StorageUnavailableError, None),
        (409, {"error": "LEASE_LOST"}, StorageRefusedError, "LEASE_LOST"),
        (404, {"error": "NOT_PUBLISHED"}, StorageRefusedError, "NOT_PUBLISHED"),
    ],
    ids=["outage", "no-code", "fenced", "refused"],
)
def test_the_route_answers_map_to_pause_or_refusal(status: int, reply: Any, error: type[Exception], code: str | None) -> None:
    storage = GatewayIndexStorage(_SETTINGS, scope="ab" * 32, post=lambda *_a, **_k: lambda _body: (status, reply))
    with pytest.raises(error) as raised:
        storage.call("coverage")
    assert code is None or raised.value.code == code  # type: ignore[attr-defined]


def test_a_transport_failure_pauses() -> None:
    def fail(_body: bytes) -> tuple[int, Any]:
        raise ReportTransportError("no route")

    with pytest.raises(StorageUnavailableError):
        GatewayIndexStorage(_SETTINGS, scope="ab" * 32, post=lambda *_a, **_k: fail).call("coverage")


def test_the_model_cannot_choose_the_scope_but_the_host_can_name_it() -> None:
    bodies: list[bytes] = []

    def post(body: bytes) -> tuple[int, Any]:
        bodies.append(body)
        return 200, {"status": "ok"}

    GatewayIndexStorage(_SETTINGS, scope="ab" * 32, post=lambda *_a, **_k: post).call("coverage")
    assert b'"scope":"' + b"ab" * 32 + b'"' in bodies[0]


def test_no_artifact_is_a_stable_refusal_with_no_download(tmp_path: Path) -> None:
    with pytest.raises(EmbedderUnavailableError) as raised:
        FastembedEmbedder(tmp_path, _config("0" * 64), directory="model")
    assert raised.value.code == "EMBEDDING_ARTIFACT_MISSING"


def test_a_changed_artifact_is_refused_before_anything_loads_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = _artifact(tmp_path)
    digest = artifact_digest(artifact)
    (artifact / "model.onnx").write_bytes(b"other weights")
    monkeypatch.setitem(sys.modules, "fastembed", None)  # a load would say MEMORY_PACKAGES_MISSING instead
    with pytest.raises(EmbedderUnavailableError) as raised:
        FastembedEmbedder(tmp_path, _config(digest), directory="model")
    assert raised.value.code == "EMBEDDING_ARTIFACT_CHANGED"


def test_absent_packages_are_a_stable_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = _artifact(tmp_path)
    monkeypatch.setitem(sys.modules, "fastembed", None)
    with pytest.raises(EmbedderUnavailableError) as raised:
        FastembedEmbedder(tmp_path, _config(artifact_digest(artifact)), directory="model")
    assert raised.value.code == "MEMORY_PACKAGES_MISSING"


def test_importing_the_host_side_needs_no_optional_package() -> None:
    assert "fastembed" not in vars(memory_workspace)


def _source(root: Path) -> memory_workspace.WorkspaceIndexSource:
    return memory_workspace.WorkspaceIndexSource(FilePolicy(root))


def test_a_repository_git_cannot_read_never_repeats_a_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    source = _source(tmp_path)
    monkeypatch.setattr(memory_workspace, "_git", lambda *_a, **_k: None)
    first, second = source.revision(), source.revision()
    assert first[0] != second[0] and first[1] is True


def test_outside_git_the_revision_follows_the_files_and_counts_as_dirty(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    source = _source(tmp_path)
    first = source.revision()
    assert source.revision() == first and first[1] is True
    (tmp_path / "a.py").write_text("x = 22\n", encoding="utf-8")
    assert source.revision()[0] != first[0]
    (tmp_path / "b.py").write_text("y = 1\n", encoding="utf-8")
    assert source.revision()[0] != first[0]


def test_a_folder_beneath_a_repository_git_cannot_read_never_repeats_a_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    source = _source(tmp_path / "pkg")
    monkeypatch.setattr(memory_workspace, "_git", lambda *_a, **_k: None)
    assert source.revision()[0] != source.revision()[0]


@pytest.mark.skipif(sys.platform != "win32", reason="the path length limit is a Windows mechanism")
def test_past_the_path_limit_the_revision_follows_the_file_and_git_reads_the_repository(tmp_path: Path) -> None:
    relative = "/".join(["a_folder_named_long_enough_to_add_up"] * 10) + "/deep.py"
    full = file_policy._extended(str(tmp_path.joinpath(*relative.split("/"))))
    os.makedirs(os.path.dirname(full))
    with open(full, "w", encoding="utf-8") as stream:
        stream.write("x = 1\n")
    git = ["git", "-C", str(tmp_path), "-c", "core.longpaths=true", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "one"], check=True)
    source = _source(tmp_path)
    try:
        _first, dirty = source.revision()
        assert dirty is False, "a tracked file past the limit is not a deletion"
        assert [item.path for item in source.files()] == [relative]
        with open(full, "w", encoding="utf-8") as stream:
            stream.write("x = 22\n")
        edited, dirty = source.revision()
        assert dirty is True
        with open(full, "w", encoding="utf-8") as stream:  # already dirty, so only the file's own facts can show this
            stream.write("x = 333\n")
        assert source.revision()[0] != edited
    finally:
        shutil.rmtree(file_policy._extended(str(tmp_path / "a_folder_named_long_enough_to_add_up")))


def test_a_folder_the_listing_could_not_read_is_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "locked").mkdir()
    (tmp_path / "locked" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 1\n", encoding="utf-8")
    source = _source(tmp_path)
    assert [item.path for item in source.files()] == ["b.py", "locked/a.py"] and source.unreachable() == 0
    real = os.scandir
    monkeypatch.setattr(file_policy.os, "scandir", lambda path: (_ for _ in ()).throw(PermissionError(path)) if os.path.basename(path) == "locked" else real(path))
    assert [item.path for item in source.files()] == ["b.py"] and source.unreachable() == 1


def test_a_revision_reads_no_files_bytes_but_follows_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.py").write_text("one\n", encoding="utf-8")
    source = WorkspaceIndexSource(FilePolicy(tmp_path))
    before = source.revision()
    (tmp_path / "a.py").write_text("two more\n", encoding="utf-8")

    def refuse(*_args: Any) -> None:
        raise AssertionError("a file was read")

    monkeypatch.setattr(file_policy, "_read_validated", refuse)
    assert source.revision() != before


def test_disk_facts_count_a_file_too_large_to_index(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    policy = FilePolicy(tmp_path, max_index_file_bytes=10)
    assert WorkspaceIndexSource(policy).disk_facts()[1] == 0
    (tmp_path / "big.py").write_text("y = 1\n" * 10, encoding="utf-8")
    source = WorkspaceIndexSource(policy)
    revision, too_large = source.disk_facts()
    assert too_large == 1 and revision == source.revision()[0]
