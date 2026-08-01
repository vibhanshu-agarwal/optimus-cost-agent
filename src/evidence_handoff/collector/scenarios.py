"""Strict scenario parsing, binding resolution, and digests.

Stdlib-only. Scenario files are untrusted declarative data.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import (
    AdapterParameter,
    AdapterSpec,
    BindingKind,
    RequiredBinding,
    Scenario,
    adapter_parameter_to_canonical_dict,
    scenario_to_canonical_dict,
)

SCENARIO_SCHEMA_V1 = "evidence-scenario-v1"

_SCENARIO_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_FEATURE_ID_RE = re.compile(
    r"(?<![A-Z0-9-])(?:[A-Z][A-Z0-9]*-)*FEAT-[A-Z0-9]+(?:-[A-Z0-9]+)*(?![A-Z0-9-])"
)
_PLAN_NUMBER_RE = re.compile(r"\bPlan [0-9]|\bplan-[0-9]", re.IGNORECASE)
# Forbid shell/env expansion forms in untrusted scenario strings (portable, host-independent).
_ENV_OR_SHELL_RE = re.compile(
    r"""
    \$\{          # ${VAR}
    | \$\(        # $(cmd)
    | `           # backtick command substitution
    | \$[A-Za-z_][A-Za-z0-9_]*   # bare $VAR
    | %[A-Za-z_][A-Za-z0-9_]*%   # Windows %VAR%
    """,
    re.VERBOSE,
)
_ADAPTER_CAPABILITY_BAN_RE = re.compile("prompt" + "[_-]?" + "inject", re.IGNORECASE)

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema",
        "scenario_id",
        "required_bindings",
        "client",
        "fixture",
        "preconditions",
        "collection",
        "detection",
        "required_evidence",
    }
)
_BINDING_KEYS = frozenset({"name", "kind", "required", "min_length", "max_length"})
_ADAPTER_KEYS = frozenset({"adapter_id", "contract_version", "parameters"})
_PARAMETER_KEYS = frozenset({"name", "kind", "value"})
_FORBIDDEN_KEYS = frozenset(
    {
        "import",
        "import_path",
        "module",
        "class",
        "expression",
        "eval",
        "template",
        "shell",
        "command",
        "hook",
        "executable",
        "env",
        "environment",
        "argv",
        "args",
        "entry_point",
        "package",
    }
)


def load_scenario(path: Path) -> Scenario:
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".toml":
        data = _load_toml(raw)
    elif suffix == ".json":
        data = _load_json(raw)
    else:
        raise ValueError("unknown_scenario_format")
    return _parse_scenario(data)


def resolve_bindings(
    scenario: Scenario,
    supplied: Sequence[str],
) -> tuple[AdapterParameter, ...]:
    parsed: dict[str, str] = {}
    for item in supplied:
        if "=" not in item:
            raise ValueError("invalid_binding")
        name, value = item.split("=", 1)
        if not name:
            raise ValueError("invalid_binding")
        if name in parsed:
            raise ValueError("duplicate_binding")
        parsed[name] = value

    required_names = {binding.name for binding in scenario.required_bindings}
    unknown = sorted(set(parsed) - required_names)
    if unknown:
        raise ValueError("unknown_binding")

    resolved: list[AdapterParameter] = []
    for binding in scenario.required_bindings:
        if binding.name not in parsed:
            if binding.required:
                raise ValueError("missing_binding")
            continue
        value = parsed[binding.name]
        if binding.name == "model" and value == "":
            raise ValueError("empty_binding")
        resolved.append(_coerce_binding_value(binding, value))
    return tuple(resolved)


def scenario_sha256(
    scenario: Scenario,
    bindings: Sequence[AdapterParameter],
) -> str:
    payload = {
        "scenario": scenario_to_canonical_dict(scenario),
        "bindings": [adapter_parameter_to_canonical_dict(item) for item in bindings],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load_toml(raw: bytes) -> dict[str, Any]:
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        message = str(exc).lower()
        if "duplicate" in message:
            raise ValueError("duplicate_key") from exc
        raise ValueError("invalid_toml") from exc
    if not isinstance(data, dict):
        raise ValueError("invalid_toml")
    return data


def _load_json(raw: bytes) -> dict[str, Any]:
    def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc
    if not isinstance(data, dict):
        raise ValueError("invalid_json")
    return data


def _reject_forbidden_keys(mapping: Mapping[str, Any]) -> None:
    for key in mapping:
        if key in _FORBIDDEN_KEYS:
            raise ValueError("non_executable_input")


def _require_keys(mapping: Mapping[str, Any], allowed: frozenset[str]) -> None:
    _reject_forbidden_keys(mapping)
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        # Prefer the stronger non-executable signal when a forbidden construct slipped
        # past the allowlist under an alternate spelling already covered above.
        raise ValueError("unknown_field")


def _parse_scenario(data: Mapping[str, Any]) -> Scenario:
    _require_keys(data, _TOP_LEVEL_KEYS)
    schema = data.get("schema")
    if schema != SCENARIO_SCHEMA_V1:
        raise ValueError("unknown_schema")
    scenario_id = data.get("scenario_id")
    if not isinstance(scenario_id, str) or not _is_safe_scenario_id(scenario_id):
        raise ValueError("unsafe_scenario_id")

    required_bindings = tuple(
        _parse_required_binding(item) for item in _require_list(data, "required_bindings")
    )
    client = _parse_adapter(data.get("client"))
    fixture = _parse_adapter(data.get("fixture"))
    preconditions = tuple(
        _parse_adapter(item) for item in _require_list(data, "preconditions")
    )
    collection = tuple(
        _parse_adapter(item) for item in _require_list(data, "collection")
    )
    detection = tuple(
        _parse_adapter(item) for item in _require_list(data, "detection")
    )
    required_evidence = tuple(_require_list(data, "required_evidence"))
    for item in required_evidence:
        if not isinstance(item, str) or not item:
            raise ValueError("invalid_required_evidence")

    return Scenario(
        schema=schema,
        scenario_id=scenario_id,
        required_bindings=required_bindings,
        client=client,
        fixture=fixture,
        preconditions=preconditions,
        collection=collection,
        detection=detection,
        required_evidence=required_evidence,
    )


def _is_safe_scenario_id(scenario_id: str) -> bool:
    if not scenario_id or not _SCENARIO_ID_RE.fullmatch(scenario_id):
        return False
    if _FEATURE_ID_RE.search(scenario_id) or _PLAN_NUMBER_RE.search(scenario_id):
        return False
    if "/" in scenario_id or "\\" in scenario_id or ".." in scenario_id:
        return False
    return True


def _require_list(data: Mapping[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if value is None:
        raise ValueError("unknown_field")
    if not isinstance(value, list):
        raise ValueError("ambiguous_type")
    return value


def _parse_required_binding(raw: Any) -> RequiredBinding:
    if not isinstance(raw, Mapping):
        raise ValueError("ambiguous_type")
    _require_keys(raw, _BINDING_KEYS)
    name = raw.get("name")
    kind_raw = raw.get("kind")
    required = raw.get("required")
    if not isinstance(name, str) or not name:
        raise ValueError("invalid_binding")
    if not isinstance(kind_raw, str):
        raise ValueError("ambiguous_type")
    try:
        kind = BindingKind(kind_raw)
    except ValueError as exc:
        raise ValueError("invalid_binding") from exc
    if not isinstance(required, bool):
        raise ValueError("ambiguous_type")
    min_length = raw.get("min_length")
    max_length = raw.get("max_length")
    if min_length is not None and not isinstance(min_length, int):
        raise ValueError("ambiguous_type")
    if max_length is not None and not isinstance(max_length, int):
        raise ValueError("ambiguous_type")
    return RequiredBinding(
        name=name,
        kind=kind,
        required=required,
        min_length=min_length,
        max_length=max_length,
    )


def _parse_adapter(raw: Any) -> AdapterSpec:
    if not isinstance(raw, Mapping):
        raise ValueError("ambiguous_type")
    _require_keys(raw, _ADAPTER_KEYS)
    adapter_id = raw.get("adapter_id")
    contract_version = raw.get("contract_version")
    if not isinstance(adapter_id, str) or not adapter_id:
        raise ValueError("invalid_adapter")
    if not isinstance(contract_version, str) or not contract_version:
        raise ValueError("invalid_adapter")
    _reject_executable_string(adapter_id)
    _reject_executable_string(contract_version)
    if _ADAPTER_CAPABILITY_BAN_RE.search(adapter_id):
        raise ValueError("non_executable_input")
    parameters_raw = raw.get("parameters", [])
    if not isinstance(parameters_raw, list):
        raise ValueError("ambiguous_type")
    parameters = tuple(_parse_parameter(item) for item in parameters_raw)
    return AdapterSpec(
        adapter_id=adapter_id,
        contract_version=contract_version,
        parameters=parameters,
    )


def _parse_parameter(raw: Any) -> AdapterParameter:
    if not isinstance(raw, Mapping):
        raise ValueError("ambiguous_type")
    _require_keys(raw, _PARAMETER_KEYS)
    name = raw.get("name")
    kind_raw = raw.get("kind")
    value = raw.get("value")
    if not isinstance(name, str) or not name:
        raise ValueError("invalid_binding")
    if not isinstance(kind_raw, str):
        raise ValueError("ambiguous_type")
    try:
        kind = BindingKind(kind_raw)
    except ValueError as exc:
        raise ValueError("invalid_binding") from exc
    coerced = _coerce_parameter_value(kind, value)
    if isinstance(coerced, str):
        _reject_executable_string(coerced)
    return AdapterParameter(name=name, kind=kind, value=coerced)


def _coerce_parameter_value(kind: BindingKind, value: Any) -> str | int | bool:
    if kind is BindingKind.STRING:
        if not isinstance(value, str):
            raise ValueError("ambiguous_type")
        return value
    if kind is BindingKind.INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("ambiguous_type")
        return value
    if kind is BindingKind.BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError("ambiguous_type")
        return value
    if kind is BindingKind.ABSOLUTE_PATH:
        if not isinstance(value, str):
            raise ValueError("ambiguous_type")
        if not _is_portable_absolute_path(value):
            raise ValueError("invalid_binding")
        return value
    raise ValueError("invalid_binding")


def _coerce_binding_value(binding: RequiredBinding, raw: str) -> AdapterParameter:
    kind = binding.kind
    if kind is BindingKind.STRING:
        if binding.min_length is not None and len(raw) < binding.min_length:
            raise ValueError("invalid_bounds")
        if binding.max_length is not None and len(raw) > binding.max_length:
            raise ValueError("invalid_bounds")
        if raw == "" and binding.required:
            raise ValueError("empty_binding")
        _reject_executable_string(raw)
        return AdapterParameter(name=binding.name, kind=kind, value=raw)
    if kind is BindingKind.INTEGER:
        if raw.startswith("-"):
            body = raw[1:]
        else:
            body = raw
        if not body.isdigit():
            raise ValueError("invalid_binding")
        return AdapterParameter(name=binding.name, kind=kind, value=int(raw))
    if kind is BindingKind.BOOLEAN:
        lowered = raw.lower()
        if lowered == "true":
            return AdapterParameter(name=binding.name, kind=kind, value=True)
        if lowered == "false":
            return AdapterParameter(name=binding.name, kind=kind, value=False)
        raise ValueError("ambiguous_type")
    if kind is BindingKind.ABSOLUTE_PATH:
        if not _is_portable_absolute_path(raw):
            raise ValueError("invalid_binding")
        _reject_executable_string(raw)
        return AdapterParameter(name=binding.name, kind=kind, value=raw)
    raise ValueError("invalid_binding")


def _is_portable_absolute_path(value: str) -> bool:
    """Host-independent absolute-path syntax for portable scenario contracts.

    Accepts POSIX absolute paths, Windows drive-absolute paths, and UNC paths.
    Does not consult pathlib/os so accept/reject is identical on every host.
    """
    if not value or "\x00" in value:
        return False
    if value.startswith("/"):
        return True
    if value.startswith("\\\\"):
        return True
    if len(value) >= 3 and value[0].isalpha() and value[1] == ":" and value[2] in {"/", "\\"}:
        return True
    return False


def _reject_executable_string(value: str) -> None:
    if _ENV_OR_SHELL_RE.search(value):
        raise ValueError("non_executable_input")
    if "\n" in value or "\r" in value:
        raise ValueError("non_executable_input")
