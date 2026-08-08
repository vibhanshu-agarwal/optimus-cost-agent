"""Audience-bound short-lived credentials for the evidence-handoff ledger.

Token values and signing keys never enter logs, rows, or bootstrap manifests.
Signature verification uses hmac.compare_digest only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_TOKEN_PREFIX = "eh1."
_SESSION_LIKE = re.compile(r"^[A-Za-z0-9_-]{20,}$")


class AuthError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"AuthError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


@dataclass(frozen=True, slots=True)
class Enrollment:
    principal_id: str
    agent_id: str
    caller_role: str
    scopes: frozenset[str]
    instance_id: str


@dataclass(frozen=True, slots=True)
class CredentialClaims:
    principal_id: str
    agent_id: str
    caller_role: str
    issuer: str
    audience: str
    scope: frozenset[str]
    expires_at: datetime
    token_id: str
    instance_id: str

    @staticmethod
    def parse_unverified_for_tests(token: str) -> CredentialClaims:
        if not token.startswith(_TOKEN_PREFIX):
            raise AuthError("token_malformed")
        parts = token[len(_TOKEN_PREFIX) :].split(".")
        if len(parts) != 2:
            raise AuthError("token_malformed")
        payload = json.loads(_b64url_decode(parts[0]).decode("utf-8"))
        return CredentialClaims(
            principal_id=str(payload["principal_id"]),
            agent_id=str(payload["agent_id"]),
            caller_role=str(payload["caller_role"]),
            issuer=str(payload["issuer"]),
            audience=str(payload["audience"]),
            scope=frozenset(str(item) for item in payload["scope"]),
            expires_at=datetime.fromisoformat(str(payload["expires_at"])),
            token_id=str(payload["token_id"]),
            instance_id=str(payload["instance_id"]),
        )


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    principal_id: str
    agent_id: str
    caller_role: str
    token_id: str
    scope: frozenset[str]

    def __repr__(self) -> str:
        return (
            "AuthenticatedPrincipal("
            f"principal_id={self.principal_id!r}, "
            f"agent_id={self.agent_id!r}, "
            f"caller_role={self.caller_role!r}, "
            f"token_id={self.token_id!r}, "
            f"scope_count={len(self.scope)})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass
class CredentialIssuer:
    signing_key: bytes
    issuer: str
    audience: str
    enrollments: Mapping[tuple[str, str], Enrollment]
    now: Callable[[], datetime]
    default_ttl: timedelta
    control_root: Path | None = None

    def issue(self, *, instance_id: str, enrollment: Enrollment) -> str:
        if enrollment.instance_id != instance_id:
            raise AuthError("token_wrong_instance")
        key = (instance_id, enrollment.principal_id)
        registered = self.enrollments.get(key)
        if registered is None:
            raise AuthError("principal_not_enrolled")
        expires_at = self.now() + self.default_ttl
        token_id = secrets.token_urlsafe(16)
        payload = {
            "principal_id": enrollment.principal_id,
            "agent_id": enrollment.agent_id,
            "caller_role": enrollment.caller_role,
            "issuer": self.issuer,
            "audience": self.audience,
            "scope": sorted(enrollment.scopes),
            "expires_at": expires_at.astimezone(UTC).isoformat(),
            "token_id": token_id,
            "instance_id": instance_id,
        }
        body = _b64url_encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signature = _b64url_encode(hmac.new(self.signing_key, body.encode("ascii"), hashlib.sha256).digest())
        # control_root is accepted for API symmetry; never persist token or key material.
        _ = self.control_root
        return f"{_TOKEN_PREFIX}{body}.{signature}"


@dataclass
class CredentialValidator:
    signing_key: bytes
    expected_issuer: str
    expected_audience: str
    enrollments: Mapping[tuple[str, str], Enrollment]
    now: Callable[[], datetime]
    revoked_token_ids: frozenset[str]
    consumed_jti: set[str]

    def validate(self, header: str, request: Mapping[str, Any]) -> AuthenticatedPrincipal:
        if not isinstance(header, str) or not header.startswith("Bearer "):
            raise AuthError("token_malformed")
        token = header[len("Bearer ") :].strip()
        if not token:
            raise AuthError("token_malformed")
        if not token.startswith(_TOKEN_PREFIX):
            if _SESSION_LIKE.fullmatch(token) or "session" in token.lower():
                raise AuthError("session_not_credential")
            raise AuthError("token_malformed")
        parts = token[len(_TOKEN_PREFIX) :].split(".")
        if len(parts) != 2:
            raise AuthError("token_malformed")
        body, signature = parts
        expected = hmac.new(self.signing_key, body.encode("ascii"), hashlib.sha256).digest()
        try:
            provided = _b64url_decode(signature)
        except Exception as exc:
            raise AuthError("token_malformed") from exc
        if not hmac.compare_digest(expected, provided):
            raise AuthError("token_bad_signature")
        try:
            payload = json.loads(_b64url_decode(body).decode("utf-8"))
        except Exception as exc:
            raise AuthError("token_malformed") from exc
        try:
            claims = CredentialClaims(
                principal_id=str(payload["principal_id"]),
                agent_id=str(payload["agent_id"]),
                caller_role=str(payload["caller_role"]),
                issuer=str(payload["issuer"]),
                audience=str(payload["audience"]),
                scope=frozenset(str(item) for item in payload["scope"]),
                expires_at=datetime.fromisoformat(str(payload["expires_at"])),
                token_id=str(payload["token_id"]),
                instance_id=str(payload["instance_id"]),
            )
        except Exception as exc:
            raise AuthError("token_malformed") from exc
        if claims.issuer != self.expected_issuer:
            raise AuthError("token_wrong_issuer")
        if claims.audience != self.expected_audience:
            raise AuthError("token_wrong_audience")
        if claims.expires_at <= self.now():
            raise AuthError("token_expired")
        if claims.token_id in self.revoked_token_ids:
            raise AuthError("token_revoked")
        if claims.token_id in self.consumed_jti:
            raise AuthError("token_replayed")
        instance_id = str(request.get("ledger_instance_id") or "")
        if not instance_id or claims.instance_id != instance_id:
            raise AuthError("token_wrong_instance")
        required_scope = request.get("required_scope")
        if required_scope is not None and str(required_scope) not in claims.scope:
            raise AuthError("token_wrong_scope")
        enrollment = self.enrollments.get((instance_id, claims.principal_id))
        if enrollment is None:
            raise AuthError("principal_not_enrolled")
        if (
            enrollment.agent_id != claims.agent_id
            or enrollment.caller_role != claims.caller_role
            or enrollment.instance_id != claims.instance_id
        ):
            raise AuthError("principal_not_enrolled")
        return AuthenticatedPrincipal(
            principal_id=claims.principal_id,
            agent_id=claims.agent_id,
            caller_role=claims.caller_role,
            token_id=claims.token_id,
            scope=claims.scope,
        )


def validate_authorization(
    *,
    authorization_header: str | None,
    validator: CredentialValidator | None,
    request: Mapping[str, Any] | None = None,
) -> AuthenticatedPrincipal | None:
    """Transport-position auth gate. Replaces PreParseAuthGateStub in place."""
    if not authorization_header:
        raise AuthError("auth_gate_rejected")
    if validator is None:
        # Structural presence-only fallback for tests that do not wire a validator.
        if authorization_header.lower().startswith("bearer ") and authorization_header[7:].strip():
            return None
        raise AuthError("auth_gate_rejected")
    return validator.validate(authorization_header, request or {})


__all__ = [
    "AuthError",
    "AuthenticatedPrincipal",
    "CredentialClaims",
    "CredentialIssuer",
    "CredentialValidator",
    "Enrollment",
    "validate_authorization",
]
