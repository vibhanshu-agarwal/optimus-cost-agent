"""Worked-example contracts for the Plan 11.26 delivery-settlement audit."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import importlib.util
import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit import inventory as inventory_module
from tools.plan1126_runtime_audit.corpus import derived_seed, literal_seeds
from tools.plan1126_runtime_audit.model import AuditArtifact, BaselineScope, Classification, DeliveryPhase
from tools.plan1126_runtime_audit.render import render_markdown
from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree

_MERGED = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"
_OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"
_DELIVERY_PATHS = (
    "src/optimus/acp/outbound_writer.py",
    "src/optimus/acp/lifecycle.py",
    "src/optimus/acp/settlement.py",
    "src/optimus/acp/conversation.py",
    "src/optimus/acp/spec.py",
    "src/optimus/acp/server.py",
)
_SCHEMA_PATH = Path(__file__).parents[2] / "fixtures" / "plan1126_runtime_audit" / "audit-artifact.schema.json"
_SETTLED_VOCABULARY = frozenset(
    {
        "SendState",
        "SendOutcome",
        "Settlement",
        "FinalDelivery",
        "RpcResponseDelivery",
        "ConversationCommit",
        "EffectState",
    }
)
_COVERAGE_OWNER = "P11-FEAT-ACP-RUNTIME-HARDENING"
_EXPECTED_SETTLED_COVERAGE = {
    "conversation_commit": {
        "field_name": "conversation_commit",
        "type_name": "ConversationCommit",
        "vocabulary_values": ["committed", "not_committed"],
        "observed_values": ["committed", "not_committed"],
        "missing_values": [],
        "status": "FULLY_OBSERVED",
        "reason": None,
        "owner": None,
        "next_gate": None,
    },
    "effect_state": {
        "field_name": "effect_state",
        "type_name": "EffectState",
        "vocabulary_values": ["complete", "indeterminate", "none", "partial"],
        "observed_values": ["complete", "indeterminate", "none", "partial"],
        "missing_values": [],
        "status": "FULLY_OBSERVED",
        "reason": None,
        "owner": None,
        "next_gate": None,
    },
    "final_delivery": {
        "field_name": "final_delivery",
        "type_name": "FinalDelivery",
        "vocabulary_values": [
            "ambiguous", "conclusive_failure", "flushed", "not_attempted", "partial",
        ],
        "observed_values": ["not_attempted"],
        "missing_values": ["ambiguous", "conclusive_failure", "flushed", "partial"],
        "status": "SCOPED_OUT",
        "reason": (
            "These H4 scenarios execute start_response_send and never start_terminal_message, "
            "so terminal-message states are unreachable."
        ),
        "owner": _COVERAGE_OWNER,
        "next_gate": "G5 terminal-message characterization",
    },
    "rpc_response_delivery": {
        "field_name": "rpc_response_delivery",
        "type_name": "RpcResponseDelivery",
        "vocabulary_values": ["ambiguous", "conclusive_failure", "flushed", "not_attempted"],
        "observed_values": ["ambiguous", "conclusive_failure", "flushed", "not_attempted"],
        "missing_values": [],
        "status": "FULLY_OBSERVED",
        "reason": None,
        "owner": None,
        "next_gate": None,
    },
    "send_outcome": {
        "field_name": "send_outcome",
        "type_name": "SendOutcome",
        "vocabulary_values": ["ambiguous", "conclusive_failure", "flushed", "suppressed"],
        "observed_values": ["ambiguous", "conclusive_failure", "flushed", "suppressed"],
        "missing_values": [],
        "status": "FULLY_OBSERVED",
        "reason": None,
        "owner": None,
        "next_gate": None,
    },
    "send_state": {
        "field_name": "send_state",
        "type_name": "SendState",
        "vocabulary_values": [
            "ambiguous", "conclusive_failure", "flushed", "queued", "suppressed", "write_started",
        ],
        "observed_values": ["ambiguous", "conclusive_failure", "flushed", "suppressed"],
        "missing_values": ["queued", "write_started"],
        "status": "SCOPED_OUT",
        "reason": (
            "Queued and write_started are transient states absent from terminal observation snapshots."
        ),
        "owner": _COVERAGE_OWNER,
        "next_gate": "G4 per-group transient-state observation review",
    },
    "settlement": {
        "field_name": "settlement",
        "type_name": "Settlement",
        "vocabulary_values": ["cancelled", "completed", "failed", "rejected", "transport_abandoned"],
        "observed_values": ["completed", "transport_abandoned"],
        "missing_values": ["cancelled", "failed", "rejected"],
        "status": "SCOPED_OUT",
        "reason": (
            "The reviewed _placeholder_settlement two-branch producer does not emit cancelled, "
            "failed, or rejected."
        ),
        "owner": _COVERAGE_OWNER,
        "next_gate": "G4 per-group settlement-producer review",
    },
}
_EXPECTED_CONSTANT_METADATA_NOTES = {
    "classification": {
        "field_name": "classification",
        "constant_value": "CANONICAL",
        "claim_status": "NOT_A_VOCABULARY_CLAIM",
        "reason": (
            "Classification is static-site lineage represented by discovered sites and findings; "
            "schedule rows do not claim classification-vocabulary coverage."
        ),
    },
    "complete": {
        "field_name": "complete",
        "constant_value": True,
        "claim_status": "NOT_A_VOCABULARY_CLAIM",
        "reason": (
            "Complete means closed observation-record shape only; it is not a settled-vocabulary "
            "coverage claim."
        ),
    },
    "contradiction": {
        "field_name": "contradiction",
        "constant_value": None,
        "claim_status": "NOT_A_VOCABULARY_CLAIM",
        "reason": (
            "Contradiction belongs to the static contradiction search; no schedule row executes a "
            "contradictory site."
        ),
    },
}
_DELIVERY_VERB = re.compile(
    r"(?:^|_)(?:send|write|enqueue|submit|notify|publish|flush|drain|deliver|commit|settle|finalize)(?:_|$)"
)


@dataclass(frozen=True, slots=True)
class _Candidate:
    path: str
    symbol: str
    line: int
    reference: str
    fingerprint: str


def _call_name(node: ast.expr) -> tuple[str, str]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    dotted = ".".join(parts)
    return (parts[-1] if parts else "", dotted)


class _IndependentDeliveryOracle(ast.NodeVisitor):
    """Broad AST oracle independent of the audit inventory implementation."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.function_stack: list[tuple[str, str | None]] = []
        self.candidates: list[_Candidate] = []

    @property
    def symbol(self) -> str:
        module = self.path.removesuffix(".py").replace("/", ".")
        suffix = ".".join(item[0] for item in self.function_stack)
        return f"{module}.{suffix}" if suffix else module

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.function_stack.append((node.name, ast.get_docstring(node, clean=True)))
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        leaf, dotted = _call_name(node.func)
        if leaf in _SETTLED_VOCABULARY or _DELIVERY_VERB.search(leaf):
            self.candidates.append(
                _Candidate(
                    self.path,
                    self.symbol,
                    node.lineno,
                    dotted or leaf,
                    ast.dump(node, include_attributes=False),
                )
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id in _SETTLED_VOCABULARY:
            self.candidates.append(
                _Candidate(
                    self.path,
                    self.symbol,
                    node.lineno,
                    f"{node.value.id}.{node.attr}",
                    ast.dump(node, include_attributes=False),
                )
            )
        self.generic_visit(node)


def _baseline(commit: str) -> SourceTree:
    source = GitCommitSource(commit)
    return SourceTree({path: source.read_text(path) for path in _DELIVERY_PATHS})


def _candidates(source: SourceTree) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for path in source.paths():
        visitor = _IndependentDeliveryOracle(path)
        visitor.visit(ast.parse(source.read_text(path), filename=path))
        candidates.extend(visitor.candidates)
    return candidates


def _expected_conceptual_counts(merged: SourceTree, overlay: SourceTree) -> Counter[tuple[str, str, str]]:
    merged_groups: dict[tuple[str, str, str], list[_Candidate]] = {}
    overlay_groups: dict[tuple[str, str, str], list[_Candidate]] = {}
    for candidate in _candidates(merged):
        merged_groups.setdefault((candidate.path, candidate.symbol, candidate.reference), []).append(candidate)
    for candidate in _candidates(overlay):
        overlay_groups.setdefault((candidate.path, candidate.symbol, candidate.reference), []).append(candidate)
    expected: Counter[tuple[str, str, str]] = Counter()
    for key in set(merged_groups) | set(overlay_groups):
        before = sorted(merged_groups.get(key, ()), key=lambda candidate: candidate.line)
        after = sorted(overlay_groups.get(key, ()), key=lambda candidate: candidate.line)
        for index in range(max(len(before), len(after))):
            merged_candidate = before[index] if index < len(before) else None
            overlay_candidate = after[index] if index < len(after) else None
            expected[key] += 2 if (
                merged_candidate is not None
                and overlay_candidate is not None
                and merged_candidate.fingerprint != overlay_candidate.fingerprint
            ) else 1
    return expected


def test_delivery_contract_ast_covers_all_send_sites() -> None:
    merged = _baseline(_MERGED)
    overlay = _baseline(_OVERLAY)
    discover = getattr(inventory_module, "discover_delivery_sites", None)
    assert discover is not None, "delivery-specific AST inventory rule does not exist"

    sites = discover(merged, overlay=overlay)
    observed = {(site.path, site.symbol, site.reference) for site in sites}

    # Independent structural oracle: annotations establish queue/future ownership;
    # only calls on those owned receivers are expected publication boundaries.
    expected_role_calls: set[tuple[str, str, str]] = set()
    for source in (merged, overlay):
        for path in source.paths():
            tree = ast.parse(source.read_text(path), filename=path)
            queue_fields: set[str] = set()
            future_fields: set[str] = set()
            for node in ast.walk(tree):
                if not isinstance(node, ast.AnnAssign):
                    continue
                annotation = ast.unparse(node.annotation)
                target = ast.unparse(node.target).rsplit(".", 1)[-1]
                if "Queue[" in annotation:
                    queue_fields.add(target)
                if "Future[" in annotation:
                    future_fields.add(target)
            class RoleOracle(ast.NodeVisitor):
                def __init__(self, source_path: str, queues: set[str], futures: set[str]) -> None:
                    self.source_path = source_path
                    self.queues = queues
                    self.futures = futures
                    self.function_stack: list[str] = []

                def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                    self.function_stack.append(node.name)
                    self.generic_visit(node)
                    self.function_stack.pop()

                visit_FunctionDef = _function
                visit_AsyncFunctionDef = _function

                def visit_Call(self, node: ast.Call) -> None:
                    if isinstance(node.func, ast.Attribute):
                        receiver_leaf = ast.unparse(node.func.value).rsplit(".", 1)[-1]
                        if (
                            node.func.attr in {"put", "put_nowait"} and receiver_leaf in self.queues
                        ) or (node.func.attr == "set_result" and receiver_leaf in self.futures):
                            module = self.source_path.removesuffix(".py").replace("/", ".")
                            symbol = ".".join((module, *self.function_stack))
                            expected_role_calls.add((self.source_path, symbol, ast.unparse(node.func)))
                    self.generic_visit(node)

            RoleOracle(path, queue_fields, future_fields).visit(tree)

    assert expected_role_calls <= observed
    assert any(reference.endswith(".put") for _, _, reference in expected_role_calls)
    assert any(reference.endswith(".set_result") for _, _, reference in expected_role_calls)
    assert all("set_running_or_notify_cancel" not in reference for _, _, reference in observed)
    assert all("next_ephemeral_send_key" not in reference for _, _, reference in observed)
    assert all(site.delivery_phase is not None for site in sites)
    assert all(site.classification is not Classification.UNCLASSIFIED for site in sites)


def test_delivery_inventory_has_one_phase_per_conceptual_site() -> None:
    sites = inventory_module.discover_delivery_sites(_baseline(_MERGED), overlay=_baseline(_OVERLAY))
    groups: dict[tuple[str, int, str, str | None], list[object]] = {}
    for site in sites:
        key = (site.path, site.line, site.symbol, site.reference)
        groups.setdefault(key, []).append(site)

    invalid = {
        key: variants
        for key, variants in groups.items()
        if not (
            len(variants) == 1
            or (
                len(variants) == 2
                and all(item.baseline_scope is BaselineScope.BOTH_DIVERGENT for item in variants)
                and len({item.evidence_digest for item in variants}) == 2
            )
        )
    }
    assert invalid == {}, "a baseline variant must have one immediate semantic phase"


def test_h4_model_and_schema_reject_duplicate_conceptual_sites() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    payload = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED), overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED, overlay_commit=_OVERLAY,
    ).to_dict()
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))

    exact = copy.deepcopy(payload)
    exact["evidence_records"][0]["discovered_sites"].append(  # type: ignore[index,union-attr]
        copy.deepcopy(exact["evidence_records"][0]["discovered_sites"][0])  # type: ignore[index]
    )
    assert list(Draft202012Validator(schema).iter_errors(exact))

    changed = copy.deepcopy(payload)
    record = changed["evidence_records"][0]
    duplicate = copy.deepcopy(record["discovered_sites"][0])
    duplicate["delivery_phase"] = (
        "PUBLICATION" if duplicate["delivery_phase"] != "PUBLICATION" else "CANCELLATION"
    )
    duplicate["evidence_digest"] = "sha256:" + "1" * 64
    record["discovered_sites"].append(duplicate)
    citation = f"{duplicate['path']}:{duplicate['line']}:{duplicate['symbol']}:{duplicate['reference']}"
    record["symbol_citations"].append(citation)
    record["contradiction_search"]["searched_reference_count"] += 1
    inventory = json.dumps(
        record["discovered_sites"], sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    record["content_free_evidence"][0]["digest"] = hashlib.sha256(inventory).hexdigest()
    with pytest.raises(ValueError, match="conceptual"):
        AuditArtifact.from_dict(changed)


def test_delivery_contract_model_1000_seed_schedule() -> None:
    module_name = "tools.plan1126_runtime_audit.delivery"
    delivery_module = importlib.import_module(module_name) if importlib.util.find_spec(module_name) else None
    assert delivery_module is not None, "delivery schedule model does not exist"
    execute = getattr(delivery_module, "delivery_schedule_observations", None)
    assert execute is not None, "delivery schedule model does not exist"

    frozen = literal_seeds()
    discovered = inventory_module.discover_delivery_sites(_baseline(_MERGED), overlay=_baseline(_OVERLAY))
    observations = execute(
        anchor_commit=_MERGED,
        literal=frozen,
        derived_count=1_000,
        discovered_sites=discovered,
        vocabulary=delivery_module.derive_delivery_vocabulary(
            _baseline(_MERGED), _baseline(_OVERLAY)
        ),
        transition_authority=delivery_module.derive_transition_authority(
            _baseline(_MERGED), _baseline(_OVERLAY)
        ),
    )
    assert len(observations) == len(frozen) + 1_000
    assert [item.seed for item in observations[: len(frozen)]] == list(frozen)
    assert all(item.seed_source == "frozen-literal" for item in observations[: len(frozen)])
    assert [item.seed for item in observations[len(frozen) :]] == [
        derived_seed(_MERGED, "H4-delivery", index) for index in range(1_000)
    ]
    assert all(item.seed_source == "commit-derived" for item in observations[len(frozen) :])
    assert all(item.anchor_commit == _MERGED for item in observations)
    assert all(item.complete for item in observations)
    assert all(item.classification is not Classification.UNCLASSIFIED for item in observations)
    assert {phase.value for item in observations for phase in item.schedule} == {
        "QUEUE_ADMISSION",
        "PUBLICATION",
        "PHYSICAL_WRITE",
        "FLUSH",
        "CANCELLATION",
        "FINAL_RESPONSE",
        "CONVERSATION_COMMIT",
        "EFFECT_SETTLEMENT",
    }
    assert {item.vocabulary_names for item in observations} == {tuple(sorted(_SETTLED_VOCABULARY))}
    assert any(site.classification is Classification.CONTRADICTORY for site in discovered)
    assert all(item.classification is Classification.CANONICAL for item in observations)
    assert all(item.contradiction is None for item in observations)
    executed_citations = delivery_module.derive_transition_authority(
        _baseline(_MERGED), _baseline(_OVERLAY)
    ).executed_definition_citations
    assert all(len(item.site_citations) == len(DeliveryPhase) for item in observations)
    assert all(set(item.site_citations) <= executed_citations for item in observations)
    assert all(item.send_state == item.send_outcome for item in observations)
    assert all(
        item.conversation_commit != "committed" or item.send_outcome == "flushed"
        for item in observations
    )
    assert all(
        item.send_outcome == "flushed" or item.conversation_commit == "not_committed"
        for item in observations
    )


def test_delivery_phase_and_cross_baseline_classification_follow_settled_symbols() -> None:
    stable = SourceTree({"fixture.py": """
def settle():
    final = FinalDelivery.FLUSHED
    rpc = RpcResponseDelivery.NOT_ATTEMPTED
    commit = ConversationCommit.COMMITTED
    effect = EffectState.NONE
"""})
    sites = inventory_module.discover_delivery_sites(stable, overlay=stable)
    assert {site.reference: site.delivery_phase for site in sites} == {
        "FinalDelivery.FLUSHED": DeliveryPhase.FINAL_RESPONSE,
        "RpcResponseDelivery.NOT_ATTEMPTED": DeliveryPhase.FINAL_RESPONSE,
        "ConversationCommit.COMMITTED": DeliveryPhase.CONVERSATION_COMMIT,
        "EffectState.NONE": DeliveryPhase.EFFECT_SETTLEMENT,
    }
    assert all(site.baseline_scope is BaselineScope.BOTH_ALIGNED for site in sites)
    assert all(site.classification is Classification.CANONICAL for site in sites)

    merged = SourceTree({"fixture.py": "def publish():\n    FinalDelivery('flushed')\n"})
    overlay = SourceTree({"fixture.py": "def publish():\n    FinalDelivery(value)\n"})
    divergent = inventory_module.discover_delivery_sites(merged, overlay=overlay)
    assert len(divergent) == 2
    assert all(site.baseline_scope is BaselineScope.BOTH_DIVERGENT for site in divergent)
    assert all(site.classification is Classification.CANONICAL for site in divergent)


def test_h4_record_uses_canonical_evidence_template_and_separate_baseline_identities() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    build = getattr(delivery_module, "build_h4_audit_artifact", None)
    assert build is not None, "canonical H4 evidence-record builder does not exist"

    artifact = build(
        merged=_baseline(_MERGED),
        overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
    )
    payload = artifact.to_dict()
    assert AuditArtifact.from_dict(payload).to_dict() == payload
    schema = __import__("json").loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []

    assert len(payload["evidence_records"]) == 1
    record = payload["evidence_records"][0]
    assert record["hypothesis_id"] == "H4"
    assert record["baseline_scope"] == "both-aligned"
    assert record["baseline_anchor_commit"] == _MERGED
    assert record["overlay_commit"] == _OVERLAY
    assert record["binding_commit"] is None
    assert record["vocabulary_names"] == sorted(_SETTLED_VOCABULARY)
    assert record["reviewer_status"] == "PENDING_G2"
    assert record["discovered_sites"]
    assert record["symbol_citations"] == sorted(
        f"{site['path']}:{site['line']}:{site['symbol']}:{site['reference']}"
        for site in record["discovered_sites"]
    )
    assert all(site["delivery_phase"] is not None for site in record["discovered_sites"])
    assert all(site["classification"] != "UNCLASSIFIED" for site in record["discovered_sites"])
    contradictions = [
        site for site in record["discovered_sites"] if site["classification"] == "CONTRADICTORY"
    ]
    assert record["contradiction_search"]["contradictory_site_count"] == len(contradictions)
    assert record["contradiction_search"]["contradictory_citations"] == sorted(
        f"{site['path']}:{site['line']}:{site['symbol']}:{site['reference']}"
        for site in contradictions
    )
    observations = record["schedule_observations"]
    assert observations["literal_seeds"] == list(literal_seeds())
    assert observations["derived_seed_count"] == 1_000
    assert observations["derived_seed_anchor_commit"] == _MERGED
    assert observations["total_observation_count"] == len(literal_seeds()) + 1_000
    assert observations["complete_observation_count"] == observations["total_observation_count"]
    assert observations["digest"].isalnum() and len(observations["digest"]) == 64
    assert record["commands"] == [
        "uv run --frozen pytest tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_ast_covers_all_send_sites -q",
        "uv run --frozen pytest tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_model_1000_seed_schedule -q",
    ]
    assert record["content_free_evidence"]


def test_h4_separates_structural_closure_from_owned_settled_vocabulary_coverage() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    payload = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED), overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED, overlay_commit=_OVERLAY,
    ).to_dict()
    summary = payload["evidence_records"][0]["schedule_observations"]

    assert summary["complete_observation_count"] == 1_004
    assert summary["observation_closure_status"] == "FULLY_STRUCTURALLY_CLOSED"
    assert summary["vocabulary_coverage_status"] == "PARTIAL_WITH_SCOPE_OUTS"
    assert {
        assessment["field_name"]: assessment
        for assessment in summary["coverage_assessments"]
    } == _EXPECTED_SETTLED_COVERAGE
    assert {
        note["field_name"]: note
        for note in summary["constant_metadata_notes"]
    } == _EXPECTED_CONSTANT_METADATA_NOTES

    assert AuditArtifact.from_dict(payload).to_dict() == payload
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []


