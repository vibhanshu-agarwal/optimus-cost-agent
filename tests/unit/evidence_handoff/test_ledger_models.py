"""Portable ledger model contracts for the immutable entry envelope."""

from __future__ import annotations

import pytest


def test_entry_kind_contains_all_six_design_values() -> None:
    from evidence_handoff.ledger.models import EntryKind

    assert {kind.value for kind in EntryKind} == {
        "question",
        "answer",
        "evidence-notice",
        "review-ruling",
        "handoff",
        "acknowledgement",
    }


def test_only_review_ruling_is_active_writer_kind() -> None:
    from evidence_handoff.ledger.models import ACTIVE_WRITER_KINDS, EntryKind

    assert ACTIVE_WRITER_KINDS == frozenset({EntryKind.REVIEW_RULING})


def test_schema_ids_are_versioned_and_kind_aligned() -> None:
    from evidence_handoff.ledger.models import SCHEMA_ID_BY_KIND, EntryKind, SchemaId

    assert SchemaId.REVIEW_RULING.value == "review-ruling.v1"
    for kind in EntryKind:
        assert kind in SCHEMA_ID_BY_KIND
        assert SCHEMA_ID_BY_KIND[kind].endswith(".v1")


def test_entry_draft_rejects_server_owned_fields() -> None:
    from evidence_handoff.ledger.errors import LedgerValidationError
    from evidence_handoff.ledger.models import EntryDraft

    with pytest.raises(LedgerValidationError) as raised:
        EntryDraft.from_mapping(
            {
                "kind": "review-ruling",
                "schema_id": "review-ruling.v1",
                "context_id": "ctx-1",
                "recipient_agent_ids": ["reviewer-1"],
                "message": {"parts": [{"kind": "text", "text": "ok"}]},
                "principal_id": "should-not-be-here",
            }
        )
    assert raised.value.code == "unexpected_server_owned_field"


def test_entry_draft_rejects_non_null_attestation_and_bad_recipients() -> None:
    from evidence_handoff.ledger.errors import LedgerValidationError
    from evidence_handoff.ledger.models import EntryDraft, EntryKind, EntryMessage, MessagePart, SchemaId

    base = dict(
        kind=EntryKind.REVIEW_RULING,
        schema_id=SchemaId.REVIEW_RULING.value,
        context_id="ctx-1",
        message=EntryMessage(parts=(MessagePart(kind="text", text="ruling"),)),
    )
    with pytest.raises(LedgerValidationError) as attestation:
        EntryDraft(**base, recipient_agent_ids=("a1",), attestation={"sig": "x"})
    assert attestation.value.code == "attestation_must_be_null"

    with pytest.raises(LedgerValidationError) as empty:
        EntryDraft(**base, recipient_agent_ids=())
    assert empty.value.code == "recipients_required"

    with pytest.raises(LedgerValidationError) as dupes:
        EntryDraft(**base, recipient_agent_ids=("a1", "a1"))
    assert dupes.value.code == "duplicate_recipients"


def test_entry_draft_rejects_inactive_writer_kinds() -> None:
    from evidence_handoff.ledger.errors import LedgerValidationError
    from evidence_handoff.ledger.models import EntryDraft, EntryKind, EntryMessage, MessagePart, SchemaId

    with pytest.raises(LedgerValidationError) as raised:
        EntryDraft(
            kind=EntryKind.QUESTION,
            schema_id=SchemaId.QUESTION.value,
            context_id="ctx-1",
            recipient_agent_ids=("a1",),
            message=EntryMessage(parts=(MessagePart(kind="text", text="q"),)),
        )
    assert raised.value.code == "writer_kind_inactive"


def test_message_part_bounds_and_artifact_sha256() -> None:
    from evidence_handoff.ledger.errors import LedgerValidationError
    from evidence_handoff.ledger.models import ArtifactRef, MessagePart

    with pytest.raises(LedgerValidationError) as huge:
        MessagePart(kind="text", text="x" * (64 * 1024 + 1))
    assert huge.value.code == "message_part_too_large"

    with pytest.raises(LedgerValidationError) as huge_data:
        MessagePart(kind="data", data={"blob": "y" * (64 * 1024 + 1)})
    assert huge_data.value.code == "message_part_too_large"

    with pytest.raises(LedgerValidationError) as digest:
        ArtifactRef(name="shot", content_sha256="not-a-digest")
    assert digest.value.code == "malformed_sha256"


def test_entry_draft_rejects_unknown_fields() -> None:
    from evidence_handoff.ledger.errors import LedgerValidationError
    from evidence_handoff.ledger.models import EntryDraft

    with pytest.raises(LedgerValidationError) as raised:
        EntryDraft.from_mapping(
            {
                "kind": "review-ruling",
                "schema_id": "review-ruling.v1",
                "context_id": "ctx-1",
                "recipient_agent_ids": ["reviewer-1"],
                "message": {"parts": [{"kind": "text", "text": "ok"}]},
                "unexpected_client_field": "nope",
            }
        )
    assert raised.value.code == "unknown_field"
