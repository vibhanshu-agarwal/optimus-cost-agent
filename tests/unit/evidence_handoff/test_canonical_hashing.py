"""Deterministic canonical JSON and content digest contracts."""

from __future__ import annotations


def test_canonical_json_is_deterministic_sorted_utf8() -> None:
    from evidence_handoff.ledger.canonical import canonical_json

    left = canonical_json({"b": 1, "a": {"z": True, "m": [2, 1]}})
    right = canonical_json({"a": {"m": [2, 1], "z": True}, "b": 1})
    assert left == right
    assert left == b'{"a":{"m":[2,1],"z":true},"b":1}'


def test_content_sha256_covers_chain_fields_and_excludes_digest_field() -> None:
    from evidence_handoff.ledger.canonical import content_sha256_for_envelope

    base = {
        "sequence": 1,
        "ledger_instance_id": "inst-1",
        "entry_id": "entry-1",
        "schema_id": "review-ruling.v1",
        "kind": "review-ruling",
        "context_id": "ctx",
        "task_id": None,
        "in_reply_to": None,
        "recipient_agent_ids": ["a1"],
        "message": {"parts": [{"kind": "text", "text": "ok"}]},
        "artifacts": [],
        "principal_id": "p1",
        "agent_id": "reviewer-1",
        "caller_role": "reviewer",
        "authority": "review-ruling",
        "attestation": None,
        "created_at": "2026-08-08T00:00:00+00:00",
        "idempotency_key": "idem-1",
        "prev_content_sha256": None,
    }
    digest = content_sha256_for_envelope(base)
    assert len(digest) == 64
    assert digest == content_sha256_for_envelope({**base, "content_sha256": "should-be-ignored"})

    changed_sequence = content_sha256_for_envelope({**base, "sequence": 2})
    changed_instance = content_sha256_for_envelope({**base, "ledger_instance_id": "inst-2"})
    changed_prev = content_sha256_for_envelope({**base, "prev_content_sha256": "a" * 64})
    assert digest != changed_sequence
    assert digest != changed_instance
    assert digest != changed_prev