def test_h4_model_schema_and_public_verify_reject_coverage_metadata_mutations(
    tmp_path: Path,
) -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    payload = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED), overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED, overlay_commit=_OVERLAY,
    ).to_dict()
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    def changed_payload() -> dict[str, object]:
        return copy.deepcopy(payload)

    mutations: list[dict[str, object]] = []

    changed = changed_payload()
    coverage = changed["evidence_records"][0]["schedule_observations"]["coverage_assessments"]  # type: ignore[index]
    coverage[5]["observed_values"].append("queued")
    mutations.append(changed)

    changed = changed_payload()
    coverage = changed["evidence_records"][0]["schedule_observations"]["coverage_assessments"]  # type: ignore[index]
    coverage[5]["missing_values"].remove("queued")
    mutations.append(changed)

    changed = changed_payload()
    coverage = changed["evidence_records"][0]["schedule_observations"]["coverage_assessments"]  # type: ignore[index]
    coverage[5]["status"] = "FULLY_OBSERVED"
    mutations.append(changed)

    for ownership_field in ("owner", "reason", "next_gate"):
        changed = changed_payload()
        coverage = changed["evidence_records"][0]["schedule_observations"]["coverage_assessments"]  # type: ignore[index]
        del coverage[5][ownership_field]
        mutations.append(changed)

    changed = changed_payload()
    coverage = changed["evidence_records"][0]["schedule_observations"]["coverage_assessments"]  # type: ignore[index]
    coverage.pop()
    mutations.append(changed)

    changed = changed_payload()
    summary = changed["evidence_records"][0]["schedule_observations"]  # type: ignore[index]
    summary["observations"][0]["final_delivery"] = "ambiguous"
    observation_bytes = json.dumps(
        summary["observations"], sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    summary["digest"] = hashlib.sha256(observation_bytes).hexdigest()
    changed["evidence_records"][0]["content_free_evidence"][1]["digest"] = summary["digest"]  # type: ignore[index]
    mutations.append(changed)

    cli = importlib.import_module("tools.run_plan1126_runtime_audit")
    for mutation_index, changed in enumerate(mutations):
        with pytest.raises(ValueError):
            AuditArtifact.from_dict(changed)
        assert list(validator.iter_errors(changed)), f"schema accepted mutation {mutation_index}"
        artifact_path = tmp_path / f"coverage-mutation-{mutation_index}.json"
        artifact_path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError):
            cli._verify_artifact(str(artifact_path))


