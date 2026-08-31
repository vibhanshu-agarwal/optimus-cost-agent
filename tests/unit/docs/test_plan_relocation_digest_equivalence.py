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


# Each entry records the originally approved blob at the archive-move base,
# exact path-only substitutions, and the resulting re-pinned blob. Evidence
# artifacts remain immutable; these are only frozen Markdown path repairs.
RELOCATION_EQUIVALENCES: tuple[RelocationEquivalence, ...] = (
    RelocationEquivalence(
        source_commit="63b5d8f7853c57030426a01776905b0c521f1036",
        original_path="docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md",
        destination_path="docs/superpowers/plans/archive/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md",
        approved_original_sha256="106FD92B8E43F44A7115D7EDB1F9CF1E3EE643E4B6F594FA656FB4119A969B82",
        replacements=(
            Replacement(
                "2026-07-23-consolidated-deferred-followups-backlog.md#p11-fu-11-plan-117-retry-preflight-and-live-session-proof",
                "../2026-07-23-consolidated-deferred-followups-backlog.md#p11-fu-11-plan-117-retry-preflight-and-live-session-proof",
                1,
            ),
            Replacement(
                "../specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md",
                "../../specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md",
                1,
            ),
        ),
        expected_new_sha256="0AA1007309C26B072A37310F01B65B38E874A88625B9DF1215C0C61EA7620B2B",
    ),
    RelocationEquivalence(
        source_commit="63b5d8f7853c57030426a01776905b0c521f1036",
        original_path="docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md",
        destination_path="docs/superpowers/plans/archive/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md",
        approved_original_sha256="B5E2ACB08A35CF42D2D8AC83762D4EB1021461786B30EDB1C7615CBCD159728D",
        replacements=(
            Replacement(
                "2026-07-23-consolidated-deferred-followups-backlog.md#durable-effect-aware-mcp-indeterminate-call-custody",
                "../2026-07-23-consolidated-deferred-followups-backlog.md#durable-effect-aware-mcp-indeterminate-call-custody",
                1,
            ),
        ),
        expected_new_sha256="213744ECB6580B4A47BC61ED8D4B331724D4A05F50A23DFF6FAC9D137C99ACBA",
    ),
    RelocationEquivalence(
        source_commit="63b5d8f7853c57030426a01776905b0c521f1036",
        original_path="docs/superpowers/plans/2026-08-07-open-work-pool-status-normalization-implementation.md",
        destination_path="docs/superpowers/plans/archive/2026-08-07-open-work-pool-status-normalization-implementation.md",
        approved_original_sha256="7B719F23E7C716F744AC52BA21FE7114C329089B28218704BD0D351DC7E5C7F8",
        replacements=(
            Replacement(
                "../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json",
                "../../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json",
                3,
            ),
            Replacement(
                "../../../reports/p11-fu-9-client-mcp-closure-evidence.md",
                "../../../../reports/p11-fu-9-client-mcp-closure-evidence.md",
                1,
            ),
            Replacement(
                "../../runbooks/local-live-dependencies.md",
                "../../../runbooks/local-live-dependencies.md",
                1,
            ),
        ),
        expected_new_sha256="CC82FEA8DD6421FE33BE95853F2372F34AABB140082F86844D757802EC9C1051",
    ),
    RelocationEquivalence(
        source_commit="63b5d8f7853c57030426a01776905b0c521f1036",
        original_path="docs/superpowers/plans/evidence-handoff-open-work-pool.md",
        destination_path="docs/superpowers/plans/archive/evidence-handoff-open-work-pool.md",
        approved_original_sha256="D1973E5B6CDC1FB9629BDAEA572C6550F4FC3C5238AE71D10D23AD364EF808F5",
        replacements=(
            Replacement(
                "../specs/evidence-handoff-zed-render-observation-design.md",
                "../../specs/evidence-handoff-zed-render-observation-design.md",
                1,
            ),
            Replacement(
                "../specs/evidence-handoff-redaction-gate-design.md",
                "../../specs/evidence-handoff-redaction-gate-design.md",
                1,
            ),
            Replacement(
                "](evidence-handoff-evidence-collector-implementation.md)",
                "](../evidence-handoff-evidence-collector-implementation.md)",
                2,
            ),
            Replacement(
                "../specs/evidence-handoff-evidence-collector-design.md",
                "../../specs/evidence-handoff-evidence-collector-design.md",
                1,
            ),
            Replacement(
                "../specs/evidence-handoff-a2a-ledger-design.md",
                "../../specs/evidence-handoff-a2a-ledger-design.md",
                2,
            ),
            Replacement(
                "../specs/evidence-handoff-a2a-ledger-remediation-scoping.md",
                "../../specs/evidence-handoff-a2a-ledger-remediation-scoping.md",
                1,
            ),
        ),
        expected_new_sha256="7157F28D215D86C201028F3A3D72B645E8D69DBA5AF99D1A60C42CCB587EF182",
    ),
    RelocationEquivalence(
        source_commit="63b5d8f7853c57030426a01776905b0c521f1036",
        original_path="docs/superpowers/specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md",
        destination_path="docs/superpowers/specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md",
        approved_original_sha256="EB34FA10148CE813A03E60E0770116ABA4AC9857E4DFBEE87E00C39BFDB0D392",
        replacements=(
            Replacement(
                "../plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md",
                "../plans/archive/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md",
                1,
            ),
        ),
        expected_new_sha256="3D4FBA5BE86399F4FD7CABB319847A847A06394BE2CEEB5D795952C2901EB90E",
    ),
    RelocationEquivalence(
        source_commit="547d88741ed54617251f83059ea100f0292d8fcd",
        original_path="docs/superpowers/plans/2026-08-29-plan-11-26-acp-runtime-hardening-audit-implementation.md",
        destination_path="docs/superpowers/plans/archive/2026-08-29-plan-11-26-acp-runtime-hardening-audit-implementation.md",
        approved_original_sha256="5D24670EE0516C089283065B2E52E8F719004CF951A3C5351BB06400C738F33D",
        replacements=(),
        expected_new_sha256="5D24670EE0516C089283065B2E52E8F719004CF951A3C5351BB06400C738F33D",
    ),
)


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
