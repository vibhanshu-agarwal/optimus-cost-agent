"""Value-free ledger validation and store errors."""

from __future__ import annotations


class LedgerValidationError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"LedgerValidationError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


class LedgerStoreError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"LedgerStoreError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


__all__ = ["LedgerStoreError", "LedgerValidationError"]