def test_h4_render_surfaces_worked_example_evidence_without_payload_content() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    artifact = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED),
        overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
    )
    report = render_markdown(artifact.to_dict())
    record = artifact.to_dict()["evidence_records"][0]
    assert "## Evidence records" in report
    assert "`H4`" in report
    assert "`both-aligned`" in report
    assert f"`{_MERGED}`" in report
    assert f"`{_OVERLAY}`" in report
    assert "`PENDING_G2`" in report
    assert f"{record['contradiction_search']['contradictory_site_count']} contradictory site(s)" in report
    assert "1,000 commit-derived" in report
    assert record["schedule_observations"]["digest"] in report
    assert "Primary scenario counts:" in report
    assert "`preparation-failure`=" in report
    assert "Primary attempts:" in report
    assert "Cancellation timing counts:" in report
    assert "Primary conversation states:" in report
    assert "1,004/1,004 structurally closed" in report
    assert "Settled-vocabulary coverage: `PARTIAL_WITH_SCOPE_OUTS`" in report
    assert "| Observation field | Settled type | Coverage | Observed | Missing | Owner | Next gate | Reason |" in report
    assert "`final_delivery`" in report
    assert "`not_attempted`" in report
    assert "`ambiguous`, `conclusive_failure`, `flushed`, `partial`" in report
    assert "Constant metadata dimensions are not vocabulary-coverage claims:" in report
    assert "`classification`" in report
    assert "`contradiction`" in report
    assert "`complete`" in report
    assert record["commands"][0] in report
    assert record["ruling"] in report
    assert "prompt body" not in report.lower()
    assert "response body" not in report.lower()


