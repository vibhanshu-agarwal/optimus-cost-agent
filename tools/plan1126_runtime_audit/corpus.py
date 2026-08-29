"""Frozen literal corpus and reproducible binding-derived seeds."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_DEFAULT_CORPUS = Path(__file__).parents[2] / "tests" / "fixtures" / "plan1126_runtime_audit" / "frozen-regression-seeds.json"


def literal_seeds(*, binding_commit: str | None = None, path: Path | str | None = None) -> tuple[int, ...]:
    """Return frozen seeds; ``binding_commit`` is accepted but deliberately irrelevant."""

    del binding_commit
    payload = json.loads(Path(path or _DEFAULT_CORPUS).read_text(encoding="utf-8"))
    if set(payload) != {"schema_version", "seeds"} or payload["schema_version"] != "plan-11-26-frozen-regression-seeds-v1":
        raise ValueError("literal seed corpus schema is invalid")
    seeds = tuple(payload["seeds"])
    if any(not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**64 for seed in seeds):
        raise ValueError("literal seeds must be unsigned 64-bit integers")
    return seeds


def derived_seed(binding_commit: str, scenario_id: str, n: int) -> int:
    if len(binding_commit) != 40 or any(character not in "0123456789abcdef" for character in binding_commit):
        raise ValueError("binding_commit must be a lowercase 40-hex commit")
    if not scenario_id or n < 0:
        raise ValueError("scenario_id must be non-empty and n must be non-negative")
    digest = hashlib.sha256(f"{binding_commit}{scenario_id}{n}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")
