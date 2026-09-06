"""External running-artifact provenance verification without checkout inference."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_MANIFEST_FIELDS = {
    "binding_commit", "executable_path", "executable_sha256", "package_metadata_path", "package_metadata_sha256",
    "build_manifest_path", "build_manifest_sha256", "embedded_commit_path", "embedded_commit_sha256",
    "launcher_path", "launcher_sha256", "client_metadata_path", "client_metadata_sha256",
    "environment_manifest_path", "environment_fingerprint",
}


@dataclass(frozen=True, slots=True)
class ExpectedArtifactIdentity:
    package_name: str
    package_version: str
    client_name: str
    client_version: str


@dataclass(frozen=True, slots=True)
class ProvenanceResult:
    valid: bool
    reasons: tuple[str, ...]
    provenance: Mapping[str, Any] | None


def _is_hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(character in "0123456789abcdef" for character in value)


def _file_sha256(path_value: object) -> str | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    path = Path(path_value)
    if not path.is_file() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path_value: object) -> Mapping[str, Any] | None:
    if not isinstance(path_value, str):
        return None
    try:
        payload = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def verify_running_artifact(
    manifest: Mapping[str, Any], *, binding_commit: str, expected_identity: ExpectedArtifactIdentity
) -> ProvenanceResult:
    """Derive identity from digest-bound metadata and compare it with command-owned expectations."""

    if set(manifest) != _MANIFEST_FIELDS:
        return ProvenanceResult(False, ("manifest_fields_incomplete",), None)
    reasons: list[str] = []
    if not _is_hex(binding_commit, 40):
        reasons.append("expected_binding_commit_invalid")
    if manifest["binding_commit"] != binding_commit:
        reasons.append("binding_commit_mismatch")
    actual_digests: dict[str, str | None] = {}
    for label, path_field, digest_field in (
        ("executable", "executable_path", "executable_sha256"),
        ("package_metadata", "package_metadata_path", "package_metadata_sha256"),
        ("build_manifest", "build_manifest_path", "build_manifest_sha256"),
        ("embedded_commit", "embedded_commit_path", "embedded_commit_sha256"),
        ("launcher", "launcher_path", "launcher_sha256"),
        ("client_metadata", "client_metadata_path", "client_metadata_sha256"),
        ("environment_manifest", "environment_manifest_path", "environment_fingerprint"),
    ):
        actual = _file_sha256(manifest[path_field])
        actual_digests[label] = actual
        if actual is None:
            reasons.append(f"{label}_unavailable")
        elif actual != manifest[digest_field]:
            reasons.append(f"{label}_digest_mismatch")

    package = _read_json(manifest["package_metadata_path"])
    if package is None or set(package) != {"schema_version", "name", "version"} or package.get("schema_version") != "plan-11-26-package-metadata-v1":
        reasons.append("package_metadata_invalid")
    elif (package.get("name"), package.get("version")) != (expected_identity.package_name, expected_identity.package_version):
        reasons.append("package_identity_mismatch")

    build = _read_json(manifest["build_manifest_path"])
    if build is None or set(build) != {"schema_version", "source_commit", "executable_sha256", "package_metadata_sha256"} or build.get("schema_version") != "plan-11-26-build-manifest-v1":
        reasons.append("build_manifest_invalid")
    else:
        if build.get("source_commit") != binding_commit:
            reasons.append("build_commit_mismatch")
        if build.get("executable_sha256") != actual_digests["executable"]:
            reasons.append("build_executable_mismatch")
        if build.get("package_metadata_sha256") != actual_digests["package_metadata"]:
            reasons.append("build_package_metadata_mismatch")

    embedded_commit: str | None = None
    try:
        embedded_commit = Path(str(manifest["embedded_commit_path"])).read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        pass
    if embedded_commit != binding_commit:
        reasons.append("embedded_commit_mismatch")

    client = _read_json(manifest["client_metadata_path"])
    client_artifact_digest: str | None = None
    if client is None or set(client) != {"schema_version", "name", "version", "artifact_path", "artifact_sha256"} or client.get("schema_version") != "plan-11-26-client-metadata-v1":
        reasons.append("client_metadata_invalid")
    else:
        if (client.get("name"), client.get("version")) != (expected_identity.client_name, expected_identity.client_version):
            reasons.append("client_identity_mismatch")
        client_artifact_digest = _file_sha256(client.get("artifact_path"))
        if client_artifact_digest is None or client_artifact_digest != client.get("artifact_sha256"):
            reasons.append("client_digest_mismatch")

    environment = _read_json(manifest["environment_manifest_path"])
    environment_fields = {"schema_version", "platform", "architecture", "python_version", "runtime_id"}
    if environment is None or set(environment) != environment_fields or environment.get("schema_version") != "plan-11-26-environment-v1" or any(not isinstance(environment.get(field), str) or not environment.get(field) for field in environment_fields - {"schema_version"}):
        reasons.append("environment_manifest_invalid")
    if reasons:
        return ProvenanceResult(False, tuple(sorted(set(reasons))), None)
    assert package is not None and client is not None and embedded_commit is not None
    provenance = {
        "binding_commit": binding_commit,
        "executable_path": manifest["executable_path"],
        "executable_sha256": actual_digests["executable"],
        "package_name": package["name"],
        "package_version": package["version"],
        "package_metadata_sha256": actual_digests["package_metadata"],
        "build_manifest_sha256": actual_digests["build_manifest"],
        "embedded_commit": embedded_commit,
        "embedded_commit_sha256": actual_digests["embedded_commit"],
        "launcher_sha256": actual_digests["launcher"],
        "client_provenance": {
            "name": client["name"], "version": client["version"], "path": client["artifact_path"],
            "sha256": client_artifact_digest, "metadata_sha256": actual_digests["client_metadata"],
        },
        "environment_fingerprint": actual_digests["environment_manifest"],
    }
    return ProvenanceResult(True, (), provenance)