def test_evidence_template_pins_h4_seed_count_without_pinning_later_hypotheses() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    payload = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED),
        overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
    ).to_dict()
    schema = __import__("json").loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    later = copy.deepcopy(payload)
    later_record = later["evidence_records"][0]
    later_record["record_id"] = "ER-H5-SHUTDOWN"
    later_record["hypothesis_id"] = "H5"
    later_summary = later_record["schedule_observations"]
    later_summary["derived_seed_count"] = 999
    later_summary["total_observation_count"] = 1_003
    later_summary["complete_observation_count"] = 1_003
    later_summary["classification_counts"]["CANONICAL"] -= 1
    assert list(validator.iter_errors(later)) == []

    invalid_h4 = copy.deepcopy(later)
    invalid_h4["evidence_records"][0]["record_id"] = "ER-H4-DELIVERY"
    invalid_h4["evidence_records"][0]["hypothesis_id"] = "H4"
    assert list(validator.iter_errors(invalid_h4))


def test_delivery_scanner_uses_typed_roles_and_control_flow_not_name_tokens() -> None:
    source = SourceTree({"fixture.py": '''
import asyncio
import concurrent.futures
import queue
from typing import Protocol

class Completion: ...
class SendOutcome: ...

class OutcomeOwner(Protocol):
    def record(self, outcome: SendOutcome) -> None: ...

class Metrics:
    def admit(self, value: object) -> None: ...
    def record(self, value: object) -> None: ...

class Worker:
    def __init__(self):
        self.outbox: queue.Queue[object] = queue.Queue()

    def admit(self, item: object) -> None:
        self.outbox.put(item)

    def execute(self, completion: concurrent.futures.Future[Completion], owner: OutcomeOwner, metrics: Metrics, unrelated, token):
        self.admit(object())
        self.outbox.put(object())
        completion.set_result(Completion())
        owner.record(SendOutcome())
        metrics.admit(object())
        metrics.record(object())
        unrelated.put(object())
        token.set_running_or_notify_cancel()

async def read(reader):
    inbox: asyncio.Queue[object] = asyncio.Queue()
    await inbox.put(object())

def next_ephemeral_send_key():
    return 1
'''})
    sites = inventory_module.discover_delivery_sites(source, overlay=source)
    references = {site.reference for site in sites}

    assert "self.outbox.put" in references
    assert "self.admit" in references
    assert "completion.set_result" in references
    assert "owner.record" in references
    assert "inbox.put" in references
    assert "metrics.admit" not in references
    assert "metrics.record" not in references
    assert "unrelated.put" not in references
    assert "token.set_running_or_notify_cancel" not in references
    assert "next_ephemeral_send_key" not in references
    assert {
        site.delivery_phase
        for site in sites
        if site.reference in {"self.outbox.put", "self.admit", "completion.set_result", "owner.record", "inbox.put"}
    } == {DeliveryPhase.QUEUE_ADMISSION, DeliveryPhase.PUBLICATION}


