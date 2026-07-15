"""Tests for the shared sanitization module.

Plan 9.96, Task 4 Step 4: Tests cover every Tier 1 name, nested containers,
bearer/header/assignment forms, URI schemes, and objects whose __repr__/__str__
raise or contain canaries.
"""

from __future__ import annotations

from optimus_security.sanitization import (
    mask_uri_userinfo,
    sanitize_for_persistence,
)


class TestExactSecretReplacement:
    """Known secrets are replaced with the redaction placeholder."""

    def test_single_known_secret_in_text(self) -> None:
        result = sanitize_for_persistence(
            "key is sk-ant-secret123 here",
            known_secrets=["sk-ant-secret123"],
        )
        assert "sk-ant-secret123" not in result.value
        assert "**********" in result.value
        assert result.rule_counts.get("exact_secret_replacement", 0) > 0

    def test_multiple_known_secrets(self) -> None:
        result = sanitize_for_persistence(
            "first=abc123 second=xyz789",
            known_secrets=["abc123", "xyz789"],
        )
        assert "abc123" not in result.value
        assert "xyz789" not in result.value

    def test_longest_secret_matched_first(self) -> None:
        """When secrets overlap, the longest match wins."""
        result = sanitize_for_persistence(
            "value is sk-ant-very-long-key here",
            known_secrets=["sk-ant", "sk-ant-very-long-key"],
        )
        assert "sk-ant-very-long-key" not in result.value
        # The shorter prefix should also be gone since it's a substring.
        assert "sk-ant" not in result.value

    def test_empty_secrets_list_is_safe(self) -> None:
        result = sanitize_for_persistence("no secrets here", known_secrets=[])
        assert result.value == "no secrets here"

    def test_secret_in_nested_dict(self) -> None:
        data = {"config": {"key": "my-secret-value"}}
        result = sanitize_for_persistence(data, known_secrets=["my-secret-value"])
        assert "my-secret-value" not in str(result.value)

    def test_secret_in_list(self) -> None:
        data = ["safe", "my-secret", "also-safe"]
        result = sanitize_for_persistence(data, known_secrets=["my-secret"])
        assert "my-secret" not in str(result.value)


class TestUriUserinfoMasking:
    """URI user information is masked in free text."""

    def test_http_userinfo_masked(self) -> None:
        result = sanitize_for_persistence(
            "connecting to http://admin:hunter2@db.example.com:5432/mydb",
            known_secrets=[],
        )
        assert "hunter2" not in result.value
        assert "admin" not in result.value

    def test_https_userinfo_masked(self) -> None:
        result = sanitize_for_persistence(
            "url: https://user:pass@host.com/path",
            known_secrets=[],
        )
        assert "pass" not in result.value
        assert "user:" not in result.value

    def test_redis_userinfo_masked(self) -> None:
        """Redis URLs with credentials get masked."""
        result = sanitize_for_persistence(
            "OPTIMUS_REDIS_URL=redis://default:s3cr3t@127.0.0.1:6379/0",
            known_secrets=[],
        )
        assert "s3cr3t" not in result.value

    def test_password_only_redis_url_masked(self) -> None:
        """Redis URLs with password-only auth (no username) get masked."""
        result = sanitize_for_persistence(
            "connecting to redis://:hunter2@127.0.0.1:6379/0",
            known_secrets=[],
        )
        assert "hunter2" not in result.value

    def test_no_userinfo_unchanged(self) -> None:
        result = sanitize_for_persistence(
            "http://example.com/path",
            known_secrets=[],
        )
        assert result.value == "http://example.com/path"


class TestBearerAndHeaderRedaction:
    """Bearer tokens and API key headers are redacted."""

    def test_bearer_token_redacted(self) -> None:
        result = sanitize_for_persistence(
            "Authorization: Bearer sk-ant-very-secret-token",
            known_secrets=[],
        )
        assert "sk-ant-very-secret-token" not in result.value

    def test_lowercase_bearer_redacted(self) -> None:
        result = sanitize_for_persistence(
            "bearer my-token-123",
            known_secrets=[],
        )
        assert "my-token-123" not in result.value

    def test_x_api_key_header_redacted(self) -> None:
        result = sanitize_for_persistence(
            "x-api-key: sk-proj-abcdef",
            known_secrets=[],
        )
        assert "sk-proj-abcdef" not in result.value

    def test_api_key_header_redacted(self) -> None:
        result = sanitize_for_persistence(
            "api_key: my-key-value",
            known_secrets=[],
        )
        assert "my-key-value" not in result.value


class TestEnvAssignmentRedaction:
    """Environment variable assignment patterns are redacted."""

    def test_optimus_api_key_assignment(self) -> None:
        result = sanitize_for_persistence(
            "OPTIMUS_API_KEY=opt-secret-value",
            known_secrets=[],
        )
        assert "opt-secret-value" not in result.value

    def test_anthropic_api_key_assignment(self) -> None:
        result = sanitize_for_persistence(
            "ANTHROPIC_API_KEY=sk-ant-canary",
            known_secrets=[],
        )
        assert "sk-ant-canary" not in result.value

    def test_generic_secret_assignment(self) -> None:
        result = sanitize_for_persistence(
            "password=hunter2",
            known_secrets=[],
        )
        assert "hunter2" not in result.value

    def test_token_colon_assignment(self) -> None:
        result = sanitize_for_persistence(
            "token: my-bearer-tok",
            known_secrets=[],
        )
        assert "my-bearer-tok" not in result.value


