"""The curated model registry (ADR-004): strict YAML, a typed immutable schema and its effective hash.

Reviewed defaults ship with the package; an optional operator override is combined over them by
declared keys (maps combine, lists replace). The YAML loader rejects every feature that could make
two readers see different data: duplicate keys at any depth, anchors, aliases, ``<<`` merge keys
(quoted or not), non-string keys and any tag outside plain str/int/float/bool/null/map/seq. The
combined result is validated against a strict schema that forbids unknown fields and loose types
(a quoted or boolean integer, a float count), then hashed from its canonical JSON with numbers in
normalized form, so formatting alone (``0.10`` or ``0.1``) never changes the effective snapshot.

This module is neutral: it imports nothing from ``optimus``, ``optimus_gateway`` or
``optimus_security``, so the host and the Gateway share one validator.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

__all__ = [
    "Capabilities",
    "DataUse",
    "Endpoint",
    "EstimatorProfile",
    "ModelEntry",
    "Origin",
    "Policy",
    "Prices",
    "RegistryError",
    "RegistrySnapshot",
    "Role",
    "Route",
    "SummaryReceipt",
    "Tier",
    "load_registry",
]

MAX_CONTEXT_CEILING_TOKENS = 262_144
"""ADR-003's total context ceiling, output reserve included once."""

SUMMARY_FORMAT = "context-summary-v1"
"""The accepted host-wrapped plain-text summary format (Task 1 contracts §3)."""

# The rest of a summarizer qualification key (Task 1 contracts §3; Plan 12.2 Task 8). A receipt
# qualifies a route only for these exact values: a changed prompt, validator or fixture invalidates
# every receipt until the check is run and reviewed again. They are pinned here so this neutral package
# need not import the engine; a cross-check test keeps them equal to the engine's prompt, its
# validator version and the fixture's canonical digest.
SUMMARY_PROMPT_DIGEST = "6d1b4e77d77f1a7331932633dbc39ae4f1c3bf5c4a79acf8aed9873b410902db"  # pragma: allowlist secret - public prompt digest
SUMMARY_VALIDATOR = "context-summary-validator-v4"
SUMMARY_FIXTURE_DIGEST = "10eafc91d3ca0025887e82ecf08136218bb1e886bfc5b627d72688fce8efd960"  # pragma: allowlist secret - public fixture digest


class RegistryError(Exception):
    """The registry could not be loaded. ``code`` is ``YAML_REJECTED`` or ``SCHEMA_INVALID``."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class Origin(StrEnum):
    CHINA = "china"
    NON_CHINA = "non-china"


class Tier(StrEnum):
    ULTRA_CHEAP = "ultra-cheap"
    CHEAP = "cheap"
    REVIEW = "review"


class Role(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    COMPLEX = "complex"
    ESCALATION = "escalation"
    SUMMARIZER = "summarizer"
    REVIEWER = "reviewer"
    CLASSIFIER = "classifier"


IMPLEMENTER_ROLES = frozenset({Role.EASY, Role.MEDIUM, Role.COMPLEX, Role.ESCALATION})
DORMANT_ROLES = frozenset({Role.REVIEWER, Role.CLASSIFIER})
"""Reviewer awaits its artifact contract (ADR-008); classifier awaits proposed ADR-007."""

ReserveClass = Literal["implementer", "summarizer", "reviewer", "classifier"]


def reserve_class(role: Role) -> ReserveClass:
    if role in IMPLEMENTER_ROLES:
        return "implementer"
    return role.value  # type: ignore[return-value]


# --- Strict YAML -----------------------------------------------------------------------------------

_ALLOWED_TAGS = frozenset(
    {
        "tag:yaml.org,2002:str",
        "tag:yaml.org,2002:int",
        "tag:yaml.org,2002:float",
        "tag:yaml.org,2002:bool",
        "tag:yaml.org,2002:null",
        "tag:yaml.org,2002:seq",
        "tag:yaml.org,2002:map",
    }
)
_MERGE_TAG = "tag:yaml.org,2002:merge"


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that also refuses anchors, aliases, merge keys, duplicates and non-plain tags."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise RegistryError("YAML_REJECTED", "aliases are not allowed")
        event = self.peek_event()
        if getattr(event, "anchor", None) is not None:
            raise RegistryError("YAML_REJECTED", "anchors are not allowed")
        return super().compose_node(parent, index)

    def construct_object(self, node: Any, deep: bool = False) -> Any:
        if node.tag not in _ALLOWED_TAGS and node.tag != _MERGE_TAG:
            raise RegistryError("YAML_REJECTED", f"tag {node.tag!r} is not allowed")
        return super().construct_object(node, deep=deep)

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[str, Any]:
        if not isinstance(node, yaml.MappingNode):
            raise RegistryError("YAML_REJECTED", "expected a mapping")
        mapping: dict[str, Any] = {}
        for key_node, value_node in node.value:
            if key_node.tag == _MERGE_TAG:
                raise RegistryError("YAML_REJECTED", "'<<' merge keys are not allowed")
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise RegistryError("YAML_REJECTED", f"mapping key {key!r} is not a string")
            if key == "<<":
                raise RegistryError("YAML_REJECTED", "'<<' merge keys are not allowed")
            if key in mapping:
                raise RegistryError("YAML_REJECTED", f"duplicate key {key!r}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _load_yaml(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        loader = _StrictLoader(raw.decode("utf-8"))
        try:
            data = loader.get_single_data()
        finally:
            loader.dispose()
    except RegistryError:
        raise
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise RegistryError("YAML_REJECTED", f"{path.name}: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RegistryError("YAML_REJECTED", f"{path.name}: the document must be a mapping")
    return data, raw


def _combine(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Maps combine by declared key; every other value, lists included, is replaced."""
    combined = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(combined.get(key), Mapping):
            combined[key] = _combine(combined[key], value)
        else:
            combined[key] = value
    return combined