def test_delivery_scanner_recognizes_settled_write_by_following_owner_publication() -> None:
    merged = _baseline(_MERGED)
    overlay = _baseline(_OVERLAY)
    sites = inventory_module.discover_delivery_sites(merged, overlay=overlay)
    settled_fallbacks = [
        site
        for site in sites
        if site.reference == "writer.write_line"
        and site.symbol.endswith("submit_via_turn")
        and site.baseline_scope is BaselineScope.BOTH_ALIGNED
    ]
    assert settled_fallbacks
    assert {site.classification for site in settled_fallbacks} == {
        Classification.CANONICAL_BYPASSED
    }

    unrelated = SourceTree({"fixture.py": '''
from collections.abc import Mapping
from typing import Protocol

class LineWriter(Protocol):
    async def write_line(self, payload: Mapping[str, object]) -> None: ...

async def send(writer: LineWriter, owner, unrelated_owner):
    lease = owner.start_response_send()
    if lease.granted:
        await writer.write_line({})
        unrelated_owner.publish_authoritative(lease.send_key, SendOutcome.FLUSHED)
'''})
    unrelated_sites = inventory_module.discover_delivery_sites(unrelated, overlay=unrelated)
    writes = [site for site in unrelated_sites if site.reference == "writer.write_line"]
    assert writes
    assert {site.classification for site in writes} == {Classification.CONTRADICTORY}


