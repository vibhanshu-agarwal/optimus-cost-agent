from __future__ import annotations

from decimal import Decimal
from typing import Any


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_safe(child) for child in value]
    if isinstance(value, Decimal):
        return str(value)
    return value
