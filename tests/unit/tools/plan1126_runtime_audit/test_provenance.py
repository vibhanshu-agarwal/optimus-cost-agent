"""Fail-closed installed-artifact provenance tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.plan1126_runtime_audit.provenance import ExpectedArtifactIdentity, verify_running_artifact

_COMMIT = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"  # pragma: allowlist secret - Historical commit-identity pin in _COMMIT;
_EXPECTED = ExpectedArtifactIdentity(
    package_name="optimus-cost-agent", package_version="0.1.0", client_name="acpx", client_version="0.12.0"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _valid_manifest(tmp_path: Path, *, package_name: str = "optimus-cost-agent", client_name: str = "acpx") -> dict[str, object]:
    executable = tmp_path / "optimus-agent.exe"
    launcher = tmp_path / "launcher.cmd"
    client = tmp_path / "client.bin"
    executable.write_bytes(b"installed executable")
    launcher.write_bytes(b"@optimus-agent.exe\r\n")
    client.write_bytes(b"independent client")
    package_metadata = tmp_path / "package-metadata.json"
    embedded_commit = tmp_path / "embedded-commit.txt"
    build_manifest = tmp_path / "build-manifest.json"
    client_metadata = tmp_path / "client-metadata.json"
    environment_manifest = tmp_path / "environment-manifest.json"
    _json(package_metadata, {"schema_version": "plan-11-26-package-metadata-v1", "name": package_name, "version": "0.1.0"})
    embedded_commit.write_text(_COMMIT + "\n", encoding="ascii")
    _json(build_manifest, {
        "schema_version": "plan-11-26-build-manifest-v1", "source_commit": _COMMIT,
        "executable_sha256": _sha256(executable), "package_metadata_sha256": _sha256(package_metadata),
    })
    _json(client_metadata, {
        "schema_version": "plan-11-26-client-metadata-v1", "name": client_name, "version": "0.12.0",
        "artifact_path": str(client), "artifact_sha256": _sha256(client),
    })
    _json(environment_manifest, {
        "schema_version": "plan-11-26-environment-v1", "platform": "windows", "architecture": "x86_64",
        "python_version": "3.14.0", "runtime_id": "fixture-runtime",
    })
    return {
        "binding_commit": _COMMIT,
        "executable_path": str(executable), "executable_sha256": _sha256(executable),
        "package_metadata_path": str(package_metadata), "package_metadata_sha256": _sha256(package_metadata),
        "build_manifest_path": str(build_manifest), "build_manifest_sha256": _sha256(build_manifest),
        "embedded_commit_path": str(embedded_commit), "embedded_commit_sha256": _sha256(embedded_commit),
        "launcher_path": str(launcher), "launcher_sha256": _sha256(launcher),
        "client_metadata_path": str(client_metadata), "client_metadata_sha256": _sha256(client_metadata),
        "environment_manifest_path": str(environment_manifest), "environment_fingerprint": _sha256(environment_manifest),
    }


def test_running_artifact_provenance_matches_binding_commit_and_expected_identity(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    result = verify_running_artifact(manifest, binding_commit=_COMMIT, expected_identity=_EXPECTED)
    assert result.valid is True
    assert result.reasons == ()
    assert result.provenance is not None
    assert result.provenance["embedded_commit"] == _COMMIT
    assert result.provenance["package_name"] == "optimus-cost-agent"
    assert result.provenance["client_provenance"]["name"] == "acpx"
    assert result.provenance["environment_fingerprint"] == manifest["environment_fingerprint"]
    assert "git_sha" not in result.provenance


def test_running_artifact_provenance_rejects_manifest_asserted_identity_strings(tmp_path: Path) -> None:
    del tmp_path
    opaque = {
        "git_sha": _COMMIT, "embedded_commit": _COMMIT, "package_name": "optimus-cost-agent",
        "package_version": "0.1.0", "client_provenance": {"name": "acpx", "version": "0.12.0"},
        "environment_fingerprint": "b" * 64,
    }
    result = verify_running_artifact(opaque, binding_commit=_COMMIT, expected_identity=_EXPECTED)
    assert result.valid is False
    assert result.reasons == ("manifest_fields_incomplete",)


def test_running_artifact_provenance_rejects_independently_read_identity_mismatch(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path, package_name="fabricated-package", client_name="fabricated-client")
    result = verify_running_artifact(manifest, binding_commit=_COMMIT, expected_identity=_EXPECTED)
    assert result.valid is False
    assert set(result.reasons) >= {"package_identity_mismatch", "client_identity_mismatch"}


def test_running_artifact_provenance_rejects_build_commit_and_environment_tamper(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    Path(manifest["embedded_commit_path"]).write_text("1" * 40 + "\n", encoding="ascii")
    environment_path = Path(manifest["environment_manifest_path"])
    environment_path.write_text('{"secret":"must-not-be-read-as-environment-facts"}', encoding="utf-8")  # pragma: allowlist secret - Deliberately invalid environment-manifest marker written under tmp_path;
    manifest["embedded_commit_sha256"] = _sha256(Path(manifest["embedded_commit_path"]))
    manifest["environment_fingerprint"] = _sha256(environment_path)
    result = verify_running_artifact(manifest, binding_commit=_COMMIT, expected_identity=_EXPECTED)
    assert result.valid is False
    assert set(result.reasons) >= {"embedded_commit_mismatch", "environment_manifest_invalid"}
