"""Orchestrate live evidence verification without synthesizing agent results."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .canary import scan_raw_canaries
from .constants import EXPECTED_CLIENT_NAMES
from .errors import VerificationError
from .manifest import load_manifest, validate_manifest

# Derived only from per-agent outcome strings — never from self-declared flags.
REQUIRED_OUTCOMES: frozenset[str] = frozenset(
    {
        "reviewer_append_succeeds",
        "implementer_review_ruling_append_rejected",
        "sequence_and_counter_unchanged_on_implementer_reject",
        "each_client_confirms_a_real_page",
        "post_latch_next_interaction_emits_ledger_integrity_failed",
        "no_automatic_relay_after_latch",
    }
)


def _require_absolute_root(evidence_root: Path | None) -> Path:
    if evidence_root is None:
        raise VerificationError("missing_evidence_root", "evidence_root is required")
    if not isinstance(evidence_root, Path):
        raise VerificationError("missing_evidence_root", "evidence_root must be a Path")
    if not evidence_root.is_absolute():
        raise VerificationError("evidence_root_not_absolute", "evidence_root must be absolute")
    if not evidence_root.exists():
        raise VerificationError("evidence_incomplete", f"evidence_root does not exist: {evidence_root}")
    if not evidence_root.is_dir():
        raise VerificationError("evidence_incomplete", f"evidence_root is not a directory: {evidence_root}")
    return evidence_root


def _require_service_endpoint(service_endpoint: str | None) -> str:
    if service_endpoint is None or not str(service_endpoint).strip():
        raise VerificationError("missing_service_endpoint", "service_endpoint is required")
    endpoint = str(service_endpoint).strip()
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise VerificationError("missing_service_endpoint", "service_endpoint must be an http(s) URL")
    return endpoint


def _outcomes_for_agent(agent: dict[str, Any]) -> set[str]:
    collected: set[str] = set()
    singular = agent.get("outcome")
    if singular is not None and str(singular).strip():
        collected.add(str(singular))
    extra = agent.get("outcomes")
    if isinstance(extra, list):
        collected.update(str(item) for item in extra if str(item).strip())
    return collected


def verify_evidence_root(
    *,
    evidence_root: Path | None,
    service_endpoint: str | None,
    expected_agent_ids: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    """Verify an operator-supplied content-free live evidence root.

    Does not launch agents, emulate MCP, or create credentials.
    Pass/fail is derived strictly from per-agent outcome evidence — never from
    self-declared ``verification_flags``.
    """
    root = _require_absolute_root(evidence_root)
    endpoint = _require_service_endpoint(service_endpoint)
    expected = tuple(str(item) for item in expected_agent_ids)

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        scenario = root / "three_agent_scenario.json"
        if scenario.is_file():
            raise VerificationError(
                "scenario_shape_insufficient",
                "evidence root has scenario fixture but no live manifest.json",
            )
        raise VerificationError("evidence_incomplete", "manifest.json missing from evidence root")

    payload = load_manifest(manifest_path)
    # verification_flags is non-authoritative metadata only; never consulted for pass/fail.
    if "verification_flags" in payload and payload.get("verification_flags") is not None:
        if not isinstance(payload.get("verification_flags"), dict):
            raise VerificationError("missing_manifest_field", "verification_flags must be an object")

    agents = validate_manifest(payload, expected_agent_ids=expected)

    client_names = {str(agent["client_name"]) for agent in agents}
    if not EXPECTED_CLIENT_NAMES.issubset(client_names) or len(agents) != 3:
        raise VerificationError(
            "missing_client_identity",
            f"native clients incomplete: {sorted(client_names)}",
        )

    outcomes: set[str] = set()
    for agent in agents:
        outcomes.update(_outcomes_for_agent(agent))

    reviewers = [agent for agent in agents if str(agent["client_name"]) in {"claude_code", "cursor"}]
    implementer = next((agent for agent in agents if str(agent["client_name"]) == "codex"), None)

    # reviewer_append_succeeds must come from a reviewer record, never Codex alone.
    reviewer_append_ok = any(
        "reviewer_append_succeeds" in _outcomes_for_agent(agent) for agent in reviewers
    )
    if not reviewer_append_ok:
        raise VerificationError(
            "required_outcomes_missing",
            "reviewer_append_succeeds must be recorded by claude_code or cursor, not only codex",
        )

    # each_client_confirms_a_real_page — every native client, own record (like post_latch).
    confirmers = {
        str(agent["client_name"])
        for agent in agents
        if "each_client_confirms_a_real_page" in _outcomes_for_agent(agent)
    }
    if confirmers < EXPECTED_CLIENT_NAMES:
        raise VerificationError(
            "required_outcomes_missing",
            "each native client must record each_client_confirms_a_real_page on its own record",
        )

    implementer_rejected = bool(
        implementer is not None
        and "implementer_review_ruling_append_rejected" in _outcomes_for_agent(implementer)
    )
    if not implementer_rejected:
        raise VerificationError(
            "required_outcomes_missing",
            "implementer (codex) must record implementer_review_ruling_append_rejected",
        )

    sequence_unchanged = "sequence_and_counter_unchanged_on_implementer_reject" in outcomes
    if not sequence_unchanged:
        raise VerificationError(
            "required_outcomes_missing",
            "sequence_and_counter_unchanged_on_implementer_reject missing",
        )

    post_latch: dict[str, str] = {}
    for agent in agents:
        name = str(agent["client_name"])
        if "post_latch_next_interaction_emits_ledger_integrity_failed" in _outcomes_for_agent(agent):
            post_latch[name] = "ledger_integrity_failed"
    if set(post_latch) < EXPECTED_CLIENT_NAMES:
        raise VerificationError(
            "required_outcomes_missing",
            "each native client must record post_latch_next_interaction_emits_ledger_integrity_failed",
        )

    if "no_automatic_relay_after_latch" not in outcomes:
        raise VerificationError(
            "required_outcomes_missing",
            "no_automatic_relay_after_latch outcome required",
        )

    # Remaining required outcomes that are still global (delivery / authority) must appear
    # somewhere in the union — they cannot be satisfied solely by the checks above.
    remaining = REQUIRED_OUTCOMES - {
        "reviewer_append_succeeds",
        "each_client_confirms_a_real_page",
        "implementer_review_ruling_append_rejected",
        "sequence_and_counter_unchanged_on_implementer_reject",
        "post_latch_next_interaction_emits_ledger_integrity_failed",
        "no_automatic_relay_after_latch",
    }
    if remaining and not remaining.issubset(outcomes):
        raise VerificationError(
            "required_outcomes_missing",
            f"missing required outcomes: {sorted(remaining - outcomes)}",
        )

    canary = scan_raw_canaries(root)
    if not canary["clean"]:
        raise VerificationError("token_in_manifest", f"raw canary hits={canary['hit_count']}")

    return {
        "passed": True,
        "service_endpoint": endpoint,
        "evidence_root": str(root),
        "client_names": sorted(client_names),
        "agent_ids": [str(agent["agent_id"]) for agent in agents],
        "implementer_append_rejected": implementer_rejected,
        "sequence_unchanged_on_implementer_reject": sequence_unchanged,
        "post_latch_warnings": dict(post_latch),
        "automatic_relay": False,
        "canary": canary,
        "outcomes": sorted(outcomes),
        "verification_flags_ignored": bool(payload.get("verification_flags")),
    }


def inspect_evidence_root(*, evidence_root: Path | None) -> dict[str, Any]:
    """Content-free inspection: digests/identities present plus raw-canary scan."""
    root = _require_absolute_root(evidence_root)
    manifest_path = root / "manifest.json"
    summary: dict[str, Any] = {
        "evidence_root": str(root),
        "manifest_present": manifest_path.is_file(),
        "canary": scan_raw_canaries(root),
    }
    if manifest_path.is_file():
        payload = load_manifest(manifest_path)
        agents = payload.get("agents") if isinstance(payload.get("agents"), list) else []
        summary["agent_count"] = len(agents)
        from .manifest import _walk_for_token_fields

        token_path = _walk_for_token_fields(payload)
        summary["has_tokens"] = token_path is not None
        summary["scenario_shape"] = payload.get("purpose") == "scenario_shape_only"
    return summary
