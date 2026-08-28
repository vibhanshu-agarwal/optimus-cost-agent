"""Mechanical proof that a frozen plan's post-archival content differs from
its originally approved bytes by exactly a registered set of path
replacements -- nothing else.

This lets a digest re-pin for an archived, frozen document be verified by
execution rather than trusted by assertion: apply only the registered
replacements to the approved original blob and require byte-for-byte
equality with the actual committed destination blob.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Replacement:
    """One exact-count string substitution, applied in registration order."""

    search: str
    replace: str
    expected_count: int


@dataclass(frozen=True)
class RelocationEquivalence:
    """Proves a frozen document's post-move bytes are a pure path repair.

    `source_commit`/`original_path` name the git blob that carried the
    originally approved bytes (`approved_original_sha256`). Applying
    `replacements`, in order, must reproduce `expected_new_sha256` and must
    byte-for-byte equal the committed blob at `destination_path` on HEAD.
    """

    source_commit: str
    original_path: str
    destination_path: str
    approved_original_sha256: str
    replacements: tuple[Replacement, ...]
    expected_new_sha256: str


# Populated by the document-repair lane as each frozen archived document's
# stale relative links are mechanically repaired. Every entry here is
# mechanically checked, not merely asserted, by
# test_registered_relocations_are_pure_path_repairs below.
RELOCATION_EQUIVALENCES: tuple[RelocationEquivalence, ...] = ()


def test_registered_relocations_are_pure_path_repairs() -> None:
    for entry in RELOCATION_EQUIVALENCES:
        _assert_relocation_equivalence(entry)


def _git_blob(commit: str, relative_path: str, *, repo_root: Path = REPO_ROOT) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return result.stdout


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _apply_replacements(original: bytes, replacements: tuple[Replacement, ...]) -> bytes:
    text = original.decode("utf-8")
    for replacement in replacements:
        actual_count = text.count(replacement.search)
        assert actual_count == replacement.expected_count, (
            f"expected {replacement.expected_count} occurrence(s) of "
            f"{replacement.search!r}, found {actual_count}"
        )
        text = text.replace(replacement.search, replacement.replace)
    return text.encode("utf-8")


def _assert_relocation_equivalence(entry: RelocationEquivalence, *, repo_root: Path = REPO_ROOT) -> None:
    original = _git_blob(entry.source_commit, entry.original_path, repo_root=repo_root)
    assert _sha256(original) == entry.approved_original_sha256, (
        f"{entry.original_path} at {entry.source_commit} no longer matches its "
        "approved digest; the source-of-truth blob moved"
    )

    repaired = _apply_replacements(original, entry.replacements)
    assert _sha256(repaired) == entry.expected_new_sha256, (
        f"applying the registered replacements to {entry.original_path} does not "
        f"reproduce the expected new digest for {entry.destination_path}"
    )

    destination = _git_blob("HEAD", entry.destination_path, repo_root=repo_root)
    assert destination == repaired, (
        f"{entry.destination_path} differs from its approved original by more than "
        "the registered path replacements"
    )


def _init_git_fixture(repo_root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Hygiene Test"], cwd=repo_root, check=True)


def _commit_file(repo_root: Path, relative_path: str, content: bytes, message: str) -> str:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    subprocess.run(["git", "add", relative_path], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo_root, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_relocation_equivalence_accepts_a_pure_path_repair(tmp_path: Path) -> None:
    _init_git_fixture(tmp_path)
    original = b"See ../plans/x.md for detail.\nSee ../plans/x.md again.\n"
    source_commit = _commit_file(tmp_path, "spec.md", original, "seed")
    replacements = (Replacement("../plans/x.md", "../plans/archive/x.md", 2),)
    repaired = _apply_replacements(original, replacements)
    _commit_file(tmp_path, "spec-archive.md", repaired, "move with repair")

    entry = RelocationEquivalence(
        source_commit=source_commit,
        original_path="spec.md",
        destination_path="spec-archive.md",
        approved_original_sha256=_sha256(original),
        replacements=replacements,
        expected_new_sha256=_sha256(repaired),
    )

    _assert_relocation_equivalence(entry, repo_root=tmp_path)  # must not raise


def test_relocation_equivalence_rejects_an_unregistered_byte_change(tmp_path: Path) -> None:
    _init_git_fixture(tmp_path)
    original = b"See ../plans/x.md for detail.\n"
    source_commit = _commit_file(tmp_path, "spec.md", original, "seed")
    replacements = (Replacement("../plans/x.md", "../plans/archive/x.md", 1),)
    # Destination has the registered path repair AND an extra, unregistered
    # content edit -- the predicate must catch this, not just the path fix.
    drifted = _apply_replacements(original, replacements).replace(b"detail", b"full detail")
    _commit_file(tmp_path, "spec-archive.md", drifted, "move with unregistered drift")

    entry = RelocationEquivalence(
        source_commit=source_commit,
        original_path="spec.md",
        destination_path="spec-archive.md",
        approved_original_sha256=_sha256(original),
        replacements=replacements,
        expected_new_sha256=_sha256(_apply_replacements(original, replacements)),
    )

    with pytest.raises(AssertionError, match="differs from its approved original"):
        _assert_relocation_equivalence(entry, repo_root=tmp_path)


def test_relocation_equivalence_rejects_a_wrong_occurrence_count(tmp_path: Path) -> None:
    _init_git_fixture(tmp_path)
    original = b"See ../plans/x.md for detail.\nSee ../plans/x.md again.\n"
    source_commit = _commit_file(tmp_path, "spec.md", original, "seed")
    # Registered count (1) doesn't match the real occurrence count (2) --
    # this must fail loudly rather than silently under- or over-replacing.
    entry = RelocationEquivalence(
        source_commit=source_commit,
        original_path="spec.md",
        destination_path="spec.md",
        approved_original_sha256=_sha256(original),
        replacements=(Replacement("../plans/x.md", "../plans/archive/x.md", 1),),
        expected_new_sha256="irrelevant",
    )

    with pytest.raises(AssertionError, match="expected 1 occurrence"):
        _assert_relocation_equivalence(entry, repo_root=tmp_path)


def test_relocation_equivalence_rejects_a_stale_approved_digest(tmp_path: Path) -> None:
    _init_git_fixture(tmp_path)
    original = b"See ../plans/x.md for detail.\n"
    source_commit = _commit_file(tmp_path, "spec.md", original, "seed")
    entry = RelocationEquivalence(
        source_commit=source_commit,
        original_path="spec.md",
        destination_path="spec.md",
        approved_original_sha256="0" * 64,  # deliberately wrong
        replacements=(Replacement("../plans/x.md", "../plans/archive/x.md", 1),),
        expected_new_sha256="irrelevant",
    )

    with pytest.raises(AssertionError, match="no longer matches its"):
        _assert_relocation_equivalence(entry, repo_root=tmp_path)