class TestDictKeyRedaction:
    """Dictionary keys that indicate secrets get their values redacted."""

    def test_api_key_field_redacted(self) -> None:
        data = {"api_key": "sk-secret-123", "model": "gpt-4"}
        result = sanitize_for_persistence(data, known_secrets=[])
        assert result.value["api_key"] == "**********"
        assert result.value["model"] == "gpt-4"

    def test_authorization_field_redacted(self) -> None:
        data = {"authorization": "Bearer token123"}
        result = sanitize_for_persistence(data, known_secrets=[])
        assert result.value["authorization"] == "**********"

    def test_nested_secret_field(self) -> None:
        data = {"headers": {"x-api-key": "my-key"}}
        result = sanitize_for_persistence(data, known_secrets=[])
        assert result.value["headers"]["x-api-key"] == "**********"

    def test_password_field_redacted(self) -> None:
        data = {"password": "p4ssw0rd", "username": "admin"}
        result = sanitize_for_persistence(data, known_secrets=[])
        assert result.value["password"] == "**********"
        assert result.value["username"] == "admin"

    def test_optimus_api_key_field_redacted(self) -> None:
        data = {"optimus_api_key": "opt-secret"}
        result = sanitize_for_persistence(data, known_secrets=[])
        assert result.value["optimus_api_key"] == "**********"


class TestUnsupportedObjects:
    """Unsupported objects return safe type metadata without repr/str."""

    def test_custom_object_returns_type_metadata(self) -> None:
        class MyCustomClass:
            def __repr__(self) -> str:
                return "CANARY_REPR_SHOULD_NOT_APPEAR"

            def __str__(self) -> str:
                return "CANARY_STR_SHOULD_NOT_APPEAR"

        obj = MyCustomClass()
        result = sanitize_for_persistence(obj, known_secrets=[])
        assert "CANARY_REPR" not in str(result.value)
        assert "CANARY_STR" not in str(result.value)
        # Should contain type info.
        assert "MyCustomClass" in str(result.value)
        assert result.rule_counts.get("unsupported_object_type_metadata", 0) > 0

    def test_object_with_raising_repr(self) -> None:
        class BadRepr:
            def __repr__(self) -> str:
                raise RuntimeError("repr exploded")

            def __str__(self) -> str:
                raise RuntimeError("str exploded")

        result = sanitize_for_persistence(BadRepr(), known_secrets=[])
        assert "BadRepr" in str(result.value)
        # Must not crash.

    def test_object_with_secret_in_repr(self) -> None:
        class LeakyRepr:
            def __repr__(self) -> str:
                return "Object(secret=hunter2-canary-value)"

        result = sanitize_for_persistence(LeakyRepr(), known_secrets=["hunter2-canary-value"])
        # Type metadata, not repr output.
        assert "hunter2-canary-value" not in str(result.value)
        assert "LeakyRepr" in str(result.value)


class TestRuleCounts:
    """Rule counts are content-free metadata."""

    def test_rule_counts_are_integers(self) -> None:
        result = sanitize_for_persistence(
            "OPTIMUS_API_KEY=secret bearer token123",
            known_secrets=["secret"],
        )
        for count in result.rule_counts.values():
            assert isinstance(count, int)
            assert count > 0

    def test_no_rules_fired_returns_empty_counts(self) -> None:
        result = sanitize_for_persistence("safe text", known_secrets=[])
        assert result.rule_counts == {}


class TestMaskUriUserinfo:
    """URI masking utility."""

    def test_masks_username_and_password(self) -> None:
        masked = mask_uri_userinfo("redis://user:password@host:6379/0")
        assert "user" not in masked
        assert "password" not in masked
        assert "host:6379/0" in masked

    def test_no_userinfo_unchanged(self) -> None:
        uri = "http://example.com:8080/path"
        assert mask_uri_userinfo(uri) == uri

    def test_password_only_masked(self) -> None:
        masked = mask_uri_userinfo("redis://:secret@host:6379")
        assert "secret" not in masked


class TestPrimitivePassthrough:
    """Primitive types pass through unchanged."""

    def test_int_unchanged(self) -> None:
        result = sanitize_for_persistence(42, known_secrets=[])
        assert result.value == 42

    def test_float_unchanged(self) -> None:
        result = sanitize_for_persistence(3.14, known_secrets=[])
        assert result.value == 3.14

    def test_bool_unchanged(self) -> None:
        result = sanitize_for_persistence(True, known_secrets=[])
        assert result.value is True

    def test_none_unchanged(self) -> None:
        result = sanitize_for_persistence(None, known_secrets=[])
        assert result.value is None
