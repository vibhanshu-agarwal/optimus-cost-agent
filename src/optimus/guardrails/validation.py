from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ValidationVerdict(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    HOLD = "HOLD"


@dataclass(frozen=True)
class ValidationResult:
    verdict: ValidationVerdict
    rule_id: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.verdict is ValidationVerdict.ALLOW
