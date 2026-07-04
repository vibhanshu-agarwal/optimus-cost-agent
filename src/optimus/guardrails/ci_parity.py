from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GuardrailRuleSet:
    check_names: frozenset[str]

    @classmethod
    def phase1(cls) -> "GuardrailRuleSet":
        return cls(
            frozenset(
                {
                    "hygiene",
                    "ruff",
                    "bandit",
                    "ast-grep",
                    "config-trust-scan",
                    "secret-scan",
                    "pytest-coverage",
                }
            )
        )


def load_pre_commit_check_names(path: Path) -> frozenset[str]:
    text = path.read_text(encoding="utf-8")
    return frozenset(name for name in GuardrailRuleSet.phase1().check_names if f"optimus-check: {name}" in text)


def load_ci_check_names(path: Path) -> frozenset[str]:
    text = path.read_text(encoding="utf-8")
    return frozenset(name for name in GuardrailRuleSet.phase1().check_names if f"optimus-check: {name}" in text)
