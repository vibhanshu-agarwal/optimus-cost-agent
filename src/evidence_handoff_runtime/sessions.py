"""MCP session binding for authenticated principals.

Session IDs are CSPRNG (`secrets`), never credentials, and bind principal + protocol.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from evidence_handoff_runtime.auth import AuthenticatedPrincipal


class SessionError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"SessionError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class SessionBinding:
    session_id: str
    principal_id: str
    protocol_version: str
    expires_at: datetime

    def __repr__(self) -> str:
        return (
            "SessionBinding("
            f"session_id={self.session_id!r}, "
            f"principal_id={self.principal_id!r}, "
            f"protocol_version={self.protocol_version!r}, "
            f"expires_at={self.expires_at.isoformat()!r})"
        )


@dataclass
class SessionRegistry:
    ttl: timedelta
    now: Callable[[], datetime]

    def __post_init__(self) -> None:
        self._bindings: dict[str, SessionBinding] = {}

    def create(self, principal: AuthenticatedPrincipal, protocol_version: str) -> SessionBinding:
        session_id = secrets.token_urlsafe(32)
        binding = SessionBinding(
            session_id=session_id,
            principal_id=principal.principal_id,
            protocol_version=protocol_version,
            expires_at=self.now() + self.ttl,
        )
        self._bindings[session_id] = binding
        return binding

    def validate(
        self,
        session_id: str,
        principal: AuthenticatedPrincipal,
        protocol_version: str | None = None,
    ) -> SessionBinding:
        binding = self._bindings.get(session_id)
        if binding is None or binding.expires_at <= self.now():
            self._bindings.pop(session_id, None)
            raise SessionError("session_expired_or_unknown")
        if binding.principal_id != principal.principal_id:
            raise SessionError("session_principal_mismatch")
        if protocol_version is not None and binding.protocol_version != protocol_version:
            raise SessionError("session_protocol_mismatch")
        return binding

    def attach(
        self,
        session_id: str,
        principal: AuthenticatedPrincipal,
        *,
        protocol_version: str,
    ) -> SessionBinding:
        """Bind an externally assigned session id (e.g. MCP transport) to a principal.

        Refuses to overwrite an active binding owned by a different principal.
        """
        if not session_id:
            raise SessionError("session_expired_or_unknown")
        existing = self._bindings.get(session_id)
        if existing is not None and existing.expires_at > self.now():
            if existing.principal_id != principal.principal_id:
                raise SessionError("session_principal_mismatch")
            if existing.protocol_version != protocol_version:
                raise SessionError("session_protocol_mismatch")
            return existing
        binding = SessionBinding(
            session_id=session_id,
            principal_id=principal.principal_id,
            protocol_version=protocol_version,
            expires_at=self.now() + self.ttl,
        )
        self._bindings[session_id] = binding
        return binding

    def resolve_or_adopt(
        self,
        session_id: str | None,
        principal: AuthenticatedPrincipal,
        *,
        protocol_version: str,
    ) -> str:
        """Validate an existing session, or adopt an unknown MCP transport session id.

        Principal mismatch and protocol mismatch are never auto-attached.
        """
        if not session_id:
            return self.create(principal, protocol_version=protocol_version).session_id
        try:
            self.validate(session_id, principal, protocol_version=protocol_version)
            return session_id
        except SessionError as exc:
            if exc.code != "session_expired_or_unknown":
                raise
            self.attach(session_id, principal, protocol_version=protocol_version)
            return session_id

    def expire(self, session_id: str) -> None:
        self._bindings.pop(session_id, None)


__all__ = [
    "SessionBinding",
    "SessionError",
    "SessionRegistry",
]
