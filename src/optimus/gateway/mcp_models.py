from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MCPAttribution = Literal["settled", "explicit_zero", "unavailable"]
MCPContentType = Literal["text", "structured", "resource_link", "embedded_resource"]
MCPFreshness = Literal["fresh", "stale", "unchanged"]
MCPResultType = Literal["complete", "input_required"]
MCPTransport = Literal["http", "stdio"]

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PROFILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_TOOL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _non_empty(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _profile_id(value: str) -> str:
    value = _non_empty(value, field_name="profile_id")
    if _PROFILE_PATTERN.fullmatch(value) is None:
        raise ValueError("profile_id contains unsupported characters")
    return value


def _tool_name(value: str) -> str:
    value = _non_empty(value, field_name="tool_name")
    if _TOOL_PATTERN.fullmatch(value) is None:
        raise ValueError("tool_name contains unsupported characters")
    return value


def _manifest_hash(value: str) -> str:
    value = _non_empty(value, field_name="manifest_hash")
    if _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError("manifest_hash must be a lowercase SHA-256 hex digest")
    return value


def _assert_json_value(value: Any, *, path: str) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be finite")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} must use string JSON object keys")
            _assert_json_value(item, path=f"{path}.{key}")
        return
    raise ValueError(f"{path} contains a value that is not JSON-compatible")


class MCPToolDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    description: str = ""
    input_schema: dict[str, Any]
    annotations: dict[str, Any] = Field(default_factory=dict)
    side_effect_class: Literal["read", "network", "write"] = "read"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _tool_name(value)

    @field_validator("input_schema", "annotations")
    @classmethod
    def validate_json_mapping(cls, value: dict[str, Any], info: Any) -> dict[str, Any]:
        _assert_json_value(value, path=info.field_name)
        return value


class MCPContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: MCPContentType
    text: str | None = None
    data: Any | None = None
    uri: str | None = None
    name: str | None = None
    mime_type: str | None = None
    resource: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_content_payload(self) -> MCPContent:
        if self.type == "text":
            if self.text is None or any(value is not None for value in (self.data, self.resource, self.uri)):
                raise ValueError("text content requires only text")
            return self
        if self.type == "structured":
            if self.data is None or any(value is not None for value in (self.text, self.resource, self.uri)):
                raise ValueError("structured content requires data")
            _assert_json_value(self.data, path="data")
            return self
        if self.type == "resource_link":
            if self.uri is None or not self.uri.strip() or any(value is not None for value in (self.text, self.data, self.resource)):
                raise ValueError("resource_link content requires uri")
            return self
        if self.resource is None or any(value is not None for value in (self.text, self.data, self.uri)):
            raise ValueError("embedded_resource content requires resource")
        _assert_json_value(self.resource, path="resource")
        return self


class MCPDiscoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    profile_revision: str = Field(min_length=1)
    manifest_hash: str | None = None

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str) -> str:
        return _profile_id(value)

    @field_validator("manifest_hash")
    @classmethod
    def validate_optional_manifest_hash(cls, value: str | None) -> str | None:
        return None if value is None else _manifest_hash(value)


class MCPCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    request_id: str = Field(min_length=1)
    profile_id: str
    profile_revision: str = Field(min_length=1)
    manifest_hash: str
    tool_name: str
    arguments: dict[str, Any]

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str) -> str:
        return _profile_id(value)

    @field_validator("manifest_hash")
    @classmethod
    def validate_manifest_hash(cls, value: str) -> str:
        return _manifest_hash(value)

    @model_validator(mode="after")
    def validate_binding_and_arguments(self) -> MCPCallRequest:
        parse_namespaced_tool_name(self.tool_name, expected_profile_id=self.profile_id)
        _assert_json_value(self.arguments, path="arguments")
        return self


class MCPUsageRecordSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gateway_request_id: str = Field(min_length=1)
    attribution: MCPAttribution
    billing_units: int | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=Decimal("0"))

    @field_validator("cost_usd")
    @classmethod
    def validate_finite_cost(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("cost_usd must be finite")
        return value

    @model_validator(mode="after")
    def validate_attribution_values(self) -> MCPUsageRecordSummary:
        if self.attribution == "settled" and (self.billing_units is None or self.cost_usd is None):
            raise ValueError("settled attribution requires billing_units and cost_usd")
        if self.attribution == "explicit_zero" and (self.billing_units != 0 or self.cost_usd != Decimal("0")):
            raise ValueError("explicit_zero attribution requires zero billing_units and cost_usd")
        if self.attribution == "unavailable" and (self.billing_units is not None or self.cost_usd is not None):
            raise ValueError("unavailable attribution must not carry monetary values")
        return self


class MCPBindingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    profile_revision: str = Field(min_length=1)
    manifest_hash: str

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str) -> str:
        return _profile_id(value)

    @field_validator("manifest_hash")
    @classmethod
    def validate_manifest_hash(cls, value: str) -> str:
        return _manifest_hash(value)


class MCPDiscoverResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    profile_revision: str = Field(min_length=1)
    transport: MCPTransport
    protocol_version: str = Field(min_length=1)
    descriptors: tuple[MCPToolDescriptor, ...]
    unmatched_allowlist: tuple[str, ...] = ()
    manifest_hash: str
    freshness: MCPFreshness
    disposition: str = Field(min_length=1)

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str) -> str:
        return _profile_id(value)

    @field_validator("manifest_hash")
    @classmethod
    def validate_manifest_hash(cls, value: str) -> str:
        return _manifest_hash(value)

    @model_validator(mode="after")
    def validate_descriptor_namespace(self) -> MCPDiscoverResponse:
        expected_prefix = f"{self.profile_id}."
        names = [descriptor.name for descriptor in self.descriptors]
        if any(not name.startswith(expected_prefix) or not name[len(expected_prefix) :] for name in names):
            raise ValueError("descriptors must use the profile_id.tool_name namespaced form")
        if len(names) != len(set(names)):
            raise ValueError("duplicate descriptor names are not allowed")
        return self


class MCPCallResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result_type: MCPResultType
    content: tuple[MCPContent, ...]
    disposition: str = Field(min_length=1)
    binding: MCPBindingSummary
    transport: MCPTransport
    protocol_version: str = Field(min_length=1)
    attribution: MCPAttribution
    usage: MCPUsageRecordSummary

    @model_validator(mode="after")
    def validate_usage_attribution(self) -> MCPCallResponse:
        if self.attribution != self.usage.attribution:
            raise ValueError("response attribution must match usage attribution")
        return self


def namespace_tool_name(*, profile_id: str, tool_name: str) -> str:
    return f"{_profile_id(profile_id)}.{_tool_name(tool_name)}"


def parse_namespaced_tool_name(value: str, *, expected_profile_id: str | None = None) -> tuple[str, str]:
    value = _non_empty(value, field_name="tool_name")
    profile_id, separator, tool_name = value.partition(".")
    if not separator or not profile_id or not tool_name:
        raise ValueError("tool_name must be namespaced as profile_id.tool_name")
    profile_id = _profile_id(profile_id)
    tool_name = _tool_name(tool_name)
    if expected_profile_id is not None and profile_id != _profile_id(expected_profile_id):
        raise ValueError("tool_name profile_id does not match request profile_id")
    return profile_id, tool_name


def canonical_manifest_payload(response: MCPDiscoverResponse) -> dict[str, Any]:
    return {
        "profile_id": response.profile_id,
        "profile_revision": response.profile_revision,
        "transport": response.transport,
        "protocol_version": response.protocol_version,
        "descriptors": [
            descriptor.model_dump(mode="json", exclude_none=True)
            for descriptor in sorted(response.descriptors, key=lambda item: item.name)
        ],
        "unmatched_allowlist": sorted(response.unmatched_allowlist),
    }


def canonical_manifest_bytes(response: MCPDiscoverResponse) -> bytes:
    return json.dumps(
        canonical_manifest_payload(response),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_manifest_hash(response: MCPDiscoverResponse) -> str:
    return hashlib.sha256(canonical_manifest_bytes(response)).hexdigest()


__all__ = [
    "MCPAttribution",
    "MCPBindingSummary",
    "MCPCallRequest",
    "MCPCallResponse",
    "MCPContent",
    "MCPDiscoverRequest",
    "MCPDiscoverResponse",
    "MCPToolDescriptor",
    "MCPUsageRecordSummary",
    "canonical_manifest_bytes",
    "canonical_manifest_payload",
    "compute_manifest_hash",
    "namespace_tool_name",
    "parse_namespaced_tool_name",
]
