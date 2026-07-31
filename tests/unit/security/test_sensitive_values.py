"""Non-disclosure tests for SensitiveValueInventory."""

from __future__ import annotations

import copy
import dataclasses
import logging
import pickle

import pytest

from optimus_security.sanitization import MAX_SECRET_TEXT_CHARS
from optimus_security.sensitive_values import (
    SensitiveValueError,
    SensitiveValueInventory,
    SensitiveValueSourceClass,
)


def test_inventory_has_no_dict() -> None:
    inventory = SensitiveValueInventory()
    assert not hasattr(inventory, "__dict__")
    with pytest.raises(AttributeError):
        _ = inventory.__dict__


def test_longest_first_deduplication_and_sanitizer_order() -> None:
    inventory = SensitiveValueInventory()
    inventory.add_secret("short", source_class=SensitiveValueSourceClass.ENVIRONMENT)
    inventory.add_secret("much-longer-secret-value", source_class=SensitiveValueSourceClass.KEYRING)
    inventory.add_secret("short", source_class=SensitiveValueSourceClass.CONFIG_FILE)
    secrets = inventory.secret_values_for_sanitizer()
    assert secrets == ("much-longer-secret-value", "short")
    assert inventory.secret_count == 2


def test_aggregate_source_class_counts_are_content_free() -> None:
    inventory = SensitiveValueInventory()
    inventory.add_secret("env-secret-value", source_class=SensitiveValueSourceClass.ENVIRONMENT)
    inventory.add_secret("keyring-secret-value", source_class=SensitiveValueSourceClass.KEYRING)
    inventory.add_pii("operator@example.com", source_class=SensitiveValueSourceClass.INJECTED_PII)
    assert inventory.source_class_counts == {
        "environment": 1,
        "keyring": 1,
        "injected_pii": 1,
    }
    rendered = repr(inventory)
    assert "env-secret-value" not in rendered
    assert "keyring-secret-value" not in rendered
    assert "operator@example.com" not in rendered
    assert "secret_count=2" in rendered


def test_rejects_empty_and_over_length_values() -> None:
    inventory = SensitiveValueInventory()
    with pytest.raises(SensitiveValueError, match="empty_sensitive_value"):
        inventory.add_secret("", source_class=SensitiveValueSourceClass.ENVIRONMENT)
    with pytest.raises(SensitiveValueError, match="sensitive_value_too_long"):
        inventory.add_secret(
            "x" * (MAX_SECRET_TEXT_CHARS + 1),
            source_class=SensitiveValueSourceClass.ENVIRONMENT,
        )


def test_blocks_pickle_copy_and_dataclass_conversion() -> None:
    inventory = SensitiveValueInventory()
    inventory.add_secret("secret-canary-value", source_class=SensitiveValueSourceClass.ENVIRONMENT)
    with pytest.raises(SensitiveValueError, match="sensitive_value_serialization_blocked"):
        pickle.dumps(inventory)
    with pytest.raises(SensitiveValueError, match="sensitive_value_copy_blocked"):
        copy.copy(inventory)
    with pytest.raises(SensitiveValueError, match="sensitive_value_copy_blocked"):
        copy.deepcopy(inventory)
    with pytest.raises(TypeError):
        dataclasses.asdict(inventory)  # type: ignore[arg-type]


def test_value_free_exceptions_and_log_records(caplog: pytest.LogCaptureFixture) -> None:
    inventory = SensitiveValueInventory()
    secret = "log-canary-secret-value"
    inventory.add_secret(secret, source_class=SensitiveValueSourceClass.ENVIRONMENT)
    with caplog.at_level(logging.INFO):
        logging.getLogger("optimus_security.sensitive_values").info("%s", inventory)
    assert secret not in caplog.text
    error = SensitiveValueError("empty_sensitive_value")
    assert str(error) == "empty_sensitive_value"
    assert secret not in repr(error)
