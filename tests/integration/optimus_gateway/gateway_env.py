from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import keyring
import pytest
from dotenv import dotenv_values

from optimus_gateway.models import GatewayServiceConfig
from optimus_security.launch_manifest import (
    LaunchManifestError,
    build_gateway_child_manifest,
    read_manifest_hmac_key,
    serialize_gateway_child_manifest,
)

GATEWAY_ENV_FILENAME = ".env.gateway"

# Placeholder snapshot digests for the live-smoke child manifest. Plan 9.96's
# verify_gateway_child_manifest checks only the manifest's own HMAC signature,
# expiry, and that provider/base_url/credentials/bind match the child's
# constructed config — it never validates these digests against an external
# approval store. These match the unit-test precedent in
# tests/unit/optimus_gateway/test_main_entrypoint.py.
_LIVE_SMOKE_WORKSPACE_DIGEST = "a" * 64
_LIVE_SMOKE_SECURITY_SNAPSHOT_DIGEST = "b" * 64
_LIVE_SMOKE_POLICY_VERSION = "P9.96-v1"

# Plan 9.96 __main__ rejects these inherited bind names; bind host/port are
# supplied via --bind-host/--port instead. The live-smoke launch env must not
# carry them or the child fails closed before manifest validation.
REJECTED_CHILD_BIND_ENV_NAMES = ("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "OPTIMUS_LOCAL_GATEWAY_PORT")


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def gateway_env_file_path(root: Path | None = None) -> Path:
    return (root or project_root()) / GATEWAY_ENV_FILENAME


def load_gateway_env_file(root: Path | None = None) -> dict[str, str]:
    """Load gateway secrets from disk without mutating ``os.environ``."""
    path = gateway_env_file_path(root)
    if not path.is_file():
        return {}
    values = dotenv_values(path)
    return {key: value for key, value in values.items() if key and value is not None}


def resolve_gateway_provider_api_key(gateway_env: Mapping[str, str]) -> str:
    api_key = gateway_env.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "").strip()
    if not api_key:
        pytest.fail(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY is required in .env.gateway "
            "for OpenRouter live smoke tests."
        )
    return api_key


def merge_gateway_subprocess_env(
    *,
    base_environ: Mapping[str, str] | None = None,
    root: Path | None = None,
    port: int,
    shared_secret: str,
) -> dict[str, str]:
    gateway_env = dict(base_environ or os.environ)
    gateway_env.update(load_gateway_env_file(root))

    configured_provider = gateway_env.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "").strip().lower()
    if configured_provider and configured_provider != "openrouter":
        pytest.fail(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER must be omitted or set to openrouter "
            "for live smoke tests."
        )

    gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"] = "openrouter"
    gateway_env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] = shared_secret
    gateway_env["OPTIMUS_LOCAL_GATEWAY_BIND_HOST"] = "127.0.0.1"
    gateway_env["OPTIMUS_LOCAL_GATEWAY_PORT"] = str(port)
    gateway_env.pop("OPTIMUS_GATEWAY_URL", None)
    gateway_env.pop("OPTIMUS_API_KEY", None)
    gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] = resolve_gateway_provider_api_key(gateway_env)
    gateway_env.pop("ANTHROPIC_API_KEY", None)

    _ensure_src_on_pythonpath(gateway_env, root or project_root())

    return gateway_env


def build_signed_child_manifest(
    *,
    gateway_env: Mapping[str, str],
    port: int,
    bind_host: str = "127.0.0.1",
) -> str:
    """Build a real HMAC-signed GatewayChildManifest for the live-smoke launch.

    Plan 9.96 gated ``python -m optimus_gateway`` behind ``--bind-host`` and a
    signed ``--manifest``. This live-tier harness must satisfy that real gate
    rather than mock it: it reads the real approval-store HMAC key from the OS
    keyring — the same key the spawned child reads independently through
    ``read_manifest_hmac_key`` — and signs a manifest bound to the exact
    provider/base_url/credentials/bind the child will construct.

    The child's construction inputs are reproduced by building
    ``GatewayServiceConfig.from_env`` here with the same env and bind values the
    child receives, so the signed provider/base_url/provider_api_key/shared_secret
    match by construction.
    """
    config = GatewayServiceConfig.from_env(gateway_env, bind_host=bind_host, bind_port=port)
    try:
        hmac_key = read_manifest_hmac_key(keyring)
    except LaunchManifestError as exc:
        pytest.fail(
            "approval-store HMAC key unavailable from the OS keyring "
            f"({exc.code}); it is required to sign the live-gateway child manifest. "
            "Provision it before running requires_live_gateway tests."
        )
    manifest = build_gateway_child_manifest(
        workspace_digest=_LIVE_SMOKE_WORKSPACE_DIGEST,
        security_snapshot_digest=_LIVE_SMOKE_SECURITY_SNAPSHOT_DIGEST,
        provider=config.provider,
        base_url=config.base_url,
        bind_host=config.bind_host,
        bind_port=config.bind_port,
        provider_api_key=config.provider_api_key,
        shared_secret=config.shared_secret,
        hmac_key=hmac_key,
        policy_version=_LIVE_SMOKE_POLICY_VERSION,
    )
    return serialize_gateway_child_manifest(manifest)


def strip_rejected_child_bind_env(gateway_env: dict[str, str]) -> dict[str, str]:
    """Remove inherited bind names Plan 9.96 __main__ rejects, in place."""
    for name in REJECTED_CHILD_BIND_ENV_NAMES:
        gateway_env.pop(name, None)
    return gateway_env


def _ensure_src_on_pythonpath(gateway_env: dict[str, str], root: Path) -> None:
    src_path = str(root / "src")
    existing = gateway_env.get("PYTHONPATH", "").strip()
    if not existing:
        gateway_env["PYTHONPATH"] = src_path
        return
    prefix_entries = existing.split(os.pathsep)
    if prefix_entries[0] == src_path:
        return
    gateway_env["PYTHONPATH"] = f"{src_path}{os.pathsep}{existing}"
