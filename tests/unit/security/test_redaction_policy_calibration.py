"""Task 1 calibration canaries for evidence redaction policy contracts.

Proves entropy/prefix/preservation thresholds before they freeze as
evidence-redaction-v1. Never asserts secret or canary *values* in rule
metadata — only content-free rule identifiers and survival/redaction outcomes.
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections import Counter
from pathlib import Path

import pytest

from optimus_security import sanitization as sanitization_mod

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "evidence"
CANARIES = json.loads((FIXTURES / "redaction_canaries.json").read_text(encoding="utf-8"))
ZED_LINE = (FIXTURES / "zed_rust_debug_line.txt").read_text(encoding="utf-8").rstrip("\n")

PREFIXES = (
    "sk-or-v1-",
    "sk-ant-",
    "sk-proj-",
    "sk-",
    "tvly-",
    "AIza",
    "ghp_",
    "github_pat_",
)


def _shannon(token: str) -> float:
    length = len(token)
    counts = Counter(token)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _char_classes(token: str) -> int:
    return sum(
        [
            any(ch.islower() for ch in token),
            any(ch.isupper() for ch in token),
            any(ch.isdigit() for ch in token),
            any(not ch.isalnum() for ch in token),
        ]
    )


class TestCanaryEntropyProperties:
    def test_unlabeled_api_key_is_32_char_five_bit_candidate(self) -> None:
        key = CANARIES["unlabeled_api_key"]
        assert len(key) == 32
        assert _shannon(key) == pytest.approx(5.0)
        assert _char_classes(key) >= 2

    def test_session_run_gateway_exceed_entropy_threshold(self) -> None:
        for field in ("session_id", "run_id", "gateway_request_id"):
            token = CANARIES[field]
            assert 24 <= len(token) <= 256
            assert _char_classes(token) >= 2
            assert _shannon(token) >= 4.0

    def test_git_and_artifact_sha_are_entropy_non_candidates(self) -> None:
        git_sha = CANARIES["git_sha"]
        artifact = CANARIES["artifact_sha256"]
        assert _shannon(git_sha) < 4.0
        assert _shannon(artifact) < 4.0
        assert sanitization_mod.is_git_sha_shape(git_sha)
        assert sanitization_mod.is_artifact_sha256_shape(artifact)


class TestEvidencePolicyCanaries:
    def test_prefix_grammars_catch_bounded_canaries_without_entropy(self) -> None:
        policy = sanitization_mod.EVIDENCE_REDACTION_POLICY
        for prefix in PREFIXES:
            canary = prefix + ("a" * 16)
            # Uniform 'a' has entropy 0 — prefix rule must still fire.
            assert _shannon(canary[len(prefix) :]) == 0.0
            result = sanitization_mod.sanitize_for_persistence(
                f"wire-dump {canary} trailing",
                policy=policy,
            )
            assert canary not in str(result.value)
            assert result.rule_counts.get("prefix_redaction", 0) >= 1

    def test_email_and_known_pii_use_distinct_rule_ids(self) -> None:
        policy = sanitization_mod.EVIDENCE_REDACTION_POLICY
        email_result = sanitization_mod.sanitize_for_persistence(
            "contact ops@example.com please",
            policy=policy,
        )
        pii_result = sanitization_mod.sanitize_for_persistence(
            "operator vibhanshu-canary-pii was here",
            known_pii=["vibhanshu-canary-pii"],
            policy=policy,
        )
        assert email_result.rule_counts.get("email_masking", 0) >= 1
        assert pii_result.rule_counts.get("known_pii_replacement", 0) >= 1
        assert "email_masking" != "known_pii_replacement"
        assert "email_masking" in email_result.rule_counts
        assert "known_pii_replacement" in pii_result.rule_counts
        assert "known_pii_replacement" not in email_result.rule_counts
        assert "email_masking" not in pii_result.rule_counts

    def test_labeled_high_entropy_ids_survive_only_via_validators(self) -> None:
        policy = sanitization_mod.EVIDENCE_REDACTION_POLICY
        payload = {
            "session_id": CANARIES["session_id"],
            "run_id": CANARIES["run_id"],
            "gateway_request_id": CANARIES["gateway_request_id"],
        }
        result = sanitization_mod.sanitize_for_persistence(payload, policy=policy)
        assert result.value == payload
        free_text = (
            f'session_id={CANARIES["session_id"]} '
            f'runId: {CANARIES["run_id"]} '
            f'gateway_request_id={CANARIES["gateway_request_id"]}'
        )
        text_result = sanitization_mod.sanitize_for_persistence(free_text, policy=policy)
        assert CANARIES["session_id"] in str(text_result.value)
        assert CANARIES["run_id"] in str(text_result.value)
        assert CANARIES["gateway_request_id"] in str(text_result.value)
        assert text_result.rule_counts.get("entropy_redaction", 0) == 0

    def test_git_and_artifact_survive_via_field_shape_not_entropy_override(self) -> None:
        policy = sanitization_mod.EVIDENCE_REDACTION_POLICY
        payload = {
            "git_sha": CANARIES["git_sha"],
            "artifact_sha256": CANARIES["artifact_sha256"],
        }
        result = sanitization_mod.sanitize_for_persistence(payload, policy=policy)
        assert result.value == payload
        # Not entropy candidates — must not be explained as label-over-entropy.
        assert _shannon(CANARIES["git_sha"]) < 4.0
        assert _shannon(CANARIES["artifact_sha256"]) < 4.0
        assert result.rule_counts.get("entropy_redaction", 0) == 0

    def test_unlabeled_api_key_is_detected(self) -> None:
        policy = sanitization_mod.EVIDENCE_REDACTION_POLICY
        key = CANARIES["unlabeled_api_key"]
        result = sanitization_mod.sanitize_for_persistence(
            f"debug dump {key} end",
            policy=policy,
        )
        assert key not in str(result.value)
        assert result.rule_counts.get("entropy_redaction", 0) >= 1

    def test_labeled_neighbor_does_not_preserve_unlabeled_canary(self) -> None:
        policy = sanitization_mod.EVIDENCE_REDACTION_POLICY
        key = CANARIES["unlabeled_api_key"]
        line = f'session_id={CANARIES["session_id"]} {key}'
        result = sanitization_mod.sanitize_for_persistence(line, policy=policy)
        assert CANARIES["session_id"] in str(result.value)
        assert key not in str(result.value)

    def test_zed_rust_debug_preserves_session_and_redacts_unlabeled_key(self) -> None:
        policy = sanitization_mod.EVIDENCE_REDACTION_POLICY
        key = CANARIES["unlabeled_api_key"]
        assert key in ZED_LINE
        assert CANARIES["session_id"] in ZED_LINE
        assert 'sessionId": String("' in ZED_LINE
        result = sanitization_mod.sanitize_for_persistence(ZED_LINE, policy=policy)
        sanitized = str(result.value)
        assert CANARIES["session_id"] in sanitized
        assert key not in sanitized
        assert result.rule_counts.get("entropy_redaction", 0) >= 1


class TestCompatibilityPolicyDefaults:
    def test_calls_without_policy_match_pre_task_behavior_for_clean_text(self) -> None:
        text = "no secrets here"
        result = sanitization_mod.sanitize_for_persistence(text, known_secrets=[])
        assert result.value == text
        assert result.rule_counts == {}

    def test_evidence_only_rules_inactive_under_compatibility_policy(self) -> None:
        key = CANARIES["unlabeled_api_key"]
        result = sanitization_mod.sanitize_for_persistence(
            f"debug dump {key} end",
            policy=sanitization_mod.COMPATIBILITY_SANITIZATION_POLICY,
        )
        assert key in str(result.value)
        assert result.rule_counts.get("entropy_redaction", 0) == 0
        assert result.rule_counts.get("prefix_redaction", 0) == 0
        assert result.rule_counts.get("email_masking", 0) == 0

    def test_policy_constants_are_frozen_and_versioned(self) -> None:
        assert sanitization_mod.EVIDENCE_REDACTION_POLICY.version == "evidence-redaction-v1"
        assert sanitization_mod.COMPATIBILITY_SANITIZATION_POLICY.version == "compatibility-v1"
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            sanitization_mod.EVIDENCE_REDACTION_POLICY.version = "mutated"  # type: ignore[misc]
