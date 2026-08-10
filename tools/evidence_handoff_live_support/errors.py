"""Verification failures with stable machine-readable codes."""

from __future__ import annotations


class VerificationError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        detail = message or code
        super().__init__(detail)

    def __repr__(self) -> str:
        return f"VerificationError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code
