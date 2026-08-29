from __future__ import annotations

import copy
import hashlib
import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit.cancellation import (
    H3_SOURCE_PATHS,
    cancellation_schedule_observations,
    discover_task_supervision,
)
from tools.plan1126_runtime_audit.corpus import derived_seed, literal_seeds
from tools.plan1126_runtime_audit.delivery_characterization import H4_SOURCE_PATHS
from tools.plan1126_runtime_audit.model import AuditArtifact, InventoryKind
from tools.plan1126_runtime_audit.render import render_markdown
from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree

_MERGED = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"
_OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"
_SCHEMA_PATH = Path("tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json")


def _immutable_source(commit: str) -> SourceTree:
    source = GitCommitSource(commit)
    return SourceTree({path: source.read_text(path) for path in H3_SOURCE_PATHS})


def _cumulative_source(commit: str) -> SourceTree:
    source = GitCommitSource(commit)
    paths = tuple(sorted(set(H3_SOURCE_PATHS) | set(H4_SOURCE_PATHS)))
    return SourceTree({path: source.read_text(path) for path in paths})


@dataclass(frozen=True)
class _OracleSite:
    path: str
    line: int
    kind: InventoryKind
    reference: str


_TASK_TEXT_PATTERNS = (
    (re.compile(r"\basyncio\.create_task\s*\("), "asyncio.create_task"),
    (re.compile(r"\basyncio\.to_thread\s*\("), "asyncio.to_thread"),
    (
        re.compile(r"\basyncio\.run_coroutine_threadsafe\s*\("),
        "asyncio.run_coroutine_threadsafe",
    ),
    (re.compile(r"\bthreading\.Thread\s*\("), "threading.Thread"),
)
_CANCEL_TEXT_PATTERN = re.compile(
    r"\b(?P<reference>(?:[A-Za-z_]\w*\.)*(?:request_session_cancel|request_transport_teardown)|"
    r"(?:[A-Za-z_]\w*\.)*permission_handle\.cancel|task\.cancel)\s*\("
)
_DYNAMIC_CANCEL_TEXT_PATTERN = re.compile(r"^\s*cancel\s*\(")


def _oracle_sites(source: SourceTree) -> set[tuple[str, int, InventoryKind, str]]:
    """Lexical oracle independent of the scanner's AST traversal and receiver policy."""

    sites: set[tuple[str, int, InventoryKind, str]] = set()
    for path in source.paths():
        for line_number, line in enumerate(source.read_text(path).splitlines(), start=1):
            if line.lstrip().startswith(("def ", "async def ", "class ", "#")):
                continue
            for pattern, reference in _TASK_TEXT_PATTERNS:
                if pattern.search(line):
                    sites.add((path, line_number, InventoryKind.TASK_CREATE, reference))
            for match in _CANCEL_TEXT_PATTERN.finditer(line):
                sites.add(
                    (
                        path,
                        line_number,
                        InventoryKind.CANCELLATION_POINT,
                        match.group("reference"),
                    )
                )
            if _DYNAMIC_CANCEL_TEXT_PATTERN.search(line):
                sites.add((path, line_number, InventoryKind.CANCELLATION_POINT, "cancel"))
    return sites


def test_task_supervision_inventory_is_independent_complete_and_receiver_safe() -> None:
    merged = _immutable_source(_MERGED)
    overlay = _immutable_source(_OVERLAY)

    inventory = discover_task_supervision(merged, overlay=overlay)

    merged_actual = {
        (site.path, site.line, site.kind, site.reference)
        for site in inventory.discovered_sites
        if site.source_baseline == "merged"
    }
    overlay_actual = {
        (site.path, site.line, site.kind, site.reference)
        for site in inventory.discovered_sites
        if site.source_baseline == "overlay"
    }
    assert merged_actual == _oracle_sites(merged)
    assert overlay_actual == _oracle_sites(overlay)
    assert inventory.cancellation_point_count == len(
        {site.conceptual_id for site in inventory.cancellation_points}
    )
    assert inventory.cancellation_point_count > 0
    assert all(record.creator and record.owner and record.registration_point for record in inventory.task_units)
    assert all(record.cancellation_source and record.join_or_settlement and record.escape_path for record in inventory.task_units)
    assert inventory.ownership_role_counts["TASK_GROUP"] == 0
    assert inventory.ownership_role_counts["TIMEOUT"] == 0
    assert all(
        inventory.ownership_role_counts[role] > 0
        for role in ("REGISTRATION", "CALLBACK", "CANCELLATION_CATCH", "JOIN", "TASK_SET_MUTATION")
    )
    escaped = [record for record in inventory.task_units if record.classification == "ESCAPED_CHILD"]
    assert len(escaped) == 1
    assert "run_coroutine_threadsafe" in escaped[0].creator
    assert escaped[0].registration_point.startswith("NONE_OBSERVED:")
    assert escaped[0].join_or_settlement.startswith("NONE_OBSERVED:")
    assert {record.classification for record in inventory.task_units} == {"OWNED", "ESCAPED_CHILD"}

    fixture = SourceTree(
        {
            "fixture.py": """
import asyncio

async def worker():
    await asyncio.sleep(0)

async def run(metrics, queue):
    tasks = set()
    task = asyncio.create_task(worker())
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    metrics.cancel()
    queue.submit(task)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
"""
        }
    )
    fixture_inventory = discover_task_supervision(fixture)
    fixture_refs = {site.reference for site in fixture_inventory.discovered_sites}
    assert "asyncio.create_task" in fixture_refs
    assert "task.cancel" in fixture_refs
    assert "metrics.cancel" not in fixture_refs
    assert "queue.submit" not in fixture_refs


