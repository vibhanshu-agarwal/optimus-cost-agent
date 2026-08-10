"""Load and validate content-free live evidence manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import (
    EXPECTED_CLIENT_NAMES,
    MOCK_SERVICE_MARKERS,
    REQUIRED_AGENT_FIELDS,
    TOKEN_FIELD_NAMES,
)
from .errors import VerificationError


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise VerificationError("missing_manifest_field", f"manifest missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VerificationError("missing_manifest_field", "manifest is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise VerificationError("missing_manifest_field", "manifest root must be an object")
    return payload


def _walk_for_token_fields(node: Any, *, path: str = "$") -> str | None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_l = str(key).lower()
            if key_l in TOKEN_FIELD_NAMES:
                return f"{path}.{key}"
            found = _walk_for_token_fields(value, path=f"{path}.{key}")
            if found is not None:
                return found
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found = _walk_for_token_fields(item, path=f"{path}[{index}]")
            if found is not None:
                return found
    return None


def assert_not_scenario_shape(payload: dict[str, Any]) -> None:
    purpose = payload.get("purpose")
    if purpose == "scenario_shape_only" or payload.get("pass_forbidden_without_real_evidence") is True:
        raise VerificationError(
            "scenario_shape_insufficient",
            "scenario shape fixture cannot satisfy live verification",
        )


def validate_manifest(
    payload: dict[str, Any],
    *,
    expected_agent_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    assert_not_scenario_shape(payload)

    token_path = _walk_for_token_fields(payload)
    if token_path is not None:
        raise VerificationError("token_in_manifest", f"token field at {token_path}")

    agents = payload.get("agents")
    if not isinstance(agents, list) or not agents:
        raise VerificationError("missing_manifest_field", "agents[] required")

    dependency = payload.get("dependency_identities")
    if dependency is not None and not isinstance(dependency, dict):
        raise VerificationError("fabricated_dependency_identity", "dependency_identities must be an object")

    validated: list[dict[str, Any]] = []
    seen_agent_ids: set[str] = set()
    seen_principals: set[str] = set()
    seen_fingerprints: set[str] = set()
    client_names: set[str] = set()

    for index, raw in enumerate(agents):
        if not isinstance(raw, dict):
            raise VerificationError("missing_manifest_field", f"agents[{index}] must be an object")

        missing = sorted(field for field in REQUIRED_AGENT_FIELDS if not raw.get(field))
        if missing:
            if missing == ["process_identity"]:
                raise VerificationError(
                    "missing_process_identity",
                    f"agents[{index}] lacks process_identity",
                )
            if missing == ["client_name"] or missing == ["client_version"]:
                raise VerificationError(
                    "missing_client_identity",
                    f"agents[{index}] missing {missing}",
                )
            if missing == ["store_identity"]:
                raise VerificationError(
                    "missing_store_identity",
                    f"agents[{index}] missing store_identity",
                )
            raise VerificationError("missing_manifest_field", f"agents[{index}] missing {missing}")

        agent_id = str(raw["agent_id"])
        principal_id = str(raw["principal_id"])
        fingerprint = str(raw["credential_fingerprint"])
        client_name = str(raw["client_name"])

        if agent_id in seen_agent_ids:
            raise VerificationError("non_distinct_agents", f"duplicate agent_id={agent_id}")
        seen_agent_ids.add(agent_id)

        if principal_id in seen_principals:
            raise VerificationError("non_distinct_agents", f"duplicate principal_id={principal_id}")
        seen_principals.add(principal_id)

        if fingerprint in seen_fingerprints:
            raise VerificationError("duplicate_credentials", f"duplicate credential_fingerprint={fingerprint}")
        seen_fingerprints.add(fingerprint)

        client_names.add(client_name)

        status = str(raw.get("status", "")).lower()
        passed_flag = raw.get("passed")
        if status == "skipped" and passed_flag is True:
            raise VerificationError(
                "skipped_agent_marked_passed",
                f"agents[{index}] skipped but passed=true",
            )

        service_mode = str(raw.get("service_mode", "")).lower()
        service_identity = str(raw["service_identity"]).lower()
        if service_mode in MOCK_SERVICE_MARKERS or any(
            marker in service_identity for marker in MOCK_SERVICE_MARKERS
        ):
            if passed_flag is True or status == "passed":
                raise VerificationError(
                    "mocked_service_marked_passed",
                    f"agents[{index}] mocked service marked passed",
                )

        if isinstance(dependency, dict):
            expected_service = dependency.get("service")
            expected_store = dependency.get("store")
            if expected_service is not None and str(raw["service_identity"]) != str(expected_service):
                raise VerificationError(
                    "fabricated_dependency_identity",
                    f"agents[{index}] service_identity does not match dependency_identities.service",
                )
            if expected_store is not None and str(raw["store_identity"]) != str(expected_store):
                raise VerificationError(
                    "fabricated_dependency_identity",
                    f"agents[{index}] store_identity does not match dependency_identities.store",
                )

        validated.append(raw)

    if len(expected_agent_ids) != len(set(expected_agent_ids)):
        raise VerificationError("non_distinct_agents", "expected_agent_ids are not distinct")

    expected_set = set(expected_agent_ids)
    if seen_agent_ids != expected_set:
        # Incomplete or mismatched agent set is treated as non-distinct / incomplete evidence.
        if len(seen_agent_ids) != len(expected_set) or not seen_agent_ids.issubset(expected_set):
            raise VerificationError(
                "non_distinct_agents",
                f"manifest agents {sorted(seen_agent_ids)} != expected {sorted(expected_set)}",
            )

    if not EXPECTED_CLIENT_NAMES.issubset(client_names) and len(validated) >= 3:
        # Three-agent live evidence must name the real native clients; incomplete sets fail earlier.
        raise VerificationError(
            "missing_client_identity",
            f"client_names={sorted(client_names)} missing required native clients",
        )

    return validated
