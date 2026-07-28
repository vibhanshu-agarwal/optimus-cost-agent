from __future__ import annotations

PROVIDER_MODEL_ALIASES: dict[str, dict[str, str]] = {
    "openrouter": {
        "claude-haiku": "anthropic/claude-haiku-4.5",
    },
}


def resolve_model_id(*, provider: str, model: str) -> str:
    normalized = model.strip()
    aliases = PROVIDER_MODEL_ALIASES.get(provider, {})
    if normalized in aliases:
        return aliases[normalized]
    if is_plausible_passthrough(provider, normalized):
        return normalized
    raise ValueError(f"unsupported gateway model: {normalized}")


def is_plausible_passthrough(provider: str, model: str) -> bool:
    if not model or " " in model:
        return False
    if provider == "openrouter":
        return "/" in model
    return False