def test_turn_cancellation_races_256_seed_matrix() -> None:
    inventory = discover_task_supervision(
        _immutable_source(_MERGED), overlay=_immutable_source(_OVERLAY)
    )

    observations = cancellation_schedule_observations(
        anchor_commit=_MERGED,
        inventory=inventory,
        literal=literal_seeds(),
        derived_count=256,
    )

    point_ids = tuple(sorted({site.conceptual_id for site in inventory.cancellation_points}))
    levels = (1, 2, 4, 8)
    per_family = len(literal_seeds()) + 256
    assert len(observations) == len(point_ids) * len(levels) * per_family

    by_family: dict[tuple[str, int], list[object]] = {}
    for observation in observations:
        by_family.setdefault(
            (observation.cancellation_point_id, observation.concurrency_level), []
        ).append(observation)
        assert observation.complete
        assert observation.cancellation_invocation_count == observation.concurrency_level
        assert len(observation.invocation_outcomes) == observation.concurrency_level
        assert observation.executed_definition_citations
        assert observation.request_task_state
        assert observation.child_work_state
        assert observation.final_delivery
        assert observation.conversation_commit
        assert observation.effect_state
        assert observation.cancelled_error_preserved == (
            observation.request_task_state == "cancelled"
        )

    assert set(by_family) == {(point_id, level) for point_id in point_ids for level in levels}
    for point_id, level in sorted(by_family):
        family = by_family[(point_id, level)]
        assert [item.seed for item in family[: len(literal_seeds())]] == list(literal_seeds())
        assert all(item.seed_source == "frozen-literal" for item in family[: len(literal_seeds())])
        assert [item.seed for item in family[len(literal_seeds()) :]] == [
            derived_seed(
                _MERGED,
                f"H3-cancellation:{point_id}:level-{level}",
                index,
            )
            for index in range(256)
        ]
        assert all(item.seed_source == "commit-derived" for item in family[len(literal_seeds()) :])

    assert sum(
        item.seed_source == "commit-derived" and item.concurrency_level == 1
        for item in observations
    ) == inventory.cancellation_point_count * 256
    assert sum(
        item.seed_source == "commit-derived" and item.concurrency_level in {2, 4, 8}
        for item in observations
    ) == inventory.cancellation_point_count * 3 * 256
    assert {item.phase for item in observations} == {
        "pre-start",
        "running",
        "delivery",
        "settlement",
        "teardown",
    }
    assert {item.request_task_state for item in observations} == {"cancelled", "completed"}
    assert {item.final_delivery for item in observations} >= {
        "not_attempted",
        "ambiguous",
        "flushed",
    }


