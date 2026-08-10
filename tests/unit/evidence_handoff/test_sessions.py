"""RED tests for MCP session binding (Task 6).

Session IDs are CSPRNG (`secrets`), never credentials, and bind principal + protocol.
"""

from __future__ import annotations

import inspect
import random
from datetime import UTC, datetime, timedelta

import pytest


def _principal(*, principal_id: str = "principal-reviewer", agent_id: str = "reviewer-1"):
    from evidence_handoff_runtime.auth import AuthenticatedPrincipal

    return AuthenticatedPrincipal(
        principal_id=principal_id,
        agent_id=agent_id,
        caller_role="reviewer",
        token_id="tok-1",
        scope=frozenset({"ledger.write", "ledger.read"}),
    )


def test_session_registry_create_uses_secrets_module() -> None:
    """Watch item: SessionRegistry IDs from secrets (CSPRNG), never random."""
    import evidence_handoff_runtime.sessions as sessions_mod

    source = inspect.getsource(sessions_mod)
    assert "secrets" in source
    assert "token_urlsafe" in source or "token_hex" in source
    create_src = inspect.getsource(sessions_mod.SessionRegistry.create)
    assert "random." not in create_src
    assert "Random(" not in create_src


def test_session_create_validate_and_expire() -> None:
    from evidence_handoff_runtime.sessions import SessionBinding, SessionError, SessionRegistry

    clock = {"t": datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)}
    registry = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: clock["t"],
    )
    principal = _principal()
    binding = registry.create(principal, protocol_version="2025-11-25")
    assert isinstance(binding, SessionBinding)
    assert binding.session_id
    assert binding.principal_id == principal.principal_id
    assert binding.protocol_version == "2025-11-25"
    rng = random.Random(0)
    assert binding.session_id != rng.randbytes(32).hex()

    registry.validate(binding.session_id, principal)

    registry.expire(binding.session_id)
    with pytest.raises(SessionError) as raised:
        registry.validate(binding.session_id, principal)
    assert raised.value.code == "session_expired_or_unknown"


def test_session_rejects_principal_mismatch() -> None:
    from evidence_handoff_runtime.sessions import SessionError, SessionRegistry

    registry = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
    )
    binding = registry.create(_principal(), protocol_version="2025-11-25")
    other = _principal(principal_id="principal-other", agent_id="other-1")
    with pytest.raises(SessionError) as raised:
        registry.validate(binding.session_id, other)
    assert raised.value.code == "session_principal_mismatch"


def test_session_rejects_protocol_mismatch() -> None:
    from evidence_handoff_runtime.sessions import SessionError, SessionRegistry

    registry = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
    )
    principal = _principal()
    binding = registry.create(principal, protocol_version="2025-11-25")
    with pytest.raises(SessionError) as raised:
        registry.validate(
            binding.session_id,
            principal,
            protocol_version="1999-01-01",
        )
    assert raised.value.code == "session_protocol_mismatch"


def test_session_ttl_expiry() -> None:
    from evidence_handoff_runtime.sessions import SessionError, SessionRegistry

    clock = {"t": datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)}
    registry = SessionRegistry(
        ttl=timedelta(minutes=5),
        now=lambda: clock["t"],
    )
    principal = _principal()
    binding = registry.create(principal, protocol_version="2025-11-25")
    clock["t"] = datetime(2026, 8, 8, 12, 6, 0, tzinfo=UTC)
    with pytest.raises(SessionError) as raised:
        registry.validate(binding.session_id, principal)
    assert raised.value.code == "session_expired_or_unknown"


def test_session_id_never_accepted_as_auth_credential() -> None:
    from evidence_handoff_runtime.auth import AuthError, CredentialValidator
    from evidence_handoff_runtime.sessions import SessionRegistry

    registry = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
    )
    binding = registry.create(_principal(), protocol_version="2025-11-25")
    validator = CredentialValidator(
        signing_key=b"unit-signing-key-32-bytes-xxxxxx",
        expected_issuer="evidence-handoff-runtime",
        expected_audience="evidence-handoff",
        enrollments={},
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        revoked_token_ids=frozenset(),
        consumed_jti=set(),
    )
    with pytest.raises(AuthError) as raised:
        validator.validate(
            header=f"Bearer {binding.session_id}",
            request={"ledger_instance_id": "ledger-inst-1"},
        )
    assert raised.value.code == "session_not_credential"
    assert binding.session_id not in str(raised.value)