def test_h4_persists_source_derived_transition_records_not_a_seed_formatter() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    artifact = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED),
        overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
    ).to_dict()
    summary = artifact["evidence_records"][0]["schedule_observations"]
    observations = summary["observations"]
    assert len(observations) == len(literal_seeds()) + 1_000
    assert summary["total_observation_count"] == len(observations)
    assert all(len(item["operations"]) == len(DeliveryPhase) for item in observations)
    assert all(
        [operation["phase"] for operation in item["operations"]]
        == item["schedule"]
        for item in observations
    )
    assert all(
        any(operation["phase"] == "CANCELLATION" for operation in item["operations"])
        for item in observations
    )
    assert {item["scenario"] for item in observations} == {
        "success-known-effect", "success-unknown-effect", "preparation-failure",
        "write-failure", "flush-failure", "session-cancel-before-protocol-write",
        "cancel-after-publication", "transport-teardown",
    }
    assert all(
        next(
            operation["operation"]
            for operation in item["operations"]
            if operation["phase"] == "CANCELLATION"
        ).startswith(("session_cancel_", "transport_teardown_"))
        for item in observations
    )

    settlement_tree = ast.parse(_baseline(_MERGED).read_text("src/optimus/acp/settlement.py"))
    independent_vocabulary = {
        node.name: {
            statement.targets[0].id: statement.value.value
            for statement in node.body
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        }
        for node in settlement_tree.body
        if isinstance(node, ast.ClassDef) and node.name in _SETTLED_VOCABULARY
    }
    assert summary["vocabulary"] == independent_vocabulary
    assert all(
        item["send_state"] in independent_vocabulary["SendState"].values()
        and item["send_outcome"] in independent_vocabulary["SendOutcome"].values()
        and item["settlement"] in independent_vocabulary["Settlement"].values()
        and item["final_delivery"] in independent_vocabulary["FinalDelivery"].values()
        and item["rpc_response_delivery"] in independent_vocabulary["RpcResponseDelivery"].values()
        and item["conversation_commit"] in independent_vocabulary["ConversationCommit"].values()
        and item["effect_state"] in independent_vocabulary["EffectState"].values()
        for item in observations
    )


def test_h4_execution_emits_only_citations_for_behaviors_it_runs() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    merged = _baseline(_MERGED)
    overlay = _baseline(_OVERLAY)
    authority = delivery_module.derive_transition_authority(merged, overlay)
    execution = authority.execute(literal_seeds()[0])
    assert execution.operations
    assert {
        operation.citation for operation in execution.operations
    } <= authority.executed_definition_citations

    payload = delivery_module.build_h4_audit_artifact(
        merged=merged, overlay=overlay, merged_commit=_MERGED, overlay_commit=_OVERLAY,
    ).to_dict()
    observations = payload["evidence_records"][0]["schedule_observations"]["observations"]
    assert len({tuple(item["schedule"]) for item in observations}) >= 6
    assert len({tuple(operation["operation"] for operation in item["operations"]) for item in observations}) >= 8
    assert all(
        set(item["site_citations"]) <= authority.executed_definition_citations
        for item in observations
    )