# --- Typed schema ----------------------------------------------------------------------------------

_FROZEN = ConfigDict(frozen=True, extra="forbid")


def _decimal_text(value: Any) -> Any:
    """Money and ratios come from quoted text or integers, never binary floats."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("write this number as quoted text, e.g. \"0.10\"")
    return value


def canonical_decimal(value: Decimal) -> str:
    """One text per value: ``0.10``, ``0.1`` and ``1E-1`` all hash as ``0.1``."""
    return format(value.normalize(), "f")


_CanonicalJson = PlainSerializer(canonical_decimal, return_type=str, when_used="json")
NonNegativeDecimal = Annotated[Decimal, Field(ge=0, allow_inf_nan=False), _CanonicalJson]
StrictCount = Annotated[int, Field(ge=0, strict=True)]
PositiveCount = Annotated[int, Field(gt=0, strict=True)]
StrictFlag = Annotated[bool, Field(strict=True)]


class Prices(BaseModel):
    model_config = _FROZEN

    input_usd_per_million: NonNegativeDecimal
    output_usd_per_million: NonNegativeDecimal

    @field_validator("input_usd_per_million", "output_usd_per_million", mode="before")
    @classmethod
    def prices_from_text(cls, value: Any) -> Any:
        return _decimal_text(value)


class DataUse(BaseModel):
    model_config = _FROZEN

    provider_may_train_on_inputs: Literal["yes", "no", "unverified"]
    disclosure: Literal["none", "contributor"]


class Capabilities(BaseModel):
    model_config = _FROZEN

    native_tools: StrictFlag
    text_planning_grammar: StrictFlag
    structured_output: StrictFlag
    reasoning_levels: tuple[str, ...]


class Endpoint(BaseModel):
    model_config = _FROZEN

    provider: Annotated[str, Field(min_length=1)]
    quantization: str | None
    context_window_tokens: PositiveCount | None
    max_output_tokens: PositiveCount | None
    verified: StrictFlag
    observed_on: str | None = None


class Route(BaseModel):
    model_config = _FROZEN

    estimator: Annotated[str, Field(min_length=1)]
    endpoints: Annotated[tuple[Endpoint, ...], Field(min_length=1)]
    allow_fallbacks: StrictFlag = False
    require_parameters: StrictFlag = True

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(endpoint.provider for endpoint in self.endpoints)

    @property
    def quantizations(self) -> tuple[str | None, ...]:
        return tuple(endpoint.quantization for endpoint in self.endpoints)


class SummaryReceipt(BaseModel):
    """A reviewed passing summary-quality check for one model, route and setting (Plan 12.2 Task 8).
    It binds the exact model ID, the format, the route (each endpoint's provider and quantization),
    reasoning, fixture, prompt and validator; request IDs and date record the run."""

    model_config = _FROZEN

    model_id: Annotated[str, Field(min_length=1)]
    format: str
    providers: tuple[str, ...]
    quantizations: tuple[str | None, ...]
    reasoning: str | None
    fixture_digest: str
    prompt_digest: str
    validator: str
    request_ids: tuple[str, ...]
    recorded_on: str
    result: Literal["pass"]


class EstimatorProfile(BaseModel):
    model_config = _FROZEN

    method: Literal["utf8-bytes-ratio"]
    tokens_per_byte: Annotated[Decimal, Field(gt=0, le=4, allow_inf_nan=False), _CanonicalJson]
    per_message_tokens: StrictCount
    fixed_tokens: StrictCount
    verified: StrictFlag

    @field_validator("tokens_per_byte", mode="before")
    @classmethod
    def ratio_from_text(cls, value: Any) -> Any:
        return _decimal_text(value)


class ModelEntry(BaseModel):
    model_config = _FROZEN

    origin: Origin
    tier: Tier
    prices: Prices
    data_use: DataUse
    capabilities: Capabilities
    default_reasoning: str | None
    route: Route
    summary_receipts: tuple[SummaryReceipt, ...] = ()
    evidence: tuple[str, ...] = ()


class Alerts(BaseModel):
    model_config = _FROZEN

    thresholds_usd: tuple[NonNegativeDecimal, ...] = ()

    @field_validator("thresholds_usd", mode="before")
    @classmethod
    def text_thresholds(cls, value: Any) -> Any:
        return tuple(_decimal_text(v) for v in value) if isinstance(value, (list, tuple)) else value

    @model_validator(mode="after")
    def increasing(self) -> Alerts:
        if list(self.thresholds_usd) != sorted(set(self.thresholds_usd)):
            raise ValueError("alert thresholds must be strictly increasing")
        return self


class Policy(BaseModel):
    model_config = _FROZEN

    schema_version: Literal[1]
    policy_version: Annotated[str, Field(min_length=1)]
    fixture: StrictFlag
    context_ceiling_tokens: Annotated[int, Field(gt=0, le=MAX_CONTEXT_CEILING_TOKENS, strict=True)]
    output_reserve_tokens: dict[ReserveClass, PositiveCount]
    estimators: dict[str, EstimatorProfile]
    role_price_blends: dict[Role, Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]]
    alerts: Alerts
    models: dict[str, ModelEntry]
    roles: dict[Role, tuple[str, ...]]

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_schema_version(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("schema_version must be the integer 1")
        return value

    @field_validator("role_price_blends", mode="before")
    @classmethod
    def text_blends(cls, value: Any) -> Any:
        return {k: _decimal_text(v) for k, v in value.items()} if isinstance(value, Mapping) else value

    @model_validator(mode="after")
    def unambiguous_and_frozen(self) -> Policy:
        seen: dict[str, str] = {}
        for model_id in self.models:
            if not model_id or any(character.isspace() for character in model_id):
                raise ValueError(f"model id {model_id!r} must be non-empty with no whitespace")
            folded = model_id.casefold()
            if folded in seen:
                raise ValueError(f"model ids {seen[folded]!r} and {model_id!r} differ only by case")
            seen[folded] = model_id
        for name in ("output_reserve_tokens", "estimators", "role_price_blends", "models", "roles"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))
        return self

    @field_serializer("output_reserve_tokens", "estimators", "role_price_blends", "models", "roles")
    def serialize_mapping(self, value: Mapping[Any, Any]) -> dict[str, Any]:
        def plain(item: Any) -> Any:
            if isinstance(item, BaseModel):
                return item.model_dump(mode="json")
            if isinstance(item, Decimal):
                return canonical_decimal(item)
            if isinstance(item, tuple):
                return list(item)
            return item

        return {str(key): plain(item) for key, item in value.items()}


# --- Snapshot --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    """A validated, immutable registry and its provenance.

    ``effective_hash`` is the SHA-256 of the canonical JSON of the combined typed policy; it is what
    a launch approval binds. ``input_hashes`` records each input file's bytes for provenance only.
    """

    policy: Policy
    effective_hash: str
    input_hashes: tuple[tuple[str, str], ...]


def _canonical_hash(policy: Policy) -> str:
    canonical = json.dumps(policy.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_registry(defaults: Path, override: Path | None) -> RegistrySnapshot:
    """Load the defaults, combine the optional override over them, validate and hash the result."""
    base, base_raw = _load_yaml(defaults)
    combined = base
    input_hashes = [(defaults.name, hashlib.sha256(base_raw).hexdigest())]
    if override is not None:
        extra, extra_raw = _load_yaml(override)
        combined = _combine(base, extra)
        input_hashes.append((override.name, hashlib.sha256(extra_raw).hexdigest()))
    try:
        policy = Policy.model_validate(combined)
    except ValidationError as exc:
        raise RegistryError("SCHEMA_INVALID", str(exc)) from exc
    return RegistrySnapshot(policy=policy, effective_hash=_canonical_hash(policy), input_hashes=tuple(input_hashes))
