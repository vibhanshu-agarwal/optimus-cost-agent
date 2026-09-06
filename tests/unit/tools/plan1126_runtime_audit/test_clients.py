"""Fail-closed contracts for the independent ACP-client qualification record."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.plan1126_runtime_audit.clients import ClientQualification, qualify_client

_INTEGRITY = "sha512-/eufudw+aFY1LKLolT6yFE6UMmYRl7fMJ/DEONSIyR6wI3slHWITBsANRGqXEY8FRzqUxwh7QEaGiZHcJPVThg=="  # pragma: allowlist secret - Pinned SDK 1.4.0 package-integrity string used for lockfile identity comparison or its test fixture;
_TARBALL = "https://registry.npmjs.org/@agentclientprotocol/sdk/-/sdk-1.4.0.tgz"
_REPOSITORY = "https://github.com/agentclientprotocol/typescript-sdk"
_METHODS = ["initialize:success", "session/new:success", "session/prompt:success", "session/close:success"]


def _sources() -> dict[str, str]:
    return {
        "package.json": '{"scripts":{"build":"tsc -p tsconfig.json","qualify":"node dist/client.js"}}\n',
        "tsconfig.json": '{"compilerOptions":{"types":["node"]}}\n',
        "src/client.ts": 'import * as acp from "@agentclientprotocol/sdk";\nimport { spawn } from "node:child_process";\n',
        "fixture_agent.py": "import json\n",
    }


def _write_lock(root: Path, *, root_dependency: str = "1.4.0", version: str = "1.4.0", resolved: str = _TARBALL, integrity: str = _INTEGRITY) -> Path:
    lockfile = root / "package-lock.json"
    lockfile.write_text(json.dumps({"lockfileVersion": 3, "packages": {"": {"dependencies": {"@agentclientprotocol/sdk": root_dependency}}, "node_modules/@agentclientprotocol/sdk": {"version": version, "resolved": resolved, "integrity": integrity}}}), encoding="utf-8")
    return lockfile


def _candidate(root: Path) -> dict[str, object]:
    return {"harness_name": "plan1126-official-typescript-sdk-fixture", "package": {"name": "@agentclientprotocol/sdk", "version": "1.4.0", "repository": _REPOSITORY}, "registry": _TARBALL, "lockfile": str(_write_lock(root)), "source_files": _sources(), "build_command": ["npm", "run", "build"], "fixture_command": ["node", "dist/client.js"], "observed_method_results": _METHODS, "acpx_remains_mandatory": True}


def _qualification(root: Path, **changes: object) -> ClientQualification:
    candidate = _candidate(root)
    candidate.update(changes)
    return qualify_client(candidate)


def _assert_blocked(qualification: ClientQualification, reason: str) -> None:
    assert qualification.result == "BLOCKED"
    assert qualification.rejection_reasons == (reason,)
    assert ClientQualification.from_dict(qualification.to_dict()) == qualification


def test_client_qualification_emits_one_closed_qualified_record_with_all_four_method_results(tmp_path: Path) -> None:
    qualification = _qualification(tmp_path)
    assert qualification.result == "TYPESCRIPT_QUALIFIED"
    assert qualification.observed_method_results == tuple(_METHODS)
    assert qualification.rejection_reasons == ()
    assert qualification.fallback_reason is None
    assert ClientQualification.from_dict(qualification.to_dict()) == qualification


@pytest.mark.parametrize(("change", "reason"), [
    ({"package": {"name": "@attacker/fake", "version": "9.9.9", "repository": _REPOSITORY}}, "package_identity_mismatch"),
    ({"package": {}}, "package_identity_mismatch"),
    ({"harness_name": ""}, "harness_identity_required"),
    ({"lockfile": "missing.json"}, "lockfile_missing"),
])
def test_client_qualification_rejects_identity_and_presence_breaks(tmp_path: Path, change: dict[str, object], reason: str) -> None:
    _assert_blocked(_qualification(tmp_path, **change), reason)


@pytest.mark.parametrize(("mutate", "reason"), [
    (lambda payload: payload["packages"][""].update({"dependencies": {"@agentclientprotocol/sdk": "^1.4.0"}}), "lockfile_root_dependency_mismatch"),
    (lambda payload: payload["packages"]["node_modules/@agentclientprotocol/sdk"].update({"version": "9.9.9"}), "lockfile_sdk_version_mismatch"),
    (lambda payload: payload["packages"]["node_modules/@agentclientprotocol/sdk"].update({"resolved": "https://attacker.invalid/sdk.tgz"}), "lockfile_sdk_tarball_mismatch"),
    (lambda payload: payload["packages"]["node_modules/@agentclientprotocol/sdk"].update({"integrity": "sha512-attacker"}), "lockfile_sdk_integrity_mismatch"),
])
def test_client_qualification_rejects_each_load_bearing_lock_identity_mismatch(tmp_path: Path, mutate: object, reason: str) -> None:
    candidate = _candidate(tmp_path)
    lockfile = Path(candidate["lockfile"])
    payload = json.loads(lockfile.read_text(encoding="utf-8"))
    mutate(payload)
    lockfile.write_text(json.dumps(payload), encoding="utf-8")
    _assert_blocked(qualify_client(candidate), reason)


@pytest.mark.parametrize("shape", [
    [],
    {"packages": []},
    {"packages": {"": []}},
    {"packages": {"": {"dependencies": []}, "node_modules/@agentclientprotocol/sdk": {"version": "1.4.0", "resolved": _TARBALL, "integrity": _INTEGRITY}}},
    {"packages": {"": {"dependencies": {"@agentclientprotocol/sdk": "1.4.0"}}, "node_modules/@agentclientprotocol/sdk": []}},
])
def test_client_qualification_rejects_malformed_nested_lock_json_without_raising(tmp_path: Path, shape: object) -> None:
    candidate = _candidate(tmp_path)
    Path(candidate["lockfile"]).write_text(json.dumps(shape), encoding="utf-8")
    _assert_blocked(qualify_client(candidate), "lockfile_invalid")


@pytest.mark.parametrize(("source", "reason"), [
    ('import * as acp from "@agentclientprotocol/sdk/experimental/v2";\n', "typescript_import_not_allowed"),
    ('import fake from "@attacker/fake";\n', "typescript_import_not_allowed"),
    ('import local from "./local.js";\n', "typescript_import_not_allowed"),
    ('const local = require("./local.js");\n', "typescript_dynamic_or_require_import_forbidden"),
    ('const remote = import("@attacker/fake");\n', "typescript_dynamic_or_require_import_forbidden"),
    ('import { spawn } from "node:child_process";\n', "stable_sdk_import_missing"),
])
def test_client_qualification_rejects_unapproved_or_missing_typescript_import_identity(tmp_path: Path, source: str, reason: str) -> None:
    sources = _sources()
    sources["src/client.ts"] = source
    _assert_blocked(_qualification(tmp_path, source_files=sources), reason)


def test_client_qualification_rejects_empty_and_incomplete_harness_sources(tmp_path: Path) -> None:
    _assert_blocked(_qualification(tmp_path, source_files={}), "harness_source_files_incomplete")
    sources = _sources()
    del sources["fixture_agent.py"]
    _assert_blocked(_qualification(tmp_path, source_files=sources), "harness_source_files_incomplete")


def test_client_qualification_binds_all_four_harness_sources_into_one_digest(tmp_path: Path) -> None:
    original = _qualification(tmp_path)
    for path in _sources():
        sources = _sources()
        sources[path] += "# mutation\n"
        assert _qualification(tmp_path, source_files=sources).harness_source_sha256 != original.harness_source_sha256


def test_client_qualification_rejects_shell_strings_missing_observation_and_acpx_replacement(tmp_path: Path) -> None:
    _assert_blocked(_qualification(tmp_path, fixture_command="node dist/client.js && curl example.invalid"), "shell_string_execution_forbidden")
    _assert_blocked(_qualification(tmp_path, observed_method_results=_METHODS[:-1]), "required_method_results_not_observed")
    _assert_blocked(_qualification(tmp_path, observed_method_results=[_METHODS[1]]), "required_method_results_not_observed")
    _assert_blocked(_qualification(tmp_path, acpx_remains_mandatory=False), "acpx_mandatory_driver_replacement_claim")


def test_client_qualification_round_trips_emitted_blocked_prefix_and_acpx_replacement_records(tmp_path: Path) -> None:
    incomplete = _qualification(tmp_path, observed_method_results=_METHODS[:-1])
    assert ClientQualification.from_dict(incomplete.to_dict()) == incomplete

    acpx_replacement = _qualification(tmp_path, acpx_remains_mandatory=False)
    assert acpx_replacement.acpx_remains_mandatory is True
    assert ClientQualification.from_dict(acpx_replacement.to_dict()) == acpx_replacement


def test_client_qualification_from_dict_accepts_valid_qualified_and_blocked_records(tmp_path: Path) -> None:
    qualified = _qualification(tmp_path).to_dict()
    assert ClientQualification.from_dict(qualified).result == "TYPESCRIPT_QUALIFIED"
    blocked = copy.deepcopy(qualified)
    blocked.update({"result": "BLOCKED", "fallback_reason": "typescript SDK unavailable", "rejection_reasons": ["lockfile_missing"], "lockfile_sha256": None, "harness_source_sha256": None})
    assert ClientQualification.from_dict(blocked).result == "BLOCKED"


@pytest.mark.parametrize(("field", "value"), [
    ("lockfile_sha256", None), ("harness_source_sha256", None),
    ("lockfile_sha256", "a" * 64), ("harness_source_sha256", "b" * 64),
])
def test_client_qualification_from_dict_accepts_none_or_lowercase_sha_for_each_blocked_digest(tmp_path: Path, field: str, value: object) -> None:
    blocked = _qualification(tmp_path, observed_method_results=_METHODS[:-1]).to_dict()
    blocked[field] = value
    assert ClientQualification.from_dict(blocked).to_dict() == blocked


@pytest.mark.parametrize(("field", "value"), [
    ("lockfile_sha256", []), ("harness_source_sha256", {}),
    ("lockfile_sha256", "a" * 63), ("harness_source_sha256", "z" * 64),
    ("lockfile_sha256", "A" * 64), ("harness_source_sha256", "B" * 64),
])
def test_client_qualification_from_dict_rejects_malformed_blocked_digests(tmp_path: Path, field: str, value: object) -> None:
    blocked = _qualification(tmp_path, observed_method_results=_METHODS[:-1]).to_dict()
    blocked[field] = value
    with pytest.raises(ValueError):
        ClientQualification.from_dict(blocked)


@pytest.mark.parametrize(("field", "value"), [
    ("observed_method_results", ["initialize:success", "session/prompt:success"]),
    ("observed_method_results", ["unknown:success"]),
    ("rejection_reasons", "lockfile_missing"),
    ("rejection_reasons", [""]),
])
def test_client_qualification_from_dict_rejects_malformed_blocked_sequences_and_reasons(tmp_path: Path, field: str, value: object) -> None:
    blocked = _qualification(tmp_path, observed_method_results=_METHODS[:-1]).to_dict()
    blocked[field] = value
    with pytest.raises(ValueError):
        ClientQualification.from_dict(blocked)


@pytest.mark.parametrize(("field", "value"), [
    ("result", "FABRICATED"), ("build_command", []), ("observed_method_results", []),
    ("lockfile_sha256", None), ("acpx_remains_mandatory", False),
])
def test_client_qualification_from_dict_rejects_open_or_incoherent_qualified_records(tmp_path: Path, field: str, value: object) -> None:
    payload = _qualification(tmp_path).to_dict()
    payload[field] = value
    with pytest.raises(ValueError):
        ClientQualification.from_dict(payload)