def test_resolve_or_adopt_refuses_cross_principal_hijack() -> None:
    """Service wiring must not rebind Principal A's session to Principal B."""
    from datetime import UTC, datetime, timedelta

    from evidence_handoff_runtime.auth import AuthenticatedPrincipal
    from evidence_handoff_runtime.sessions import SessionError, SessionRegistry

    registry = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
    )
    principal_a = AuthenticatedPrincipal(
        principal_id="principal-a",
        agent_id="reviewer-1",
        caller_role="reviewer",
        token_id="tok-a",
        scope=frozenset({"ledger.write"}),
    )
    principal_b = AuthenticatedPrincipal(
        principal_id="principal-b",
        agent_id="implementer-1",
        caller_role="implementer",
        token_id="tok-b",
        scope=frozenset({"ledger.write"}),
    )
    binding = registry.create(principal_a, protocol_version="2025-11-25")

    with pytest.raises(SessionError) as raised:
        registry.resolve_or_adopt(
            binding.session_id,
            principal_b,
            protocol_version="2025-11-25",
        )
    assert raised.value.code == "session_principal_mismatch"
    # Binding must remain owned by A.
    registry.validate(binding.session_id, principal_a, protocol_version="2025-11-25")
    with pytest.raises(SessionError):
        registry.attach(
            binding.session_id,
            principal_b,
            protocol_version="2025-11-25",
        )


def test_unknown_client_presented_session_is_not_auto_attached() -> None:
    """Request-path adoption of unknown ids is forbidden (hijack vector)."""
    from datetime import UTC, datetime, timedelta

    from evidence_handoff_runtime.auth import AuthenticatedPrincipal
    from evidence_handoff_runtime.sessions import SessionError, SessionRegistry

    registry = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
    )
    principal = AuthenticatedPrincipal(
        principal_id="principal-b",
        agent_id="implementer-1",
        caller_role="implementer",
        token_id="tok-b",
        scope=frozenset({"ledger.write"}),
    )
    with pytest.raises(SessionError) as raised:
        registry.validate(
            "mcp-transport-session-id-unknownxxxx",
            principal,
            protocol_version="2025-11-25",
        )
    assert raised.value.code == "session_expired_or_unknown"
    # attach remains available for response-path server-emitted ids only.
    registry.attach(
        "mcp-transport-session-id-unknownxxxx",
        principal,
        protocol_version="2025-11-25",
    )


def test_resolve_or_adopt_attaches_unknown_transport_session() -> None:
    from datetime import UTC, datetime, timedelta

    from evidence_handoff_runtime.auth import AuthenticatedPrincipal
    from evidence_handoff_runtime.sessions import SessionRegistry

    registry = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
    )
    principal = AuthenticatedPrincipal(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
        token_id="tok-1",
        scope=frozenset({"ledger.write"}),
    )
    transport_id = "mcp-transport-session-id-xxxxxxxx"
    resolved = registry.resolve_or_adopt(
        transport_id,
        principal,
        protocol_version="2025-11-25",
    )
    assert resolved == transport_id
    registry.validate(transport_id, principal, protocol_version="2025-11-25")


def test_session_binding_repr_has_no_token_fields() -> None:
    from evidence_handoff_runtime.sessions import SessionRegistry

    registry = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
    )
    binding = registry.create(_principal(), protocol_version="2025-11-25")
    rendered = repr(binding).lower()
    assert "bearer" not in rendered
    assert "signing_key" not in rendered


def test_session_accepts_admitted_protocol_after_headerless_initialize_default() -> None:
    """Codex: omit MCP-Protocol-Version on initialize; follow up with negotiated 2025-06-18.

    Headerless initialize resolves to the service default (2025-11-25) for session create.
    Spec-correct clients then send the body-negotiated version on later requests. Option A:
    any version in the admitted set is accepted — not an exact match to the create-time bind.
    """
    from evidence_handoff_runtime.sessions import SessionRegistry

    admitted = frozenset({"2025-11-25", "2025-06-18", "2025-03-26"})
    registry = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        allowed_protocol_versions=admitted,
    )
    principal = _principal()
    binding = registry.create(principal, protocol_version="2025-11-25")
    registry.validate(
        binding.session_id,
        principal,
        protocol_version="2025-06-18",
    )


def test_session_rejects_non_admitted_protocol_on_live_session() -> None:
    """Inverse of Option A: versions outside the admitted set still mismatch."""
    from evidence_handoff_runtime.sessions import SessionError, SessionRegistry

    admitted = frozenset({"2025-11-25", "2025-06-18", "2025-03-26"})
    registry = SessionRegistry(
        ttl=timedelta(minutes=10),
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        allowed_protocol_versions=admitted,
    )
    principal = _principal()
    binding = registry.create(principal, protocol_version="2025-11-25")
    with pytest.raises(SessionError) as raised:
        registry.validate(
            binding.session_id,
            principal,
            protocol_version="2024-11-05",
        )
    assert raised.value.code == "session_protocol_mismatch"
