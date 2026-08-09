"""RED tests for review-ruling append/read wiring and narrow audit (Task 7).

Append only after policy + real EntryDraft ingress success. Failures leave no row
and no sequence advance. Audit records are content-free.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from evidence_handoff.ledger.models import (
    AppendResult,
    EntryDraft,
    EntryKind,
    SanitizedDraft,
)


def _enrollment(
    *,
    principal_id: str,
    agent_id: str,
    caller_role: str,
    instance_id: str = "ledger-inst-1",
):
    from evidence_handoff_runtime.auth import Enrollment

    return Enrollment(
        principal_id=principal_id,
        agent_id=agent_id,
        caller_role=caller_role,
        scopes=frozenset({"ledger.write", "ledger.read"}),
        instance_id=instance_id,
    )


def _issue_for(enrollment, *, instance_id: str = "ledger-inst-1") -> str:
    from evidence_handoff_runtime.auth import CredentialIssuer

    issuer = CredentialIssuer(
        signing_key=b"unit-signing-key-32-bytes-xxxxxx",
        issuer="evidence-handoff-runtime",
        audience="evidence-handoff",
        enrollments={(instance_id, enrollment.principal_id): enrollment},
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        default_ttl=timedelta(minutes=5),
    )
    return issuer.issue(instance_id=instance_id, enrollment=enrollment)


def _auth_stack_validator(enrollment):
    from evidence_handoff_runtime.auth import CredentialValidator

    return CredentialValidator(
        signing_key=b"unit-signing-key-32-bytes-xxxxxx",
        expected_issuer="evidence-handoff-runtime",
        expected_audience="evidence-handoff",
        enrollments={(enrollment.instance_id, enrollment.principal_id): enrollment},
        now=lambda: datetime(2026, 8, 8, 12, 0, 30, tzinfo=UTC),
        revoked_token_ids=frozenset(),
        consumed_jti=set(),
    )


def _auth_stack(*, enrollment):
    from evidence_handoff_runtime.sessions import SessionRegistry

    token = _issue_for(enrollment, instance_id=enrollment.instance_id)
    validator = _auth_stack_validator(enrollment)
    principal = validator.validate(
        header=f"Bearer {token}",
        request={
            "ledger_instance_id": enrollment.instance_id,
            "required_scope": "ledger.write",
        },
    )
    sessions = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 30, tzinfo=UTC),
    )
    binding = sessions.create(principal, protocol_version="2025-11-25")
    return principal, binding, sessions, token


def _request_inputs(tmp_path: Path, *, secrets: tuple[str, ...] = ("svc-secret-alpha",)):
    from evidence_handoff.redaction.ingress import RequestRedactionInputs
    from evidence_handoff.redaction.models import RedactionRuntimeInputs
    from optimus_security.sanitization import PathAliasRule
    from optimus_security.sensitive_values import SensitiveValueInventory, SensitiveValueSourceClass

    capture = tmp_path / "cap"
    staging = tmp_path / "stg"
    quarantine = tmp_path / "q"
    forbidden = tmp_path / "forbidden"
    for path in (capture, staging, quarantine, forbidden):
        path.mkdir()
    inventory = SensitiveValueInventory()
    for secret in secrets:
        inventory.add_secret(secret, source_class=SensitiveValueSourceClass.ENVIRONMENT)
    inventory.add_pii("operator@example.test", source_class=SensitiveValueSourceClass.INJECTED_PII)
    return RequestRedactionInputs(
        runtime=RedactionRuntimeInputs(
            sensitive_values=inventory,
            path_aliases=(PathAliasRule(source_root=str(capture), alias="<temp>"),),
            temporary_capture_root=capture,
            staging_root=staging,
            quarantine_root=quarantine,
            forbidden_persistence_roots=(forbidden,),
        )
    )


def _client_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "kind": "review-ruling",
        "schema_id": "review-ruling.v1",
        "context_id": "ctx-ruling-1",
        "recipient_agent_ids": ["implementer-1"],
        "message": {"parts": [{"kind": "text", "text": "reviewer ruling body"}]},
        "idempotency_key": "idem-ruling-1",
    }
    fields.update(overrides)
    return fields


def _counter_snapshot(store: Any) -> tuple[int, str | None]:
    status = store.current_status()
    return int(status.last_committed), status.last_content_sha256


def test_audit_module_records_only_narrow_content_free_fields(tmp_path: Path) -> None:
    from evidence_handoff_runtime.audit import AuditRecorder

    recorder = AuditRecorder(path=tmp_path / "audit.jsonl")
    recorder.record(
        {
            "kind": "review-ruling",
            "schema_id": "review-ruling.v1",
            "digest": "a" * 64,
            "counts": {"exact_secret": 1},
            "principal_id": "principal-reviewer",
            "agent_id": "reviewer-1",
            "sequence": 1,
            "failure_code": None,
        }
    )
    with pytest.raises(ValueError):
        recorder.record({"kind": "review-ruling", "raw_body": "secret-must-not-audit"})
    with pytest.raises(ValueError):
        recorder.record({"kind": "review-ruling", "exception": "traceback"})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "raw_body" not in lines[0]
    assert "secret-must-not-audit" not in lines[0]


def test_reviewer_append_uses_entry_draft_ingress_not_text_adapter(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress
    from evidence_handoff_runtime.policy import attempt_review_ruling_append

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    _principal, binding, sessions, token = _auth_stack(enrollment=enrollment)
    real_ingress = StructuredIngress()
    seen: list[Any] = []
    original = real_ingress.sanitize

    def _spy(draft, inputs):
        seen.append(draft)
        return original(draft, inputs)

    real_ingress.sanitize = _spy  # type: ignore[method-assign]

    appended: list[Any] = []

    class _Store:
        def current_status(self):
            return MagicMock(last_committed=len(appended), last_content_sha256=None)

        def append(self, sanitized, identity, *, idempotency_key: str):
            assert isinstance(sanitized, SanitizedDraft)
            assert identity.authority == "review-ruling"
            result = AppendResult(
                entry_id="entry-1",
                sequence=1,
                ledger_instance_id="ledger-inst-1",
                content_sha256="b" * 64,
            )
            appended.append((sanitized, identity, idempotency_key))
            return result

    result = attempt_review_ruling_append(
        authorization_header=f"Bearer {token}",
        session_id=binding.session_id,
        protocol_version="2025-11-25",
        ledger_instance_id="ledger-inst-1",
        client_fields=_client_fields(),
        validator=_auth_stack_validator(enrollment),
        sessions=sessions,
        ingress=real_ingress,
        store=_Store(),
        request_inputs=_request_inputs(tmp_path),
        known_agent_ids=frozenset({"reviewer-1", "implementer-1"}),
    )
    assert result.entry_id == "entry-1"
    assert result.sequence == 1
    assert result.ledger_instance_id == "ledger-inst-1"
    assert len(result.content_sha256) == 64
    assert len(seen) == 1
    assert isinstance(seen[0], EntryDraft)
    assert seen[0].kind == EntryKind.REVIEW_RULING
    assert len(appended) == 1


def test_ingress_rejection_skips_append_and_leaves_counter(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress
    from evidence_handoff_runtime.policy import PolicyError, attempt_review_ruling_append

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    _principal, binding, sessions, token = _auth_stack(enrollment=enrollment)
    store = MagicMock()
    store.current_status.return_value = MagicMock(last_committed=4, last_content_sha256="abc")
    before = _counter_snapshot(store)
    ingress = MagicMock(spec=StructuredIngress)
    ingress.sanitize.return_value = IngressRejection(
        reason_code="final_scan_hit",
        rule_counts={},
    )

    with pytest.raises(PolicyError) as raised:
        attempt_review_ruling_append(
            authorization_header=f"Bearer {token}",
            session_id=binding.session_id,
            protocol_version="2025-11-25",
            ledger_instance_id="ledger-inst-1",
            client_fields=_client_fields(message={"parts": [{"kind": "text", "text": "x"}]}),
            validator=_auth_stack_validator(enrollment),
            sessions=sessions,
            ingress=ingress,
            store=store,
            request_inputs=_request_inputs(tmp_path),
            known_agent_ids=frozenset({"implementer-1"}),
        )
    assert raised.value.code == "final_scan_hit"
    store.append.assert_not_called()
    assert _counter_snapshot(store) == before


def test_induced_store_failure_leaves_counter_unchanged(tmp_path: Path) -> None:
    from evidence_handoff.ledger.errors import LedgerStoreError
    from evidence_handoff.redaction.ingress import StructuredIngress
    from evidence_handoff_runtime.policy import PolicyError, attempt_review_ruling_append

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    _principal, binding, sessions, token = _auth_stack(enrollment=enrollment)

    class _Store:
        def __init__(self) -> None:
            self.committed = 0
            self.head = None

        def current_status(self):
            return MagicMock(last_committed=self.committed, last_content_sha256=self.head)

        def append(self, sanitized, identity, *, idempotency_key: str):
            raise LedgerStoreError("induced_rollback")

    store = _Store()
    before = _counter_snapshot(store)
    with pytest.raises((PolicyError, LedgerStoreError)):
        attempt_review_ruling_append(
            authorization_header=f"Bearer {token}",
            session_id=binding.session_id,
            protocol_version="2025-11-25",
            ledger_instance_id="ledger-inst-1",
            client_fields=_client_fields(idempotency_key="idem-rollback"),
            validator=_auth_stack_validator(enrollment),
            sessions=sessions,
            ingress=StructuredIngress(),
            store=store,
            request_inputs=_request_inputs(tmp_path),
            known_agent_ids=frozenset({"implementer-1"}),
        )
    assert _counter_snapshot(store) == before


def test_unknown_recipient_rejected_before_ingress(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress
    from evidence_handoff_runtime.policy import PolicyError, attempt_review_ruling_append

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    _principal, binding, sessions, token = _auth_stack(enrollment=enrollment)
    ingress = MagicMock(spec=StructuredIngress)
    store = MagicMock()
    store.current_status.return_value = MagicMock(last_committed=0, last_content_sha256=None)
    before = _counter_snapshot(store)

    with pytest.raises(PolicyError) as raised:
        attempt_review_ruling_append(
            authorization_header=f"Bearer {token}",
            session_id=binding.session_id,
            protocol_version="2025-11-25",
            ledger_instance_id="ledger-inst-1",
            client_fields=_client_fields(recipient_agent_ids=["unknown-agent"]),
            validator=_auth_stack_validator(enrollment),
            sessions=sessions,
            ingress=ingress,
            store=store,
            request_inputs=_request_inputs(tmp_path),
            known_agent_ids=frozenset({"reviewer-1", "implementer-1"}),
        )
    assert raised.value.code == "unknown_recipient"
    ingress.sanitize.assert_not_called()
    store.append.assert_not_called()
    assert _counter_snapshot(store) == before


def test_non_null_attestation_rejected_before_ingress(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress
    from evidence_handoff_runtime.policy import PolicyError, attempt_review_ruling_append

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    _principal, binding, sessions, token = _auth_stack(enrollment=enrollment)
    ingress = MagicMock(spec=StructuredIngress)
    store = MagicMock()
    store.current_status.return_value = MagicMock(last_committed=2, last_content_sha256="x")
    before = _counter_snapshot(store)

    with pytest.raises(PolicyError) as raised:
        attempt_review_ruling_append(
            authorization_header=f"Bearer {token}",
            session_id=binding.session_id,
            protocol_version="2025-11-25",
            ledger_instance_id="ledger-inst-1",
            client_fields=_client_fields(attestation={"claim": "nope"}),
            validator=_auth_stack_validator(enrollment),
            sessions=sessions,
            ingress=ingress,
            store=store,
            request_inputs=_request_inputs(tmp_path),
            known_agent_ids=frozenset({"implementer-1"}),
        )
    assert raised.value.code == "closed_schema_field_rejected"
    ingress.sanitize.assert_not_called()
    assert _counter_snapshot(store) == before


def test_review_ruling_read_returns_safe_fields_only() -> None:
    from evidence_handoff_runtime.policy import attempt_review_ruling_read

    store = MagicMock()
    store.read_entry.return_value = AppendResult(
        entry_id="entry-read-1",
        sequence=7,
        ledger_instance_id="ledger-inst-1",
        content_sha256="c" * 64,
    )
    # Or envelope-shaped read — implementation may return a mapping.
    store.get_entry_by_sequence.return_value = {
        "entry_id": "entry-read-1",
        "sequence": 7,
        "ledger_instance_id": "ledger-inst-1",
        "content_sha256": "c" * 64,
        "message": {"parts": [{"kind": "text", "text": "should not return raw"}]},
    }

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    _principal, binding, sessions, token = _auth_stack(enrollment=enrollment)
    result = attempt_review_ruling_read(
        authorization_header=f"Bearer {token}",
        session_id=binding.session_id,
        protocol_version="2025-11-25",
        ledger_instance_id="ledger-inst-1",
        sequence=7,
        validator=_auth_stack_validator(enrollment),
        sessions=sessions,
        store=store,
    )
    assert set(result) <= {
        "entry_id",
        "sequence",
        "ledger_instance_id",
        "content_sha256",
    }
    assert result["entry_id"] == "entry-read-1"
    assert result["sequence"] == 7
    assert "message" not in result
    assert "should not return raw" not in repr(result)


def test_client_authority_rejection_unchanged_from_policy(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress
    from evidence_handoff_runtime.policy import PolicyError, attempt_review_ruling_append

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    _principal, binding, sessions, token = _auth_stack(enrollment=enrollment)
    ingress = MagicMock(spec=StructuredIngress)
    store = MagicMock()
    store.current_status.return_value = MagicMock(last_committed=1, last_content_sha256="h")
    before = _counter_snapshot(store)
    with pytest.raises(PolicyError) as raised:
        attempt_review_ruling_append(
            authorization_header=f"Bearer {token}",
            session_id=binding.session_id,
            protocol_version="2025-11-25",
            ledger_instance_id="ledger-inst-1",
            client_fields=_client_fields(authority="review-ruling"),
            validator=_auth_stack_validator(enrollment),
            sessions=sessions,
            ingress=ingress,
            store=store,
            request_inputs=_request_inputs(tmp_path),
            known_agent_ids=frozenset({"implementer-1"}),
        )
    assert raised.value.code == "closed_schema_field_rejected"
    ingress.sanitize.assert_not_called()
    assert _counter_snapshot(store) == before
