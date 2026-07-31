"""In-memory sensitive-value inventory with value-free non-disclosure guards.

Slot-based container: no ``__dict__``, blocked pickle/copy, value-suppressing
``repr``/``str``, and value-free errors/log metadata. Deduplicates longest-first
for sanitizer accessors and tracks aggregate source-class counts only.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import NoReturn

from optimus_security.sanitization import MAX_SECRET_TEXT_CHARS


class SensitiveValueSourceClass(StrEnum):
    ENVIRONMENT = "environment"
    CONFIG_FILE = "config_file"
    KEYRING = "keyring"
    INJECTED_PII = "injected_pii"


class SensitiveValueError(Exception):
    """Value-free inventory failure. Message is the stable code only."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"SensitiveValueError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


class SensitiveValueInventory:
    """Process-local secret/PII inventory for evidence redaction."""

    __slots__ = ("_secrets", "_pii", "_source_counts")

    def __init__(self) -> None:
        self._secrets: list[tuple[str, SensitiveValueSourceClass]] = []
        self._pii: list[tuple[str, SensitiveValueSourceClass]] = []
        self._source_counts: dict[str, int] = {}

    def add_secret(self, value: str, *, source_class: SensitiveValueSourceClass) -> None:
        self._add(value, source_class=source_class, bucket=self._secrets)

    def add_pii(self, value: str, *, source_class: SensitiveValueSourceClass) -> None:
        self._add(value, source_class=source_class, bucket=self._pii)

    def _add(
        self,
        value: str,
        *,
        source_class: SensitiveValueSourceClass,
        bucket: list[tuple[str, SensitiveValueSourceClass]],
    ) -> None:
        if not isinstance(value, str) or value == "":
            raise SensitiveValueError("empty_sensitive_value")
        if len(value) > MAX_SECRET_TEXT_CHARS:
            raise SensitiveValueError("sensitive_value_too_long")
        if any(existing == value for existing, _ in bucket):
            return
        bucket.append((value, source_class))
        key = str(source_class)
        self._source_counts[key] = self._source_counts.get(key, 0) + 1

    def secret_values_for_sanitizer(self) -> tuple[str, ...]:
        return tuple(sorted((value for value, _ in self._secrets), key=len, reverse=True))

    def pii_values_for_sanitizer(self) -> tuple[str, ...]:
        return tuple(sorted((value for value, _ in self._pii), key=len, reverse=True))

    @property
    def secret_count(self) -> int:
        return len(self._secrets)

    @property
    def pii_count(self) -> int:
        return len(self._pii)

    @property
    def source_class_counts(self) -> Mapping[str, int]:
        return dict(self._source_counts)

    def __repr__(self) -> str:
        return (
            "SensitiveValueInventory("
            f"secret_count={self.secret_count}, "
            f"pii_count={self.pii_count}, "
            f"source_class_counts={dict(self._source_counts)!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def __getstate__(self) -> NoReturn:
        raise SensitiveValueError("sensitive_value_serialization_blocked")

    def __setstate__(self, state: object) -> NoReturn:
        raise SensitiveValueError("sensitive_value_serialization_blocked")

    def __copy__(self) -> NoReturn:
        raise SensitiveValueError("sensitive_value_copy_blocked")

    def __deepcopy__(self, memo: dict[int, object]) -> NoReturn:
        raise SensitiveValueError("sensitive_value_copy_blocked")