def test_h3_artifact_derives_cost_and_coverage_from_raw_observations(tmp_path: Path) -> None:
    cancellation = importlib.import_module("tools.plan1126_runtime_audit.cancellation")
    build = getattr(cancellation, "build_h3_audit_artifact", None)
    assert build is not None, "H3 evidence builder does not exist"

    artifact = build(
        merged=_cumulative_source(_MERGED),
        overlay=_cumulative_source(_OVERLAY),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
    )
    payload = artifact.to_dict()
    assert AuditArtifact.from_dict(payload).to_dict() == payload
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []

    records = {record["hypothesis_id"]: record for record in payload["evidence_records"]}
    assert set(records) == {"H3", "H4"}
    record = records["H3"]
    assert record["baseline_scope"] == "both-aligned"
    assert record["reviewer_status"] == "PENDING_G2"
    assert record["cancellation_point_count"] == 8
    assert payload["discovered_multipliers"]["cancellation_points"] == 8
    assert payload["computed_run_cost"]["cancellation_control_schedules"] == 8 * 256
    assert payload["computed_run_cost"]["cancellation_schedules"] == 8 * 3 * 256
    assert record["turn_control_ruling"] == {"merged": "CANONICAL", "overlay": "CANONICAL"}

    summary = record["schedule_observations"]
    assert summary["total_observation_count"] == 8 * 4 * (len(literal_seeds()) + 256)
    assert summary["complete_observation_count"] == summary["total_observation_count"]
    assert summary["observation_closure_status"] == "FULLY_STRUCTURALLY_CLOSED"
    assert summary["vocabulary_coverage_status"] == "PARTIAL_WITH_SCOPE_OUTS"

    field_types = {
        "request_task_state": "RequestTaskState",
        "child_work_state": "ChildWorkState",
        "final_delivery": "FinalDelivery",
        "conversation_commit": "ConversationCommit",
        "effect_state": "EffectState",
        "invocation_outcomes": "CancellationInvocationOutcome",
    }
    assessments = {item["field_name"]: item for item in summary["coverage_assessments"]}
    assert set(assessments) == set(field_types)
    for field, type_name in field_types.items():
        observed = {
            value
            for observation in summary["observations"]
            for value in (
                observation[field]
                if isinstance(observation[field], list)
                else [observation[field]]
            )
        }
        vocabulary = set(summary["vocabulary"][type_name].values())
        assessment = assessments[field]
        assert assessment["vocabulary_values"] == sorted(vocabulary)
        assert assessment["observed_values"] == sorted(observed)
        assert assessment["missing_values"] == sorted(vocabulary - observed)
        assert assessment["status"] == (
            "SCOPED_OUT" if vocabulary - observed else "FULLY_OBSERVED"
        )
        if vocabulary - observed:
            assert assessment["reason"]
            assert assessment["owner"] == "P11-FEAT-ACP-RUNTIME-HARDENING"
            assert assessment["next_gate"]

    conversation = assessments["conversation_commit"]
    assert conversation["observed_values"] == ["not_committed"]
    assert conversation["missing_values"] == ["committed"]
    assert "conversation persistence" in conversation["reason"]

    report = render_markdown(payload)
    assert "### `H3`" in report
    assert "Derived cancellation points | 8" in report
    assert "2,048 control schedules plus 6,144 race schedules" in report
    assert "8,320/8,320 structurally closed" in report
    assert "`conversation_commit`" in report
    assert "`committed`" in report
    assert "G5 cancellation-to-conversation persistence characterization" in report

    artifact_path = tmp_path / "task5-artifact.json"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    cli = importlib.import_module("tools.run_plan1126_runtime_audit")
    assert cli._verify_artifact(str(artifact_path)).to_dict() == payload

    changed = copy.deepcopy(payload)
    changed["computed_run_cost"]["cancellation_schedules"] -= 1
    with __import__("pytest").raises(ValueError, match="cost"):
        AuditArtifact.from_dict(changed)

    changed = copy.deepcopy(payload)
    h3 = next(item for item in changed["evidence_records"] if item["hypothesis_id"] == "H3")
    h3["schedule_observations"]["coverage_assessments"][0]["observed_values"].append("invented")
    with __import__("pytest").raises(ValueError):
        AuditArtifact.from_dict(changed)

    changed = copy.deepcopy(payload)
    h3 = next(item for item in changed["evidence_records"] if item["hypothesis_id"] == "H3")
    h3["schedule_observations"]["vocabulary"]["RequestTaskState"]["INVENTED"] = "invented"
    with __import__("pytest").raises(ValueError, match="source-owned"):
        AuditArtifact.from_dict(changed)

    changed = copy.deepcopy(payload)
    h3 = next(item for item in changed["evidence_records"] if item["hypothesis_id"] == "H3")
    summary = h3["schedule_observations"]
    summary["observations"][0]["seed"] += 1
    observation_bytes = json.dumps(
        summary["observations"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    summary["digest"] = hashlib.sha256(observation_bytes).hexdigest()
    next(
        item
        for item in h3["content_free_evidence"]
        if item["evidence_id"] == "H3-CANCELLATION-OBSERVATIONS"
    )["digest"] = summary["digest"]
    with __import__("pytest").raises(ValueError, match="seed family"):
        AuditArtifact.from_dict(changed)

    changed = copy.deepcopy(payload)
    h3 = next(item for item in changed["evidence_records"] if item["hypothesis_id"] == "H3")
    scoped = next(
        item
        for item in h3["schedule_observations"]["coverage_assessments"]
        if item["status"] == "SCOPED_OUT"
    )
    del scoped["owner"]
    assert list(Draft202012Validator(schema).iter_errors(changed))
