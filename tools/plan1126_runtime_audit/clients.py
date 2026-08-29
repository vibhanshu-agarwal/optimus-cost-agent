"""Fail-closed qualification records for independent ACP comparison clients."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_SDK = "@agentclientprotocol/sdk"
_VERSION = "1.4.0"
_TARBALL = "https://registry.npmjs.org/@agentclientprotocol/sdk/-/sdk-1.4.0.tgz"
_INTEGRITY = "sha512-/eufudw+aFY1LKLolT6yFE6UMmYRl7fMJ/DEONSIyR6wI3slHWITBsANRGqXEY8FRzqUxwh7QEaGiZHcJPVThg=="
_REPOSITORY = "https://github.com/agentclientprotocol/typescript-sdk"
_SOURCES = {"package.json", "tsconfig.json", "src/client.ts", "fixture_agent.py"}
_METHODS = ("initialize:success", "session/new:success", "session/prompt:success", "session/close:success")
_OUTCOMES = {"TYPESCRIPT_QUALIFIED", "JAVA_FALLBACK_QUALIFIED", "CONFORMANCE_HARNESS_QUALIFIED", "BLOCKED"}
_UNAVAILABLE = "UNAVAILABLE"
_IMPORT = re.compile(r"(?:import|export)\s+(?:[^\"']*?\s+from\s+)?[\"']([^\"']+)[\"']")


@dataclass(frozen=True, slots=True)
class ClientQualification:
    harness_name: str
    package_name: str
    package_version: str
    registry: str
    repository: str
    lockfile_sha256: str | None
    harness_source_sha256: str | None
    build_command: tuple[str, ...]
    fixture_command: tuple[str, ...]
    observed_method_results: tuple[str, ...]
    result: str
    fallback_reason: str | None
    rejection_reasons: tuple[str, ...]
    acpx_remains_mandatory: bool

    def to_dict(self) -> dict[str, object]:
        return {"harness_name": self.harness_name, "package_name": self.package_name, "package_version": self.package_version, "registry": self.registry, "repository": self.repository, "lockfile_sha256": self.lockfile_sha256, "harness_source_sha256": self.harness_source_sha256, "build_command": list(self.build_command), "fixture_command": list(self.fixture_command), "observed_method_results": list(self.observed_method_results), "result": self.result, "fallback_reason": self.fallback_reason, "rejection_reasons": list(self.rejection_reasons), "acpx_remains_mandatory": self.acpx_remains_mandatory}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ClientQualification:
        fields = set(cls.__dataclass_fields__)
        if set(payload) != fields:
            raise ValueError("client qualification fields do not match the canonical schema")
        commands = (payload["build_command"], payload["fixture_command"])
        if any(not isinstance(item, list) or not item or not all(isinstance(arg, str) and arg for arg in item) for item in commands):
            raise ValueError("client qualification commands must be non-empty argv arrays")
        if payload["result"] not in _OUTCOMES:
            raise ValueError("client qualification result is not closed")
        if payload["acpx_remains_mandatory"] is not True:
            raise ValueError("client qualification must preserve acpx authority")
        strings = ("harness_name", "package_name", "package_version", "registry", "repository")
        if any(not isinstance(payload[name], str) or not payload[name] for name in strings):
            raise ValueError("client qualification identity is invalid")
        qualified = payload["result"] != "BLOCKED"
        methods = payload["observed_method_results"]
        if not isinstance(methods, list) or (
            qualified and methods != list(_METHODS)
        ) or (
            not qualified and tuple(methods) != _METHODS[: len(methods)]
        ):
            raise ValueError("client qualification method results are not an allowed ordered sequence")
        rejections = payload["rejection_reasons"]
        if not isinstance(rejections, list) or any(
            not isinstance(reason, str) or not reason for reason in rejections
        ):
            raise ValueError("client qualification rejection reasons are invalid")
        digests = (payload["lockfile_sha256"], payload["harness_source_sha256"])
        if any(
            value is not None and (not isinstance(value, str) or not _sha(value))
            for value in digests
        ):
            raise ValueError("client qualification digests are invalid")
        if qualified and (payload["fallback_reason"] is not None or rejections or any(not isinstance(value, str) or not _sha(value) for value in digests)):
            raise ValueError("qualified client record is incoherent")
        if not qualified and (not isinstance(payload["fallback_reason"], str) or not payload["fallback_reason"] or not rejections):
            raise ValueError("blocked client record requires fallback and rejection reasons")
        return cls(payload["harness_name"], payload["package_name"], payload["package_version"], payload["registry"], payload["repository"], payload["lockfile_sha256"], payload["harness_source_sha256"], tuple(payload["build_command"]), tuple(payload["fixture_command"]), tuple(payload["observed_method_results"]), payload["result"], payload["fallback_reason"], tuple(payload["rejection_reasons"]), True)


def _sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _command(value: object) -> tuple[str, ...] | None:
    return tuple(value) if isinstance(value, (list, tuple)) and value and all(isinstance(arg, str) and arg for arg in value) else None


def _identity(value: object) -> str:
    return value if isinstance(value, str) and value else _UNAVAILABLE


def _observed_prefix(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    sequence = tuple(value)
    if sequence != _METHODS[: len(sequence)]:
        return ()
    return sequence


def _blocked(candidate: Mapping[str, object], reason: str) -> ClientQualification:
    package = candidate.get("package") if isinstance(candidate.get("package"), Mapping) else {}
    return ClientQualification(_identity(candidate.get("harness_name")), _identity(package.get("name")), _identity(package.get("version")), _identity(candidate.get("registry")), _identity(package.get("repository")), None, None, _command(candidate.get("build_command")) or ("not-observed",), _command(candidate.get("fixture_command")) or ("not-observed",), _observed_prefix(candidate.get("observed_method_results")), "BLOCKED", "candidate rejected", (reason,), True)


def _lock_reason(path: Path) -> str | None:
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
        packages = lock["packages"]
        root = packages[""]
        sdk = packages[f"node_modules/{_SDK}"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return "lockfile_invalid"
    if not all(isinstance(value, Mapping) for value in (lock, packages, root, sdk)):
        return "lockfile_invalid"
    dependencies = root.get("dependencies")
    if not isinstance(dependencies, Mapping):
        return "lockfile_invalid"
    if dependencies.get(_SDK) != _VERSION:
        return "lockfile_root_dependency_mismatch"
    if sdk.get("version") != _VERSION:
        return "lockfile_sdk_version_mismatch"
    if sdk.get("resolved") != _TARBALL:
        return "lockfile_sdk_tarball_mismatch"
    if sdk.get("integrity") != _INTEGRITY:
        return "lockfile_sdk_integrity_mismatch"
    return None


def _source_reason(sources: Mapping[str, object]) -> str | None:
    if set(sources) != _SOURCES or any(
        not isinstance(sources[path], str) or not sources[path] for path in _SOURCES
    ):
        return "harness_source_files_incomplete"
    client = sources["src/client.ts"]
    if re.search(r"\b(?:require|import)\s*\(", client):
        return "typescript_dynamic_or_require_import_forbidden"
    specs = _IMPORT.findall(client)
    if any(spec != _SDK and not spec.startswith("node:") for spec in specs):
        return "typescript_import_not_allowed"
    if _SDK not in specs:
        return "stable_sdk_import_missing"
    return None


def _source_digest(sources: Mapping[str, object]) -> str:
    digest = hashlib.sha256()
    for path in sorted(_SOURCES):
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(str(sources[path]).encode())
    return digest.hexdigest()


def qualify_client(candidate: Mapping[str, object]) -> ClientQualification:
    package = candidate.get("package")
    if (
        not isinstance(package, Mapping)
        or package.get("name") != _SDK
        or package.get("version") != _VERSION
    ):
        return _blocked(candidate, "package_identity_mismatch")
    if not isinstance(candidate.get("harness_name"), str) or not candidate["harness_name"]:
        return _blocked(candidate, "harness_identity_required")
    if package.get("repository") != _REPOSITORY:
        return _blocked(candidate, "package_repository_identity_required")
    if candidate.get("registry") != _TARBALL:
        return _blocked(candidate, "package_registry_identity_required")
    path = Path(candidate["lockfile"]) if isinstance(candidate.get("lockfile"), str) else None
    if path is None or not path.is_file():
        return _blocked(candidate, "lockfile_missing")
    if reason := _lock_reason(path):
        return _blocked(candidate, reason)
    sources = candidate.get("source_files")
    if not isinstance(sources, Mapping):
        return _blocked(candidate, "harness_source_files_incomplete")
    if reason := _source_reason(sources):
        return _blocked(candidate, reason)
    build, fixture = _command(candidate.get("build_command")), _command(candidate.get("fixture_command"))
    if build is None or fixture is None:
        return _blocked(candidate, "shell_string_execution_forbidden")
    if candidate.get("observed_method_results") != list(_METHODS):
        return _blocked(candidate, "required_method_results_not_observed")
    if candidate.get("acpx_remains_mandatory") is not True:
        return _blocked(candidate, "acpx_mandatory_driver_replacement_claim")
    return ClientQualification(candidate["harness_name"], _SDK, _VERSION, _TARBALL, _REPOSITORY, hashlib.sha256(path.read_bytes()).hexdigest(), _source_digest(sources), build, fixture, _METHODS, "TYPESCRIPT_QUALIFIED", None, (), True)
