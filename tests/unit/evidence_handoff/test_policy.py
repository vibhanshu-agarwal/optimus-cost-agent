"""RED tests for principal mapping and role policy (Task 6).

Reviewer principals alone append review-ruling. Implementer and closed-schema
rejections must not invoke StructuredIngress and must leave counter/head unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


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

    instance_id = enrollment.instance_id
    token = _issue_for(enrollment, instance_id=instance_id)
    validator = _auth_stack_validator(enrollment)
    principal = validator.validate(
        header=f"Bearer {token}",
        request={"ledger_instance_id": instance_id, "required_scope": "ledger.write"},
    )
    sessions = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 30, tzinfo=UTC),
    )
    binding = sessions.create(principal, protocol_version="2025-11-25")
    return principal, binding, sessions, token


def _counter_snapshot(store: Any) -> tuple[int, str | None]:
    status = store.current_status()
    return int(status.last_committed), status.last_content_sha256


def test_policy_derives_identity_never_client_supplied() -> None:
    from evidence_handoff_runtime.policy import PolicyDecision, PolicyError

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    principal, _binding, _sessions, _token = _auth_stack(enrollment=enrollment)
    decision = PolicyDecision.for_append(
        principal=principal,
        kind="review-ruling",
        client_fields={},
    )
    assert decision.allowed is True
    assert decision.identity.principal_id == "principal-reviewer"
    assert decision.identity.agent_id == "reviewer-1"
    assert decision.identity.caller_role == "reviewer"
    assert decision.identity.authority == "review-ruling"

    with pytest.raises(PolicyError) as raised:
        PolicyDecision.for_append(
            principal=principal,
            kind="review-ruling",
            client_fields={"authority": "review-ruling"},
        )
    assert raised.value.code == "closed_schema_field_rejected"


@pytest.mark.parametrize(
    "field",
    ["authority", "caller_role", "agent_id", "principal_id"],
)
def test_policy_rejects_client_identity_fields(field: str) -> None:
    from evidence_handoff_runtime.policy import PolicyDecision, PolicyError

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    principal, _, _, _ = _auth_stack(enrollment=enrollment)
    with pytest.raises(PolicyError) as raised:
        PolicyDecision.for_append(
            principal=principal,
            kind="review-ruling",
            client_fields={field: "attacker-supplied"},
        )
    assert raised.value.code == "closed_schema_field_rejected"


def test_policy_rejects_non_null_attestation() -> None:
    from evidence_handoff_runtime.policy import PolicyDecision, PolicyError

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    principal, _, _, _ = _auth_stack(enrollment=enrollment)
    with pytest.raises(PolicyError) as raised:
        PolicyDecision.for_append(
            principal=principal,
            kind="review-ruling",
            client_fields={"attestation": {"claim": "x"}},
        )
    assert raised.value.code == "closed_schema_field_rejected"


def test_implementer_rejected_before_ingress_and_counter_unchanged() -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress
    from evidence_handoff_runtime.policy import PolicyError, attempt_review_ruling_append

    enrollment = _enrollment(
        principal_id="principal-implementer",
        agent_id="implementer-1",
        caller_role="implementer",
    )
    _principal, binding, sessions, token = _auth_stack(enrollment=enrollment)

    store = MagicMock()
    store.current_status.return_value = MagicMock(last_committed=0, last_content_sha256=None)
    ingress = MagicMock(spec=StructuredIngress)
    before = _counter_snapshot(store)

    with pytest.raises(PolicyError) as raised:
        attempt_review_ruling_append(
            authorization_header=f"Bearer {token}",
            session_id=binding.session_id,
            protocol_version="2025-11-25",
            ledger_instance_id="ledger-inst-1",
            client_fields={
                "kind": "review-ruling",
                "schema_id": "review-ruling.v1",
                "context_id": "ctx-1",
                "recipient_agent_ids": ["implementer-1"],
                "message_text": "should never reach ingress",
            },
            validator=_auth_stack_validator(enrollment),
            sessions=sessions,
            ingress=ingress,
            store=store,
            request_inputs=MagicMock(),
            known_agent_ids=frozenset({"implementer-1"}),
        )
    assert raised.value.code == "role_not_permitted"
    ingress.sanitize.assert_not_called()
    store.append.assert_not_called()
    assert _counter_snapshot(store) == before


def test_closed_schema_rejection_skips_ingress() -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress
    from evidence_handoff_runtime.policy import PolicyError, attempt_review_ruling_append

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    _principal, binding, sessions, token = _auth_stack(enrollment=enrollment)
    store = MagicMock()
    store.current_status.return_value = MagicMock(last_committed=3, last_content_sha256="abc")
    ingress = MagicMock(spec=StructuredIngress)
    before = _counter_snapshot(store)

    with pytest.raises(PolicyError) as raised:
        attempt_review_ruling_append(
            authorization_header=f"Bearer {token}",
            session_id=binding.session_id,
            protocol_version="2025-11-25",
            ledger_instance_id="ledger-inst-1",
            client_fields={
                "kind": "review-ruling",
                "schema_id": "review-ruling.v1",
                "context_id": "ctx-1",
                "recipient_agent_ids": ["implementer-1"],
                "message_text": "body",
                "agent_id": "spoofed",
            },
            validator=_auth_stack_validator(enrollment),
            sessions=sessions,
            ingress=ingress,
            store=store,
            request_inputs=MagicMock(),
            known_agent_ids=frozenset({"implementer-1"}),
        )
    assert raised.value.code == "closed_schema_field_rejected"
    ingress.sanitize.assert_not_called()
    store.append.assert_not_called()
    assert _counter_snapshot(store) == before


def test_invalid_origin_before_parse_skips_ingress() -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress
    from evidence_handoff_runtime.transport import evaluate_http_preamble

    decision = evaluate_http_preamble(
        bind_host="127.0.0.1",
        bind_port=8765,
        allowed_origins=frozenset({"http://127.0.0.1:8765"}),
        headers={
            "host": "127.0.0.1:8765",
            "origin": "http://evil.example",
            "authorization": "Bearer irrelevant",
        },
        content_length=10,
        max_body_bytes=65536,
        auth_present=True,
    )
    assert decision.allowed is False
    assert decision.code == "origin_rejected"
    assert decision.reached_mcp_parse is False

    ingress = MagicMock(spec=StructuredIngress)
    if decision.allowed:
        raise AssertionError("origin must block before MCP parse")
    ingress.sanitize.assert_not_called()


def test_reviewer_success_invokes_real_ingress_then_store_append(tmp_path: Path) -> None:
    """Boundary ruling: reviewer success reaches real ingress + store.append (no fake seam)."""
    from evidence_handoff.ledger.models import EntryDraft, EntryKind, SanitizedDraft
    from evidence_handoff.redaction.ingress import (
        IngressSanitizedText,
        RequestRedactionInputs,
        StructuredIngress,
    )
    from evidence_handoff.redaction.models import RedactionRuntimeInputs
    from evidence_handoff_runtime.policy import attempt_review_ruling_append
    from optimus_security.sanitization import PathAliasRule
    from optimus_security.sensitive_values import SensitiveValueInventory, SensitiveValueSourceClass

    enrollment = _enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
    )
    _principal, binding, sessions, token = _auth_stack(enrollment=enrollment)

    capture = tmp_path / "cap"
    staging = tmp_path / "stg"
    quarantine = tmp_path / "q"
    forbidden = tmp_path / "forbidden"
    for path in (capture, staging, quarantine, forbidden):
        path.mkdir()

    inventory = SensitiveValueInventory()
    inventory.add_secret("svc-secret-alpha", source_class=SensitiveValueSourceClass.ENVIRONMENT)
    inventory.add_pii("operator@example.test", source_class=SensitiveValueSourceClass.INJECTED_PII)
    runtime = RedactionRuntimeInputs(
        sensitive_values=inventory,
        path_aliases=(PathAliasRule(source_root=str(capture), alias="<temp>"),),
        temporary_capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine,
        forbidden_persistence_roots=(forbidden,),
    )
    request_inputs = RequestRedactionInputs(runtime=runtime)

    real_ingress = StructuredIngress()
    sanitize_calls: list[Any] = []
    original_sanitize = real_ingress.sanitize

    def _spy(draft, inputs):
        sanitize_calls.append(draft)
        return original_sanitize(draft, inputs)

    real_ingress.sanitize = _spy  # type: ignore[method-assign]

    appended: list[Any] = []

    class _Store:
        def current_status(self):
            return MagicMock(last_committed=len(appended), last_content_sha256=None)

        def append(self, sanitized, identity, *, idempotency_key: str):
            assert isinstance(sanitized, SanitizedDraft)
            assert sanitized.kind == EntryKind.REVIEW_RULING
            assert identity.caller_role == "reviewer"
            assert identity.authority == "review-ruling"
            assert identity.principal_id == "principal-reviewer"
            result = MagicMock(
                sequence=len(appended) + 1,
                content_sha256="deadbeef",
                idempotent_replay=False,
            )
            appended.append((sanitized, identity, idempotency_key))
            return result

    result = attempt_review_ruling_append(
        authorization_header=f"Bearer {token}",
        session_id=binding.session_id,
        protocol_version="2025-11-25",
        ledger_instance_id="ledger-inst-1",
        client_fields={
            "kind": "review-ruling",
            "schema_id": "review-ruling.v1",
            "context_id": "ctx-policy-1",
            "recipient_agent_ids": ["implementer-1"],
            "message_text": "reviewer ruling body",
            "idempotency_key": "idem-policy-1",
        },
        validator=_auth_stack_validator(enrollment),
        sessions=sessions,
        ingress=real_ingress,
        store=_Store(),
        request_inputs=request_inputs,
        known_agent_ids=frozenset({"implementer-1", "reviewer-1"}),
    )
    assert result.sequence == 1
    assert len(sanitize_calls) == 1
    assert isinstance(sanitize_calls[0], EntryDraft)
    assert sanitize_calls[0].kind == EntryKind.REVIEW_RULING
    assert len(appended) == 1
    assert not isinstance(appended[0][0], IngressSanitizedText)
