"""Constants for content-free three-agent live manifests."""

from __future__ import annotations

REQUIRED_AGENT_FIELDS: frozenset[str] = frozenset(
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
        "process_identity",
        "credential_fingerprint",
    }
)

# Field names that must never appear in a content-free manifest (raw secrets).
TOKEN_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "access_token",
        "refresh_token",
        "bearer_token",
        "token",
        "api_key",
        "password",
        "secret",
        "authorization",
        "credential",
        "credentials",
        "raw_credential",
        "client_secret",
    }
)

MOCK_SERVICE_MARKERS: frozenset[str] = frozenset(
    {
        "mock",
        "mocked",
        "fake",
        "simulated",
        "harness",
        "stub",
    }
)

EXPECTED_CLIENT_NAMES: frozenset[str] = frozenset({"claude_code", "cursor", "codex"})
