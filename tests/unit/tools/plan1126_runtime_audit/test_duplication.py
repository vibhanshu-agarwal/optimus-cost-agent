"""Task 13 behavior tests for immutable-tree duplication discovery and custody."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit.duplication import (
    DEFAULT_PRIOR_SEEDS,
    DEFAULT_SCOPE,
    canonical_json_bytes,
    discover_duplication_candidates,
    render_duplication_markdown,
    verify_duplication_audit,
)
from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree
from tools.run_plan1126_runtime_audit import main as audit_cli_main

_ROOT = Path(__file__).resolve().parents[4]
_PINNED_COMMIT = "b62462f11abe858f58af12fa2d2f159eae09d832"
_SCHEMA_DIR = _ROOT / "tests" / "fixtures" / "plan1126_runtime_audit"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _scope_fixture() -> SourceTree:
    copied = "def normalized(value):\n    cleaned = value.strip()\n    return cleaned.lower()\n"
    return SourceTree(
        {
            "src/optimus/core.py": copied,
            "src/optimus/other.py": copied,
            "src/evidence_handoff/collector/pipeline.py": copied,
            "tools/evidence_gather.py": copied,
            "tools/evidence_gather_support/common.py": copied,
            "src/evidence_handoff/ledger/models.py": copied,
            "src/evidence_handoff_runtime/service.py": copied,
            "tools/evidence_handoff_live_support/verify.py": copied,
            "tools/verify_evidence_handoff_live.py": copied,
            "tests/unit/test_copy.py": copied,
        }
    )


def _member(identity: str, path: str, symbol: str, line: int) -> dict[str, object]:
    return {
        "member_id": identity,
        "path": path,
        "symbol": symbol,
        "line_start": line,
        "line_end": line + 2,
        "async_kind": "SYNC",
        "signature_shape": "positional:1",
        "shape_digest": "1" * 64,
        "token_digest": "2" * 64,
        "call_leaves": ["strip", "lower"],
        "receiver_roles": ["value.strip", "value.strip.lower"],
        "control_flow": [],
        "node_count": 9,
    }


def _literal_inventory() -> dict[str, object]:
    groups = [
        {
            "group_id": "dup-callable-wide",
            "kind": "CALLABLE_SHAPE",
            "join_reasons": ["AST_SHAPE_EQUAL"],
            "members": [
                _member("member-a", "src/optimus/a.py", "src.optimus.a.f", 1),
                _member("member-b", "src/optimus/b.py", "src.optimus.b.f", 1),
                _member("member-c", "tools/c.py", "tools.c.f", 1),
            ],
        },
        {
            "group_id": "dup-callable-narrow",
            "kind": "CALLABLE_SHAPE",
            "join_reasons": ["FEATURE_SIMILARITY"],
            "members": [
                _member("member-d", "src/optimus/d.py", "src.optimus.d.g", 1),
                _member("member-e", "tools/e.py", "tools.e.g", 1),
            ],
        },
    ]
    inventory: dict[str, object] = {
        "schema_version": "plan-11-26-duplication-candidates-v1",
        "algorithm_version": "plan1126-duplication-v1",
        "source_commit": _PINNED_COMMIT,
        "source_tree_digest": "3" * 64,
        "allowed_roots": ["src/", "tools/"],
        "scope_exclusions": [
            {
                "exclusion_id": "tests",
                "owner": "Plan 11.26 / production-risk boundary",
                "reason": "Test scaffolding is outside the production latent-defect surface.",
                "path_prefixes": ["tests/"],
                "matched_paths": ["tests/unit/test_copy.py"],
            },
            {
                "exclusion_id": "evidence-collector",
                "owner": "EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR",
                "reason": "Evidence Collector is an affirmatively excluded product.",
                "path_prefixes": ["src/evidence_handoff/collector/"],
                "matched_paths": ["src/evidence_handoff/collector/pipeline.py"],
            },
            {
                "exclusion_id": "a2a-ledger",
                "owner": "EVIDENCE-HANDOFF-FEAT-A2A-LEDGER",
                "reason": "A2A Ledger is an affirmatively excluded product.",
                "path_prefixes": ["src/evidence_handoff/ledger/"],
                "matched_paths": ["src/evidence_handoff/ledger/models.py"],
            },
        ],
        "source_files": [
            "src/optimus/a.py",
            "src/optimus/b.py",
            "src/optimus/d.py",
            "tools/c.py",
            "tools/e.py",
        ],
        "source_file_count": 5,
        "excluded_file_count": 3,
        "callable_universe_count": 5,
        "declaration_universe_count": 0,
        "candidate_groups": groups,
        "prior_seed_reconciliation": [
            {
                "seed_id": "canonical-digest",
                "status": "NOT_REDISCOVERED",
                "candidate_group_ids": [],
                "explanation": "Fixture does not contain the pinned-tree digest helpers.",
            }
        ],
    }
    inventory["inventory_digest"] = _sha256(
        canonical_json_bytes({key: value for key, value in inventory.items() if key != "inventory_digest"})
    )
    return inventory


def _literal_audit(inventory: dict[str, object], frozen: dict[str, bytes]) -> dict[str, object]:
    groups = inventory["candidate_groups"]
    assert isinstance(groups, list)
    wide = groups[0]
    narrow = groups[1]
    assert isinstance(wide, dict) and isinstance(narrow, dict)
    wide_members = wide["members"]
    narrow_members = narrow["members"]
    assert isinstance(wide_members, list) and isinstance(narrow_members, list)
    return {
        "schema_version": "plan-11-26-duplication-audit-v1",
        "source_commit": _PINNED_COMMIT,
        "inventory_digest": inventory["inventory_digest"],
        "frozen_task12_artifacts": [
            {"path": path, "sha256": _sha256(payload)} for path, payload in sorted(frozen.items())
        ],
        "reviewed_partitions": [
            {
                "partition_id": "partition-wide",
                "raw_group_id": wide["group_id"],
                "member_ids": [member["member_id"] for member in wide_members],
                "disposition": "CONFIRMED_DUPLICATION",
                "rationale": "Three modules independently implement the same normalization contract.",
                "finding_id": "DUP-001",
                "candidate_id": "P11.26-DUP-CAND-1-NORMALIZATION",
            },
            {
                "partition_id": "partition-narrow",
                "raw_group_id": narrow["group_id"],
                "member_ids": [member["member_id"] for member in narrow_members],
                "disposition": "CONFIRMED_DUPLICATION",
                "rationale": "Two modules independently implement the same lookup contract.",
                "finding_id": "DUP-002",
                "candidate_id": "P11.26-DUP-CAND-2-LOOKUP",
            },
        ],
        "findings": [
            {
                "finding_id": "DUP-001",
                "subject": "Normalization helper ownership is duplicated.",
                "classification": "DUPLICATED",
                "symbols": [member["symbol"] for member in wide_members],
                "evidence_digest": "4" * 64,
                "impact": "A contract change can diverge across three independently maintained copies.",
                "severity": "HIGH",
                "owner": "P11-FEAT-ACP-RUNTIME-HARDENING",
            },
            {
                "finding_id": "DUP-002",
                "subject": "Lookup helper ownership is duplicated.",
                "classification": "DUPLICATED",
                "symbols": [member["symbol"] for member in narrow_members],
                "evidence_digest": "5" * 64,
                "impact": "A contract change can diverge across two independently maintained copies.",
                "severity": "CRITICAL",
                "owner": "P11-FEAT-ACP-RUNTIME-HARDENING",
            },
        ],
        "remediation_candidates": [
            {
                "candidate_id": "P11.26-DUP-CAND-1-NORMALIZATION",
                "rank": 1,
                "shape": "consolidation",
                "latent_surface_closed": 3,
                "confirmed_member_symbols": [member["symbol"] for member in wide_members],
                "module_count": 3,
                "severity": "HIGH",
                "owner_to_be": "P11-FEAT-ACP-RUNTIME-HARDENING / normalization owner",
                "next_gate": "Pickup performs the backlog conflict check and authors a remediation plan.",
                "finding_ids": ["DUP-001"],
            },
            {
                "candidate_id": "P11.26-DUP-CAND-2-LOOKUP",
                "rank": 2,
                "shape": "consolidation",
                "latent_surface_closed": 2,
                "confirmed_member_symbols": [member["symbol"] for member in narrow_members],
                "module_count": 2,
                "severity": "CRITICAL",
                "owner_to_be": "P11-FEAT-ACP-RUNTIME-HARDENING / lookup owner",
                "next_gate": "Pickup performs the backlog conflict check and authors a remediation plan.",
                "finding_ids": ["DUP-002"],
            },
        ],
        "counts": {
            "raw_groups": 2,
            "reviewed_partitions": 2,
            "confirmed_partitions": 2,
            "intentional_partitions": 0,
            "similarity_only_partitions": 0,
            "confirmed_findings": 2,
            "remediation_candidates": 2,
        },
        "gate_status": "PENDING_G7",
    }


def test_duplication_scope_excludes_products_before_ast_extraction() -> None:
    inventory = discover_duplication_candidates(_scope_fixture(), DEFAULT_SCOPE)

    assert inventory["source_files"] == ["src/optimus/core.py", "src/optimus/other.py"]
    exclusions = {item["exclusion_id"]: item for item in inventory["scope_exclusions"]}
    assert set(exclusions) == {"tests", "evidence-collector", "a2a-ledger"}
    assert all(item["matched_paths"] for item in exclusions.values())
    excluded = {
        path for item in exclusions.values() for path in item["matched_paths"]
    }
    members = {
        member["path"]
        for group in inventory["candidate_groups"]
        for member in group["members"]
    }
    assert members == {"src/optimus/core.py", "src/optimus/other.py"}
    assert excluded.isdisjoint(members)


def test_duplication_discovery_ignores_trivial_accessors_and_enum_members() -> None:
    source = SourceTree({
        "src/optimus/a.py": '''
from enum import StrEnum

MODULE_DEFAULT = "shared-default"

class Status(StrEnum):
    OPEN = "open"
    CLOSED = "closed"

class Holder:
    @property
    def value(self):
        return self._value

def normalize(value):
    cleaned = value.strip()
    return cleaned.lower()
''',
        "src/optimus/b.py": '''
MODULE_FALLBACK = "shared-default"

class Holder:
    @property
    def value(self):
        return self._value

def normalize(value):
    cleaned = value.strip()
    return cleaned.lower()
''',
    })

    inventory = discover_duplication_candidates(source, DEFAULT_SCOPE, ())
    symbols = {
        member["symbol"]
        for group in inventory["candidate_groups"]
        for member in group["members"]
    }
    assert "src.optimus.a.Holder.value" not in symbols
    assert "src.optimus.b.Holder.value" not in symbols
    assert not any(symbol.endswith((".OPEN", ".CLOSED")) for symbol in symbols)
    assert {"src.optimus.a.normalize", "src.optimus.b.normalize"} <= symbols
    assert inventory["declaration_universe_count"] == 2


def test_duplication_inventory_is_deterministic_and_reconciles_prior_seeds() -> None:
    source = GitCommitSource(_PINNED_COMMIT, _ROOT)
    first = discover_duplication_candidates(source, DEFAULT_SCOPE, DEFAULT_PRIOR_SEEDS)
    second = discover_duplication_candidates(source, DEFAULT_SCOPE, DEFAULT_PRIOR_SEEDS)

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["source_commit"] == _PINNED_COMMIT
    assert first["candidate_groups"]
    reconciliation = first["prior_seed_reconciliation"]
    assert {item["seed_id"] for item in reconciliation} == {
        seed.seed_id for seed in DEFAULT_PRIOR_SEEDS
    }
    assert all(item["status"] in {"REDISCOVERED", "NOT_REDISCOVERED"} for item in reconciliation)
    by_seed = {item["seed_id"]: item for item in reconciliation}
    assert by_seed["directive-regex-values"]["status"] == "REDISCOVERED"
    assert all(
        item["candidate_group_ids"] or item["explanation"]
        for item in reconciliation
    )


def test_duplication_audit_partitions_every_member_and_ranks_confirmed_custody() -> None:
    inventory = _literal_inventory()
    frozen = {"reports/task12.json": b"frozen-task-12"}
    audit = _literal_audit(inventory, frozen)

    verify_duplication_audit(inventory, audit, frozen_artifact_bytes=frozen)

    missing_member = copy.deepcopy(audit)
    missing_member["reviewed_partitions"][0]["member_ids"].pop()
    with pytest.raises(ValueError, match="partition coverage"):
        verify_duplication_audit(inventory, missing_member, frozen_artifact_bytes=frozen)

    wrong_rank = copy.deepcopy(audit)
    wrong_rank["remediation_candidates"][0]["rank"] = 2
    with pytest.raises(ValueError, match="candidate ranking"):
        verify_duplication_audit(inventory, wrong_rank, frozen_artifact_bytes=frozen)


def test_duplication_gate_status_rejects_accepted_zero_with_confirmed_findings() -> None:
    inventory = _literal_inventory()
    frozen = {"reports/task12.json": b"frozen-task-12"}
    audit = _literal_audit(inventory, frozen)
    audit["gate_status"] = "ACCEPTED_ZERO"

    with pytest.raises(ValueError, match="gate status"):
        verify_duplication_audit(inventory, audit, frozen_artifact_bytes=frozen)


def test_duplication_accepted_zero_is_reachable_only_for_zero_finding_content() -> None:
    inventory = _literal_inventory()
    frozen = {"reports/task12.json": b"frozen-task-12"}
    audit = _literal_audit(inventory, frozen)
    for partition in audit["reviewed_partitions"]:
        partition["disposition"] = "STRUCTURAL_SIMILARITY_ONLY"
        partition["finding_id"] = None
        partition["candidate_id"] = None
    audit["findings"] = []
    audit["remediation_candidates"] = []
    audit["counts"] = {
        "raw_groups": 2,
        "reviewed_partitions": 2,
        "confirmed_partitions": 0,
        "intentional_partitions": 0,
        "similarity_only_partitions": 2,
        "confirmed_findings": 0,
        "remediation_candidates": 0,
    }
    audit["gate_status"] = "PENDING_G7"

    verify_duplication_audit(inventory, audit, frozen_artifact_bytes=frozen)

    audit["gate_status"] = "ACCEPTED_ZERO"

    verify_duplication_audit(inventory, audit, frozen_artifact_bytes=frozen)

    audit["gate_status"] = "ACCEPTED_OPEN"
    with pytest.raises(ValueError, match="gate status"):
        verify_duplication_audit(inventory, audit, frozen_artifact_bytes=frozen)


def test_duplication_verifier_freezes_task12_and_render_is_deterministic() -> None:
    inventory = _literal_inventory()
    frozen = {"reports/task12.json": b"frozen-task-12"}
    audit = _literal_audit(inventory, frozen)

    first = render_duplication_markdown(inventory, audit)
    second = render_duplication_markdown(inventory, audit)
    assert first == second
    assert first.index("## Affirmative exclusions") < first.index("## Raw candidate groups")

    with pytest.raises(ValueError, match="frozen Task 12 artifact digest"):
        verify_duplication_audit(
            inventory,
            audit,
            frozen_artifact_bytes={"reports/task12.json": b"changed"},
        )


def test_duplication_frozen_text_digest_is_checkout_line_ending_independent() -> None:
    inventory = _literal_inventory()
    path = "reports/task12.json"
    lf_bytes = b'{"gate_status":"INCOMPLETE"}\n'
    audit = _literal_audit(inventory, {path: lf_bytes})

    verify_duplication_audit(
        inventory,
        audit,
        frozen_artifact_bytes={path: b'{"gate_status":"INCOMPLETE"}\r\n'},
    )


def test_duplication_json_schemas_are_closed_and_accept_canonical_documents() -> None:
    inventory = _literal_inventory()
    frozen = {"reports/task12.json": b"frozen-task-12"}
    audit = _literal_audit(inventory, frozen)
    inventory_schema = json.loads(
        (_SCHEMA_DIR / "duplication-candidates.schema.json").read_text(encoding="utf-8")
    )
    audit_schema = json.loads(
        (_SCHEMA_DIR / "duplication-audit.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(inventory_schema)
    Draft202012Validator.check_schema(audit_schema)
    assert not list(Draft202012Validator(inventory_schema).iter_errors(inventory))
    assert not list(Draft202012Validator(audit_schema).iter_errors(audit))

    widened = copy.deepcopy(audit)
    widened["unexpected"] = True
    assert list(Draft202012Validator(audit_schema).iter_errors(widened))


def test_duplication_cli_discovers_pinned_inventory(tmp_path: Path) -> None:
    inventory_path = tmp_path / "candidates.json"

    assert audit_cli_main([
        "duplication",
        "discover",
        "--source-commit",
        _PINNED_COMMIT,
        "--inventory",
        str(inventory_path),
    ]) == 0
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert inventory["source_commit"] == _PINNED_COMMIT
    assert inventory["candidate_groups"]


def test_duplication_cli_verifies_and_renders_reviewed_artifacts(tmp_path: Path) -> None:
    frozen_path = tmp_path / "task12.json"
    frozen_path.write_bytes(b"frozen-task-12")
    inventory = _literal_inventory()
    audit = _literal_audit(inventory, {str(frozen_path): frozen_path.read_bytes()})
    inventory_path = tmp_path / "candidates.json"
    audit_path = tmp_path / "audit.json"
    report_path = tmp_path / "audit.md"
    inventory_path.write_bytes(canonical_json_bytes(inventory))
    audit_path.write_bytes(canonical_json_bytes(audit))

    assert audit_cli_main([
        "duplication",
        "verify",
        "--inventory",
        str(inventory_path),
        "--artifact",
        str(audit_path),
    ]) == 0
    assert audit_cli_main([
        "duplication",
        "render",
        "--inventory",
        str(inventory_path),
        "--artifact",
        str(audit_path),
        "--report",
        str(report_path),
    ]) == 0
    assert report_path.read_text(encoding="utf-8").startswith(
        "# Plan 11.26 Task 13 Duplication Audit\n"
    )
