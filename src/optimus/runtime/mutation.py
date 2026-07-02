from __future__ import annotations

from dataclasses import dataclass

MUTATION_FORBIDDEN_CODE = -32002


@dataclass(frozen=True)
class MutationForbidden(Exception):
    message: str
    code: int = MUTATION_FORBIDDEN_CODE

    def __str__(self) -> str:
        return self.message
