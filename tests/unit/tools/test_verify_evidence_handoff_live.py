"""RED contract tests for the evidence-handoff live verifier (Task 10 Step 1).

Verifier production code is intentionally absent at RED. These tests define the
reject/accept surface from the frozen plan Interfaces bullets; GREEN must make
them pass without accepting scenario-shape fixtures or mocks as live evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "evidence_handoff" / "three_agent_scenario.json"
)
VERIFIER_MODULE = "tools.verify_evidence_handoff_live"
VERIFIER_PATH = REPO_ROOT / "tools" / "verify_evidence_handoff_live.py"


REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "client_name",
        "client_version",
        "agent_id",
        "principal_id",
        "service_identity",
        "store_identity",
        "request_digest",
        "entry_digest",
        "delivery_digest",
        "outcome",
    }
)


def _import_verifier():
    return __import__(VERIFIER_MODULE, fromlist=["*"])


def test_verifier_entrypoints_exist() -> None:
    assert VERIFIER_PATH.is_file(), "tools/verify_evidence_handoff_live.py must exist"
    verifier = _import_verifier()
    assert callable(getattr(verifier, "verify_evidence", None))
    assert callable(getattr(verifier, "inspect_evidence", None))
    assert callable(getattr(verifier, "main", None))


def test_scenario_fixture_is_shape_only_and_never_a_pass_artifact() -> None:
    assert SCENARIO_FIXTURE.is_file()
    scenario = json.loads(SCENARIO_FIXTURE.read_text(encoding="utf-8"))
    assert scenario["purpose"] == "scenario_shape_only"
    assert scenario["pass_forbidden_without_real_evidence"] is True
    assert "disclaimer" in scenario and "never be accepted as a passing" in scenario["disclaimer"]
    agent_ids = [row["agent_id"] for row in scenario["agents"]]
    assert len(agent_ids) == 3
    assert len(set(agent_ids)) == 3
    roles = {row["role"] for row in scenario["agents"]}
    assert roles == {"reviewer", "implementer"}
    clients = {row["client_name"] for row in scenario["agents"]}
    assert clients == {"claude_code", "cursor", "codex"}
    assert frozenset(scenario["required_manifest_fields"]) == REQUIRED_MANIFEST_FIELDS
    # Placeholders must not look like committed digest or credential material.
    blob = json.dumps(scenario)
    assert "sk-" not in blob
    assert "Bearer " not in blob
    assert "sha256:" not in blob.lower()


def test_verify_rejects_missing_and_relative_evidence_root(tmp_path: Path) -> None:
    verifier = _import_verifier()
    with pytest.raises(verifier.VerificationError) as missing:
        verifier.verify_evidence(
            evidence_root=None,
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("a", "b", "c"),
        )
    assert missing.value.code == "missing_evidence_root"

    with pytest.raises(verifier.VerificationError) as relative:
        verifier.verify_evidence(
            evidence_root=Path("relative-evidence"),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("a", "b", "c"),
        )
    assert relative.value.code == "evidence_root_not_absolute"


def test_verify_rejects_missing_service_endpoint(tmp_path: Path) -> None:
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="",
            expected_agent_ids=("a", "b", "c"),
        )
    assert raised.value.code == "missing_service_endpoint"


def test_verify_rejects_duplicate_credentials(tmp_path: Path) -> None:
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "client_name": "claude_code",
                        "client_version": "1.0.0",
                        "agent_id": "agent-a",
                        "principal_id": "principal-a",
                        "credential_fingerprint": "same-fingerprint",
                        "service_identity": "svc-1",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "reviewer_append_succeeds",
                        "process_identity": "pid-a",
                    },
                    {
                        "client_name": "cursor",
                        "client_version": "1.0.0",
                        "agent_id": "agent-b",
                        "principal_id": "principal-b",
                        "credential_fingerprint": "same-fingerprint",
                        "service_identity": "svc-1",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "each_client_confirms_a_real_page",
                        "process_identity": "pid-b",
                    },
                    {
                        "client_name": "codex",
                        "client_version": "1.0.0",
                        "agent_id": "agent-c",
                        "principal_id": "principal-c",
                        "credential_fingerprint": "other-fingerprint",
                        "service_identity": "svc-1",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "implementer_review_ruling_append_rejected",
                        "process_identity": "pid-c",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("agent-a", "agent-b", "agent-c"),
        )
    assert raised.value.code == "duplicate_credentials"


def test_verify_rejects_non_distinct_agents(tmp_path: Path) -> None:
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "client_name": "claude_code",
                        "client_version": "1.0.0",
                        "agent_id": "shared-agent",
                        "principal_id": "principal-a",
                        "credential_fingerprint": "fp-a",
                        "service_identity": "svc-1",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "reviewer_append_succeeds",
                        "process_identity": "pid-a",
                    },
                    {
                        "client_name": "cursor",
                        "client_version": "1.0.0",
                        "agent_id": "shared-agent",
                        "principal_id": "principal-b",
                        "credential_fingerprint": "fp-b",
                        "service_identity": "svc-1",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "each_client_confirms_a_real_page",
                        "process_identity": "pid-b",
                    },
                    {
                        "client_name": "codex",
                        "client_version": "1.0.0",
                        "agent_id": "agent-c",
                        "principal_id": "principal-c",
                        "credential_fingerprint": "fp-c",
                        "service_identity": "svc-1",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "implementer_review_ruling_append_rejected",
                        "process_identity": "pid-c",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("shared-agent", "agent-c", "agent-d"),
        )
    assert raised.value.code == "non_distinct_agents"


def test_verify_rejects_missing_manifest_fields(tmp_path: Path) -> None:
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "client_name": "claude_code",
                        "agent_id": "agent-a",
                        "principal_id": "principal-a",
                        # intentionally omit client_version and digests
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("agent-a", "agent-b", "agent-c"),
        )
    assert raised.value.code == "missing_manifest_field"


def test_verify_rejects_fabricated_dependency_identities(tmp_path: Path) -> None:
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "client_name": "claude_code",
                        "client_version": "1.0.0",
                        "agent_id": "agent-a",
                        "principal_id": "principal-a",
                        "credential_fingerprint": "fp-a",
                        "service_identity": "fabricated-service",
                        "store_identity": "fabricated-store",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "reviewer_append_succeeds",
                        "process_identity": "pid-a",
                    }
                ],
                "dependency_identities": {
                    "service": "real-service-from-lifecycle",
                    "store": "real-store-from-lifecycle",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("agent-a", "agent-b", "agent-c"),
        )
    assert raised.value.code == "fabricated_dependency_identity"


def test_verify_rejects_tokens_in_manifest(tmp_path: Path) -> None:
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "client_name": "claude_code",
                        "client_version": "1.0.0",
                        "agent_id": "agent-a",
                        "principal_id": "principal-a",
                        "credential_fingerprint": "fp-a",
                        "service_identity": "svc-1",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "reviewer_append_succeeds",
                        "process_identity": "pid-a",
                        "access_token": "secret-token-value",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("agent-a", "agent-b", "agent-c"),
        )
    assert raised.value.code == "token_in_manifest"


def test_verify_rejects_evidence_lacking_real_client_process_store_identity(
    tmp_path: Path,
) -> None:
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "client_name": "claude_code",
                        "client_version": "1.0.0",
                        "agent_id": "agent-a",
                        "principal_id": "principal-a",
                        "credential_fingerprint": "fp-a",
                        "service_identity": "svc-1",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "reviewer_append_succeeds",
                        # missing process_identity
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("agent-a", "agent-b", "agent-c"),
        )
    assert raised.value.code in {
        "missing_process_identity",
        "missing_client_identity",
        "missing_store_identity",
        "missing_manifest_field",
    }


def test_skipped_agent_or_mocked_service_cannot_be_marked_passed(tmp_path: Path) -> None:
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "client_name": "claude_code",
                        "client_version": "1.0.0",
                        "agent_id": "agent-a",
                        "principal_id": "principal-a",
                        "credential_fingerprint": "fp-a",
                        "service_identity": "svc-1",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "reviewer_append_succeeds",
                        "process_identity": "pid-a",
                        "status": "skipped",
                        "passed": True,
                    },
                    {
                        "client_name": "cursor",
                        "client_version": "1.0.0",
                        "agent_id": "agent-b",
                        "principal_id": "principal-b",
                        "credential_fingerprint": "fp-b",
                        "service_identity": "svc-1",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "each_client_confirms_a_real_page",
                        "process_identity": "pid-b",
                        "status": "passed",
                        "passed": True,
                    },
                    {
                        "client_name": "codex",
                        "client_version": "1.0.0",
                        "agent_id": "agent-c",
                        "principal_id": "principal-c",
                        "credential_fingerprint": "fp-c",
                        "service_identity": "mocked-service",
                        "store_identity": "store-1",
                        "request_digest": "r" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "d" * 64,
                        "outcome": "implementer_review_ruling_append_rejected",
                        "process_identity": "pid-c",
                        "status": "passed",
                        "passed": True,
                        "service_mode": "mock",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("agent-a", "agent-b", "agent-c"),
        )
    assert raised.value.code in {
        "skipped_agent_marked_passed",
        "mocked_service_marked_passed",
    }


def test_scenario_fixture_alone_cannot_satisfy_verify(tmp_path: Path) -> None:
    """Standing Task 10 constraint: shape fixture must never be a green path."""
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    # Copying the scenario fixture into an evidence root must not verify as pass.
    root.joinpath("manifest.json").write_text(
        SCENARIO_FIXTURE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=(
                "REVIEWER_CLAUDE_AGENT_ID",
                "REVIEWER_CURSOR_AGENT_ID",
                "IMPLEMENTER_CODEX_AGENT_ID",
            ),
        )
    assert raised.value.code in {
        "scenario_shape_insufficient",
        "missing_manifest_field",
        "missing_process_identity",
        "fabricated_dependency_identity",
    }


def test_verification_flags_cannot_override_missing_real_outcomes(tmp_path: Path) -> None:
    """Adversarial: self-declared verification_flags must never create a pass.

    Well-formed distinct agents with nonsense outcomes plus flags claiming success
    must raise — not return passed=true (reviewer Finding on Task 10 Step 2).
    """
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    nonsense = "agent_was_launched_and_did_nothing_useful"
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "client_name": "claude_code",
                        "client_version": "1.0.0",
                        "agent_id": "agent-a",
                        "principal_id": "principal-a",
                        "credential_fingerprint": "fp-a",
                        "service_identity": "svc-live-1",
                        "store_identity": "store-live-1",
                        "request_digest": "a" * 64,
                        "entry_digest": "b" * 64,
                        "delivery_digest": "c" * 64,
                        "outcome": nonsense,
                        "process_identity": "pid-a",
                    },
                    {
                        "client_name": "cursor",
                        "client_version": "1.0.0",
                        "agent_id": "agent-b",
                        "principal_id": "principal-b",
                        "credential_fingerprint": "fp-b",
                        "service_identity": "svc-live-1",
                        "store_identity": "store-live-1",
                        "request_digest": "d" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "f" * 64,
                        "outcome": nonsense,
                        "process_identity": "pid-b",
                    },
                    {
                        "client_name": "codex",
                        "client_version": "1.0.0",
                        "agent_id": "agent-c",
                        "principal_id": "principal-c",
                        "credential_fingerprint": "fp-c",
                        "service_identity": "svc-live-1",
                        "store_identity": "store-live-1",
                        "request_digest": "1" * 64,
                        "entry_digest": "2" * 64,
                        "delivery_digest": "3" * 64,
                        "outcome": nonsense,
                        "process_identity": "pid-c",
                    },
                ],
                "dependency_identities": {
                    "service": "svc-live-1",
                    "store": "store-live-1",
                },
                "verification_flags": {
                    "implementer_append_rejected": True,
                    "sequence_unchanged_on_implementer_reject": True,
                    "post_latch_warnings": {
                        "claude_code": "ledger_integrity_failed",
                        "cursor": "ledger_integrity_failed",
                        "codex": "ledger_integrity_failed",
                    },
                    "scenario_outcomes_confirmed": True,
                    "automatic_relay": False,
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError) as raised:
        result = verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("agent-a", "agent-b", "agent-c"),
        )
        # If no raise, the bypass is still open — force failure with evidence.
        raise AssertionError(f"verification_flags bypass still open: {result}")
    assert raised.value.code == "required_outcomes_missing"
    assert raised.value.code != "scenario_shape_insufficient"


def test_role_bound_outcomes_reject_implementer_claiming_reviewer_success(
    tmp_path: Path,
) -> None:
    """Aggregate union must not let Codex satisfy reviewer-only / each-client outcomes.

    Codex may correctly record implementer rejection, but must not satisfy
    reviewer_append_succeeds or stand in for each_client_confirms_a_real_page
    when Claude Code / Cursor never confirm a page themselves.
    """
    verifier = _import_verifier()
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "client_name": "claude_code",
                        "client_version": "1.0.0",
                        "agent_id": "agent-a",
                        "principal_id": "principal-a",
                        "credential_fingerprint": "fp-a",
                        "service_identity": "svc-live-1",
                        "store_identity": "store-live-1",
                        "request_digest": "a" * 64,
                        "entry_digest": "b" * 64,
                        "delivery_digest": "c" * 64,
                        "outcome": "post_latch_next_interaction_emits_ledger_integrity_failed",
                        "outcomes": [
                            "post_latch_next_interaction_emits_ledger_integrity_failed",
                            "no_automatic_relay_after_latch",
                            "sequence_and_counter_unchanged_on_implementer_reject",
                        ],
                        "process_identity": "pid-a",
                    },
                    {
                        "client_name": "cursor",
                        "client_version": "1.0.0",
                        "agent_id": "agent-b",
                        "principal_id": "principal-b",
                        "credential_fingerprint": "fp-b",
                        "service_identity": "svc-live-1",
                        "store_identity": "store-live-1",
                        "request_digest": "d" * 64,
                        "entry_digest": "e" * 64,
                        "delivery_digest": "f" * 64,
                        "outcome": "post_latch_next_interaction_emits_ledger_integrity_failed",
                        "outcomes": [
                            "post_latch_next_interaction_emits_ledger_integrity_failed",
                        ],
                        "process_identity": "pid-b",
                    },
                    {
                        "client_name": "codex",
                        "client_version": "1.0.0",
                        "agent_id": "agent-c",
                        "principal_id": "principal-c",
                        "credential_fingerprint": "fp-c",
                        "service_identity": "svc-live-1",
                        "store_identity": "store-live-1",
                        "request_digest": "1" * 64,
                        "entry_digest": "2" * 64,
                        "delivery_digest": "3" * 64,
                        "outcome": "implementer_review_ruling_append_rejected",
                        "outcomes": [
                            "implementer_review_ruling_append_rejected",
                            "reviewer_append_succeeds",
                            "each_client_confirms_a_real_page",
                            "post_latch_next_interaction_emits_ledger_integrity_failed",
                        ],
                        "process_identity": "pid-c",
                    },
                ],
                "dependency_identities": {
                    "service": "svc-live-1",
                    "store": "store-live-1",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError) as raised:
        result = verifier.verify_evidence(
            evidence_root=root.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=("agent-a", "agent-b", "agent-c"),
        )
        raise AssertionError(f"role-bound outcome gap still open: {result}")
    assert raised.value.code == "required_outcomes_missing"
