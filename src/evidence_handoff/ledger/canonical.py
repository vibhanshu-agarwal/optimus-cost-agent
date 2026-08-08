"""Deterministic canonical serialization for ledger envelopes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_json(value: Mapping[str, Any] | list[Any] | str | int | float | bool | None) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def content_sha256_for_envelope(fields: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in fields.items() if key != "content_sha256"}
    return hashlib.sha256(canonical_json(payload)).hexdigest()


__all__ = ["canonical_json", "content_sha256_for_envelope"]
