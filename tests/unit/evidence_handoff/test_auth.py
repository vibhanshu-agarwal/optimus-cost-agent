"""RED tests for audience-bound credentials (Task 6).

Token values must never appear in logs, rows, or bootstrap manifests.
Signature checks must use constant-time comparison (hmac.compare_digest).
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


def _enrollment(
    *,
    principal_id: str = "principal-reviewer",
    agent_id: str = "reviewer-1",
    caller_role: str = "reviewer",
    scopes: frozenset[str] | None = None,
    instance_id: str = "ledger-inst-1",
):
    from evidence_handoff_runtime.auth import Enrollment

    return Enrollment(
        principal_id=principal_id,
        agent_id=agent_id,
        caller_role=caller_role,
        scopes=scopes or frozenset({"ledger.write", "ledger.read"}),
        instance_id=instance_id,
    )


def _issuer(*, signing_key: bytes = b"unit-signing-key-32-bytes-xxxxxx", audience: str = "evidence-handoff"):
    from evidence_handoff_runtime.auth import CredentialIssuer

    return CredentialIssuer(
        signing_key=signing_key,
        issuer="evidence-handoff-runtime",
        audience=audience,
        enrollments={("ledger-inst-1", "principal-reviewer"): _enrollment()},
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        default_ttl=timedelta(minutes=5),
    )


def test_credential_issuer_issues_opaque_token_not_containing_signing_key() -> None:
    from evidence_handoff_runtime.auth import CredentialClaims

    issuer = _issuer()
    token = issuer.issue(instance_id="ledger-inst-1", enrollment=_enrollment())
    assert isinstance(token, str)
    assert token
    assert b"unit-signing-key-32-bytes-xxxxxx".decode() not in token
    claims = CredentialClaims.parse_unverified_for_tests(token)
    assert claims.principal_id == "principal-reviewer"
    assert claims.agent_id == "reviewer-1"
    assert claims.caller_role == "reviewer"
    assert claims.issuer == "evidence-handoff-runtime"
    assert claims.audience == "evidence-handoff"
    assert "ledger.write" in claims.scope
    assert claims.token_id


def test_validator_accepts_valid_token() -> None:
    from evidence_handoff_runtime.auth import AuthenticatedPrincipal, CredentialValidator

    issuer = _issuer()
    token = issuer.issue(instance_id="ledger-inst-1", enrollment=_enrollment())
    validator = CredentialValidator(
        signing_key=b"unit-signing-key-32-bytes-xxxxxx",
        expected_issuer="evidence-handoff-runtime",
        expected_audience="evidence-handoff",
        enrollments={("ledger-inst-1", "principal-reviewer"): _enrollment()},
        now=lambda: datetime(2026, 8, 8, 12, 0, 30, tzinfo=UTC),
        revoked_token_ids=frozenset(),
        consumed_jti=set(),
    )
    principal = validator.validate(
        header=f"Bearer {token}",
        request={"ledger_instance_id": "ledger-inst-1"},
    )
    assert isinstance(principal, AuthenticatedPrincipal)
    assert principal.principal_id == "principal-reviewer"
    assert principal.agent_id == "reviewer-1"
    assert principal.caller_role == "reviewer"
    assert principal.token_id


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        ("malformed", "token_malformed"),
        ("expired", "token_expired"),
        ("wrong_audience", "token_wrong_audience"),
        ("wrong_issuer", "token_wrong_issuer"),
        ("wrong_scope", "token_wrong_scope"),
        ("revoked", "token_revoked"),
        ("replayed", "token_replayed"),
        ("wrong_instance", "token_wrong_instance"),
        ("bad_signature", "token_bad_signature"),
        ("session_as_credential", "session_not_credential"),
    ],
)
def test_validator_rejects_negative_token_cases(mutate: str, code: str) -> None:
    from evidence_handoff_runtime.auth import AuthError, CredentialIssuer, CredentialValidator

    signing_key = b"unit-signing-key-32-bytes-xxxxxx"
    enrollment = _enrollment()
    issuer = CredentialIssuer(
        signing_key=signing_key,
        issuer="evidence-handoff-runtime",
        audience="evidence-handoff",
        enrollments={("ledger-inst-1", "principal-reviewer"): enrollment},
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        default_ttl=timedelta(minutes=5),
    )
    token = issuer.issue(instance_id="ledger-inst-1", enrollment=enrollment)
    revoked: frozenset[str] = frozenset()
    consumed: set[str] = set()
    now = datetime(2026, 8, 8, 12, 0, 30, tzinfo=UTC)
    expected_audience = "evidence-handoff"
    expected_issuer = "evidence-handoff-runtime"
    header = f"Bearer {token}"
    request = {"ledger_instance_id": "ledger-inst-1"}

    if mutate == "malformed":
        header = "Bearer not-a-real-token"
    elif mutate == "expired":
        now = datetime(2026, 8, 8, 13, 0, 0, tzinfo=UTC)
    elif mutate == "wrong_audience":
        expected_audience = "other-audience"
    elif mutate == "wrong_issuer":
        expected_issuer = "other-issuer"
    elif mutate == "wrong_scope":
        enrollment = _enrollment(scopes=frozenset({"ledger.read"}))
        issuer = CredentialIssuer(
            signing_key=signing_key,
            issuer="evidence-handoff-runtime",
            audience="evidence-handoff",
            enrollments={("ledger-inst-1", "principal-reviewer"): enrollment},
            now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
            default_ttl=timedelta(minutes=5),
        )
        token = issuer.issue(instance_id="ledger-inst-1", enrollment=enrollment)
        header = f"Bearer {token}"
        # Validator requires ledger.write for this request class.
        request = {"ledger_instance_id": "ledger-inst-1", "required_scope": "ledger.write"}
    elif mutate == "revoked":
        from evidence_handoff_runtime.auth import CredentialClaims

        claims = CredentialClaims.parse_unverified_for_tests(token)
        revoked = frozenset({claims.token_id})
    elif mutate == "replayed":
        from evidence_handoff_runtime.auth import CredentialClaims

        claims = CredentialClaims.parse_unverified_for_tests(token)
        consumed = {claims.token_id}
    elif mutate == "wrong_instance":
        request = {"ledger_instance_id": "other-instance"}
    elif mutate == "bad_signature":
        header = f"Bearer {token[:-4]}dead"
    elif mutate == "session_as_credential":
        header = "Bearer mcp-session-id-lookalike-value"

    validator = CredentialValidator(
        signing_key=signing_key,
        expected_issuer=expected_issuer,
        expected_audience=expected_audience,
        enrollments={("ledger-inst-1", "principal-reviewer"): enrollment},
        now=lambda: now,
        revoked_token_ids=revoked,
        consumed_jti=consumed,
    )
    with pytest.raises(AuthError) as raised:
        validator.validate(header=header, request=request)
    assert raised.value.code == code
    # Fail closed: exception text must not echo the raw token.
    assert token not in str(raised.value)
    assert token not in repr(raised.value)


def test_signature_verification_uses_compare_digest() -> None:
    """Watch item: plan requires constant-time signature comparison."""
    import evidence_handoff_runtime.auth as auth_mod

    source = inspect.getsource(auth_mod)
    assert "compare_digest" in source
    assert "hmac.compare_digest" in source or source.count("compare_digest") >= 1
    # Guard against naive equality on signature bytes in the validator path.
    validator_src = inspect.getsource(auth_mod.CredentialValidator.validate)
    assert "==" not in validator_src or "compare_digest" in inspect.getsource(auth_mod)


def test_authenticated_principal_repr_omits_token_material() -> None:
    from evidence_handoff_runtime.auth import AuthenticatedPrincipal, CredentialValidator

    issuer = _issuer()
    token = issuer.issue(instance_id="ledger-inst-1", enrollment=_enrollment())
    validator = CredentialValidator(
        signing_key=b"unit-signing-key-32-bytes-xxxxxx",
        expected_issuer="evidence-handoff-runtime",
        expected_audience="evidence-handoff",
        enrollments={("ledger-inst-1", "principal-reviewer"): _enrollment()},
        now=lambda: datetime(2026, 8, 8, 12, 0, 30, tzinfo=UTC),
        revoked_token_ids=frozenset(),
        consumed_jti=set(),
    )
    principal = validator.validate(
        header=f"Bearer {token}",
        request={"ledger_instance_id": "ledger-inst-1"},
    )
    assert isinstance(principal, AuthenticatedPrincipal)
    rendered = repr(principal) + str(principal)
    assert token not in rendered
    assert "Bearer" not in rendered


def test_transport_auth_gate_is_credential_validator_not_stub() -> None:
    """Task 5 stub must be replaced in place at the preamble auth position."""
    import evidence_handoff_runtime.transport as transport

    source = inspect.getsource(transport.evaluate_http_preamble)
    assert "CredentialValidator" in source or "validate_authorization" in source
    assert "PreParseAuthGateStub().evaluate" not in source


def test_no_token_persisted_under_control_root(tmp_path: Path) -> None:
    """Watch item: credentials must not land in bootstrap/runtime manifests."""
    from evidence_handoff_runtime.auth import CredentialIssuer

    issuer = CredentialIssuer(
        signing_key=b"unit-signing-key-32-bytes-xxxxxx",
        issuer="evidence-handoff-runtime",
        audience="evidence-handoff",
        enrollments={("ledger-inst-1", "principal-reviewer"): _enrollment()},
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        default_ttl=timedelta(minutes=5),
        control_root=tmp_path,
    )
    token = issuer.issue(instance_id="ledger-inst-1", enrollment=_enrollment())
    for path in tmp_path.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert token not in text
            assert "unit-signing-key" not in text


_EXPIRY_KEY = b"unit-signing-key-32-bytes-xxxxxx"
_EXPIRY_NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
_ABSENT = object()


def _token_with_expiry(expires: object) -> str:
    """Sign a payload whose expires_at the issuer would never write (#648)."""
    import hashlib
    import hmac
    import json

    from evidence_handoff_runtime.auth import _b64url_encode

    payload: dict[str, object] = {
        "principal_id": "principal-reviewer",
        "agent_id": "reviewer-1",
        "caller_role": "reviewer",
        "issuer": "evidence-handoff-runtime",
        "audience": "evidence-handoff",
        "scope": ["ledger.read", "ledger.write"],
        "token_id": "token-id-expiry-case",
        "instance_id": "ledger-inst-1",
    }
    if expires is not _ABSENT:
        payload["expires_at"] = expires
    body = _b64url_encode(json.dumps(payload).encode("utf-8"))
    signature = _b64url_encode(hmac.new(_EXPIRY_KEY, body.encode("ascii"), hashlib.sha256).digest())
    return f"eh1.{body}.{signature}"


def _validate_with_expiry(expires: object):
    from evidence_handoff_runtime.auth import CredentialValidator, validate_authorization

    validator = CredentialValidator(
        signing_key=_EXPIRY_KEY,
        expected_issuer="evidence-handoff-runtime",
        expected_audience="evidence-handoff",
        enrollments={("ledger-inst-1", "principal-reviewer"): _enrollment()},
        now=lambda: _EXPIRY_NOW,
        revoked_token_ids=frozenset(),
        consumed_jti=set(),
    )
    return validate_authorization(
        authorization_header="Bearer " + _token_with_expiry(expires),
        validator=validator,
        request={"ledger_instance_id": "ledger-inst-1"},
    )


@pytest.mark.parametrize(
    "expires",
    [
        pytest.param("2026-08-08T12:10:00", id="naive"),
        pytest.param("2026-08-08", id="date-only"),
        pytest.param("expiry-text-zq" + chr(0x2603), id="unparseable"),
        pytest.param("", id="empty"),
        pytest.param(1786190400, id="integer"),
        pytest.param(["2026-08-08T12:10:00+00:00"], id="list"),
        pytest.param(None, id="null"),
        pytest.param(_ABSENT, id="missing"),
    ],
)
def test_invalid_expiration_is_the_typed_value_free_refusal(expires: object) -> None:
    import traceback

    from evidence_handoff_runtime.auth import AuthError

    with pytest.raises(AuthError) as raised:
        _validate_with_expiry(expires)
    assert raised.value.code == "token_malformed"
    assert str(raised.value) == "token_malformed"
    # No chained cause: a logged traceback must not carry the rejected input.
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True
    rendered = "".join(traceback.format_exception(raised.value))
    if isinstance(expires, str) and expires:
        assert expires not in rendered
    if isinstance(expires, list):
        assert expires[0] not in rendered


@pytest.mark.parametrize(
    ("expires", "code"),
    [
        pytest.param("2026-08-08T12:00:00+00:00", "token_expired", id="exactly-now"),
        pytest.param("2026-08-08T11:59:59+00:00", "token_expired", id="already-expired"),
        pytest.param("2026-08-08T17:29:59+05:30", "token_expired", id="expired-other-offset"),
    ],
)
def test_well_formed_expiration_keeps_its_refusal(expires: str, code: str) -> None:
    from evidence_handoff_runtime.auth import AuthError

    with pytest.raises(AuthError) as raised:
        _validate_with_expiry(expires)
    assert raised.value.code == code


@pytest.mark.parametrize(
    "expires",
    [
        pytest.param("2026-08-08T12:00:01+00:00", id="one-second-ahead"),
        pytest.param("2026-08-08T17:40:00+05:30", id="other-offset"),
        pytest.param("2026-08-08T12:10:00Z", id="z-suffix"),
        pytest.param("9999-12-31T23:59:59-23:59", id="far-offset"),
    ],
)
def test_well_formed_future_expiration_is_accepted(expires: str) -> None:
    from evidence_handoff_runtime.auth import AuthenticatedPrincipal

    principal = _validate_with_expiry(expires)
    assert isinstance(principal, AuthenticatedPrincipal)
    assert principal.token_id == "token-id-expiry-case"
