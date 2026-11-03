"""`optimus-trust memory-setup` (Plan 12.10 Task 2; ADR-037): the one-time terminal step that opts a machine into the context index.

It is the only place the embedding artifact is downloaded and the index password is created: never an agent launch, never a
startup prompt. The password goes straight to the Gateway's keyring namespace and only its hash reaches a file. Nothing here starts
a container; the ACP host does that from what this writes. The feature stays off until the operator approves the new configuration.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

from optimus_security.memory_index_config import (
    ACL_NAME,
    ARTIFACTS_NAME,
    CONFIG_NAME,
    KEYRING_SERVICE,
    MemoryIndexConfigError,
    acl_text,
    artifact_digest,
    memory_index_root,
    read,
)

_DEFAULTS = "memory_index_defaults.json"
_CREDENTIAL_NAME = "redis-password"
_ALLOWED_ARTIFACT_FILES = ("*.json", "*.onnx", "*.txt")


class MemorySetupError(RuntimeError):
    """A setup step that could not finish, with what to do next. Carries no secret."""


def shipped_defaults() -> dict[str, Any]:
    """The configured resource and embedding artifact. Models are configuration (ADR-025), so this file is their only source."""
    data: dict[str, Any] = json.loads(resources.files("optimus.context").joinpath(_DEFAULTS).read_text(encoding="utf-8"))
    for field in ("revision", "artifact_sha256"):  # digests are written `hex:<digest>` in tracked files
        data["embedding"][field] = data["embedding"][field].removeprefix("hex:")
    return data


def huggingface_download(*, repository: str, revision: str, target: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise MemorySetupError("The memory packages are not installed. Install the `memory` extra, then run this again.") from exc
    snapshot_download(repo_id=repository, revision=revision, local_dir=target, allow_patterns=list(_ALLOWED_ARTIFACT_FILES))


def _atomic_write(path: Path, data: bytes, *, mode: int) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def describe(defaults: dict[str, Any]) -> str:
    embedding = defaults["embedding"]
    return (
        f"  Download once: {embedding['model']} from {embedding['source']} at revision {embedding['revision']}, "
        f"licence {embedding['licence']}, about {defaults['artifact_megabytes']} MB.\n"
        f"  Keyring: one generated password in {KEYRING_SERVICE}.\n"
        f"  Docker, at the next approved launch: container {defaults['container']}, volume {defaults['volume']}, "
        f"{defaults['host']}:{defaults['port']}, up to {defaults['maxmemory_mb']} MB, image {defaults['image']}.\n"
        "  No model is called. Nothing runs until you approve the launch again."
    )


def run_setup(
    config_root: Path,
    *,
    keyring_backend: Any,
    confirm: Callable[[str], bool],
    download: Callable[..., None] = huggingface_download,
    defaults: dict[str, Any] | None = None,
) -> Path:
    """Write the configuration, or return it when one is already here. A rerun never replaces a working password."""
    root = memory_index_root(config_root)
    try:
        literal, _config, refusal = read(root)
    except MemoryIndexConfigError as exc:
        raise MemorySetupError(f"The existing memory configuration cannot be read ({exc.code}). Move it aside and run this again.") from exc
    if refusal is not None:
        raise MemorySetupError(f"The existing memory configuration is not usable ({refusal}). Move it aside and run this again.")
    if literal is not None:
        return root / CONFIG_NAME
    settings = shipped_defaults() if defaults is None else defaults
    if not confirm(describe(settings)):
        raise MemorySetupError("Setup was not confirmed; nothing was changed.")

    embedding = settings["embedding"]
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / ARTIFACTS_NAME / embedding["artifact_directory"]
    artifact.mkdir(parents=True, exist_ok=True)
    download(repository=embedding["repository"], revision=embedding["revision"], target=artifact)
    found = artifact_digest(_content_only(artifact))
    if found != embedding["artifact_sha256"]:
        raise MemorySetupError(f"The downloaded artifact's digest is {found}, not the configured one; nothing was configured.")

    password = secrets.token_urlsafe(32)
    try:
        keyring_backend.set_password(KEYRING_SERVICE, _CREDENTIAL_NAME, password)
    except Exception as exc:  # noqa: BLE001 - any backend failure stops setup before a file claims a credential exists
        raise MemorySetupError(f"The OS keyring refused the password ({type(exc).__name__}); nothing was configured.") from None
    acl = acl_text(settings["user"], hashlib.sha256(password.encode("utf-8")).hexdigest()).encode("utf-8")
    # The container's own user reads this bind mount, and it holds only the hash of a generated high-entropy password.
    _atomic_write(root / ACL_NAME, acl, mode=0o644)
    config = {
        "schema_version": 1,
        "resource": f"optimus-memory-{secrets.token_hex(8)}",
        "image": settings["image"],
        "container": settings["container"],
        "volume": settings["volume"],
        "host": settings["host"],
        "port": settings["port"],
        "user": settings["user"],
        "credential_name": _CREDENTIAL_NAME,
        "maxmemory_mb": settings["maxmemory_mb"],
        "acl_sha256": hashlib.sha256(acl).hexdigest(),
        "embedding": {key: embedding[key] for key in ("model", "source", "revision", "licence", "dimensions", "max_input_tokens", "artifact_sha256")},
    }
    _atomic_write(root / CONFIG_NAME, json.dumps(config, indent=2, sort_keys=True).encode("utf-8"), mode=0o600)
    return root / CONFIG_NAME


def _content_only(artifact: Path) -> Path:
    """A download tool's own bookkeeping is not the artifact."""
    cache = artifact / ".cache"
    if cache.exists():
        for path in sorted(cache.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        cache.rmdir()
    return artifact