def test_h4_literal_scenarios_are_coherent_primary_transitions() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    authority = delivery_module.derive_transition_authority(_baseline(_MERGED), _baseline(_OVERLAY))
    expected = {
        0: ("success-known-effect", True, True, "flushed", "after-publication", "accepted", "committed", 1),
        1: ("success-unknown-effect", True, True, "flushed", "after-publication", "accepted", "committed", 1),
        2: ("preparation-failure", False, False, "conclusive_failure", "after-publication", "accepted", "not_committed", 0),
        3: ("write-failure", True, False, "ambiguous", "during-write", "accepted", "not_committed", 0),
        4: ("flush-failure", True, True, "ambiguous", "during-flush", "accepted", "not_committed", 0),
        5: ("session-cancel-before-protocol-write", True, True, "flushed", "before-write", "accepted", "not_committed", 0),
        6: ("cancel-after-publication", True, True, "flushed", "after-publication", "accepted", "committed", 1),
        7: ("transport-teardown", False, False, "suppressed", "before-write", "not_attempted", "not_committed", 0),
    }

    for seed, wanted in expected.items():
        execution = authority.execute(seed)
        actual = (
            execution.scenario,
            execution.write_attempted,
            execution.flush_attempted,
            execution.send_outcome,
            execution.cancellation_timing,
            execution.cancellation_result,
            execution.conversation_commit,
            execution.primary_conversation_record_count,
        )
        assert actual == wanted
        operations = {operation.phase: operation.operation for operation in execution.operations}
        assert not any(
            forbidden in operation
            for operation in operations.values()
            for forbidden in ("control", "substitute")
        )
        assert operations[DeliveryPhase.PHYSICAL_WRITE].startswith(
            "write_attempted_" if execution.write_attempted else "write_not_attempted_"
        )
        assert operations[DeliveryPhase.FLUSH].startswith(
            "flush_attempted_" if execution.flush_attempted else "flush_not_attempted_"
        )
        assert operations[DeliveryPhase.CONVERSATION_COMMIT].startswith(
            "commit_after_final_flush_"
            if execution.conversation_commit == "committed"
            else "commit_withheld_after_prepare_"
        )


def test_h4_behavioral_mutations_change_or_invalidate_primary_observation() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    authority = delivery_module.derive_transition_authority(_baseline(_MERGED), _baseline(_OVERLAY))
    baseline = authority.execute(0)

    class PreparationFailureWriter(authority.dedicated_outbound_writer):
        def _process_item(self, item) -> None:
            item.prepare_error = RuntimeError("content-free injected preparation failure")
            super()._process_item(item)

    writer_mutation = replace(authority, dedicated_outbound_writer=PreparationFailureWriter).execute(0)
    assert (
        writer_mutation.send_outcome,
        writer_mutation.write_attempted,
        writer_mutation.flush_attempted,
    ) != (baseline.send_outcome, baseline.write_attempted, baseline.flush_attempted)

    class NonCommittingConversation(authority.conversation_state):
        def commit_after_final_flush(self, decision) -> None:
            del decision

    conversation_mutation = replace(
        authority, conversation_state=NonCommittingConversation,
    ).execute(0)
    assert conversation_mutation.conversation_commit == "not_committed"
    assert conversation_mutation.primary_conversation_record_count == 0


def test_h4_persists_primary_scenario_coherence_and_rejects_tamper(tmp_path: Path) -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    payload = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED), overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED, overlay_commit=_OVERLAY,
    ).to_dict()
    observations = payload["evidence_records"][0]["schedule_observations"]["observations"]
    coherence_fields = {
        "scenario", "write_attempted", "flush_attempted", "cancellation_timing",
        "cancellation_result", "primary_conversation_record_count",
    }
    assert all(coherence_fields <= set(observation) for observation in observations)
    assert all(
        not any(
            forbidden in operation["operation"]
            for operation in observation["operations"]
            for forbidden in ("control", "substitute")
        )
        for observation in observations
    )

    tampered = copy.deepcopy(payload)
    observation = tampered["evidence_records"][0]["schedule_observations"]["observations"][0]
    observation["write_attempted"] = not observation["write_attempted"]
    with pytest.raises(ValueError, match="attempt"):
        AuditArtifact.from_dict(tampered)

    missing = copy.deepcopy(payload)
    del missing["evidence_records"][0]["schedule_observations"]["observations"][0]["scenario"]
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(missing))

    path = tmp_path / "tampered-primary-coherence.json"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    cli = importlib.import_module("tools.run_plan1126_runtime_audit")
    with pytest.raises(ValueError):
        cli._verify_artifact(str(path))


def test_h4_transition_authority_rejects_immutable_byte_drift() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    merged = _baseline(_MERGED)
    overlay = _baseline(_OVERLAY)

    mutations = (
        (
            "src/optimus/acp/outbound_writer.py",
            "self._queue.put(item)",
            "self._queue.put_nowait(item)",
        ),
        (
            "src/optimus/acp/conversation.py",
            "self._records[decision.turn_seq] = decision.record",
            "self._records.setdefault(decision.turn_seq, decision.record)",
        ),
    )
    for path, before, after in mutations:
        original = merged.read_text(path)
        assert before in original
        changed = SourceTree({
            source_path: (
                original.replace(before, after, 1)
                if source_path == path
                else merged.read_text(source_path)
            )
            for source_path in merged.paths()
        })
        with pytest.raises(ValueError, match="transition authority bytes drifted"):
            delivery_module.derive_transition_authority(changed, overlay)


def test_h4_model_schema_and_public_verify_fail_closed_on_cross_field_mutations(
    tmp_path: Path,
) -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    payload = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED), overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED, overlay_commit=_OVERLAY,
    ).to_dict()
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    def mutation(path: tuple[object, ...], value: object) -> dict[str, object]:
        changed = copy.deepcopy(payload)
        cursor: object = changed
        for part in path[:-1]:
            cursor = cursor[part]  # type: ignore[index]
        cursor[path[-1]] = value  # type: ignore[index]
        return changed

    changes = (
        mutation(("evidence_records", 0, "schedule_observations", "derived_seed_anchor_commit"), _OVERLAY),
        mutation(("evidence_records", 0, "contradiction_search", "searched_reference_count"), 0),
        mutation(("evidence_records", 0, "vocabulary_names"), ["SendState"]),
        mutation(("evidence_records", 0, "schedule_observations", "literal_seeds"), [1, 0, 42, 18446744073709551615]),
        mutation(("evidence_records", 0, "schedule_observations", "derived_seed_count"), 999),
        mutation(("evidence_records", 0, "baseline_scope"), "binding"),
        mutation(("evidence_records", 0, "discovered_sites", 0, "evidence_digest"), "sha256:broken"),
        mutation(("evidence_records", 0, "content_free_evidence", 0, "digest"), "0" * 64),
        mutation(("evidence_records", 0, "schedule_observations", "observations", 0, "send_state"), "queued"),
    )
    for mutation_index, changed in enumerate(changes):
        model_rejected = False
        schema_rejected = bool(list(validator.iter_errors(changed)))
        try:
            AuditArtifact.from_dict(changed)
        except ValueError:
            model_rejected = True
        assert model_rejected or schema_rejected, f"mutation {mutation_index} was accepted"

        artifact_path = tmp_path / "mutated.json"
        artifact_path.write_text(json.dumps(changed), encoding="utf-8")
        cli = importlib.import_module("tools.run_plan1126_runtime_audit")
        with pytest.raises(ValueError):
            cli._verify_artifact(str(artifact_path))

    empty = copy.deepcopy(payload)
    empty["evidence_records"] = []
    with pytest.raises(ValueError):
        AuditArtifact.from_dict(empty)


def test_h4_global_status_and_findings_retain_truthful_partial_lineage() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    payload = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED), overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED, overlay_commit=_OVERLAY,
    ).to_dict()
    assert payload["static_audit_status"] == "PARTIAL"
    assert payload["runtime_characterization_status"] == "PARTIAL"
    assert payload["gate_status"] == "INCOMPLETE"
    site_lineages = {
        (site["classification"], site["baseline_scope"])
        for site in payload["evidence_records"][0]["discovered_sites"]
    }
    finding_lineages = {
        (finding["classification"], finding["baseline_scope"])
        for finding in payload["findings"]
    }
    assert finding_lineages == site_lineages
    assert all(
        {evidence["baseline_scope"] for evidence in finding["evidence"]}
        == {finding["baseline_scope"]}
        for finding in payload["findings"]
    )


def test_public_verify_allows_external_g2_acceptance_without_mechanical_evidence_drift(
    tmp_path: Path,
) -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    payload = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED), overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED, overlay_commit=_OVERLAY,
    ).to_dict()
    record = payload["evidence_records"][0]
    record["reviewer_status"] = "ACCEPTED"
    record["ruling"] = "External G2 accepted the mechanically unchanged H4 evidence."
    path = tmp_path / "accepted.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    cli = importlib.import_module("tools.run_plan1126_runtime_audit")
    verified = cli._verify_artifact(str(path))
    assert verified.evidence_records[0].reviewer_status.value == "ACCEPTED"


@pytest.mark.parametrize(
    "mutation_name",
    ["ACCEPTED_FAKE_COMMAND", "ACCEPTED_SECRET_RULING", "ACCEPTED_SECRET_OWNER"],
)
def test_public_verify_rejects_mutable_or_secret_bearing_h4_metadata(
    mutation_name: str,
    tmp_path: Path,
) -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    payload = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED), overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED, overlay_commit=_OVERLAY,
    ).to_dict()
    if mutation_name == "ACCEPTED_FAKE_COMMAND":
        payload["evidence_records"][0]["commands"][0] = mutation_name
    elif mutation_name == "ACCEPTED_SECRET_RULING":
        payload["evidence_records"][0]["ruling"] = f"{mutation_name}: api_key=sk-h4-private-value"
    else:
        payload["findings"][0]["owner"] = f"{mutation_name}: response body=private-payload"
    path = tmp_path / f"{mutation_name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    cli = importlib.import_module("tools.run_plan1126_runtime_audit")
    with pytest.raises(ValueError):
        cli._verify_artifact(str(path))


def test_h4_render_escapes_content_free_markdown_metadata() -> None:
    delivery_module = importlib.import_module("tools.plan1126_runtime_audit.delivery")
    payload = delivery_module.build_h4_audit_artifact(
        merged=_baseline(_MERGED), overlay=_baseline(_OVERLAY),
        merged_commit=_MERGED, overlay_commit=_OVERLAY,
    ).to_dict()
    hostile = "unsafe | row # heading `tick` <script>x</script>"
    payload["evidence_records"][0]["subject"] = hostile
    payload["evidence_records"][0]["ruling"] = hostile
    payload["evidence_records"][0]["commands"] = [hostile]
    payload["findings"][0]["owner"] = hostile
    payload["findings"][0]["ruling"] = hostile
    report = render_markdown(payload)
    assert hostile not in report
    assert "<script>" not in report
    assert "&lt;script&gt;x&lt;/script&gt;" in report
    assert "unsafe &#124; row # heading &#96;tick&#96;" in report
