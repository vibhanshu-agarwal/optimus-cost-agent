from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from optimus.acp.local_gateway_secrets import ProviderCredentialResolution
from optimus.config.gateway import _LOOPBACK_HOSTS, LOCAL_PROVIDER_KEY_NAMES
from optimus_security.launch_manifest import build_gateway_child_manifest, serialize_gateway_child_manifest

# _LOOPBACK_HOSTS reused from optimus.config.gateway (agent-side package, already imported
# elsewhere in bootstrap.py) rather than src/optimus_gateway/models.py's own separate copy of the
# same frozenset — the local-gateway-service plan documents optimus_gateway as "a distinct
# process/deployable, not a module the agent imports," so this module must not import across
# that boundary even though optimus_gateway/models.py happens to define an identical constant.

# The agent-facing environ (passed to build_configured_server / strict run_preflight) must never
# contain a real vendor key OR the local gateway's own auth secret. LOCAL_PROVIDER_KEY_NAMES alone
# is not enough: it's the set OptimusGatewaySettings.from_env() explicitly rejects (ANTHROPIC_API_KEY,
# OPENAI_API_KEY, etc.), but OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY — the var GatewayServiceConfig
# reads for the openai/openrouter path — was deliberately NOT put in that set (it exists precisely
# to avoid the ANTHROPIC_API_KEY-style collision; see
# docs/superpowers/plans/2026-07-07-local-optimus-gateway-service.md, Scope item 5), so it would
# otherwise leak through untouched even though it is still a real provider API key. Also strip
# OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET: once apply_local_defaults() has copied its value into
# OPTIMUS_API_KEY, the agent view should keep only that public contract name, not the
# gateway-internal duplicate under its own name. Found in 2026-07-08 review, round 3.
_AGENT_ENVIRON_EXCLUDED_KEYS = LOCAL_PROVIDER_KEY_NAMES | {
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",
    "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
}

_REDIS_CONTAINER_NAME = "optimus-redis"
_REDIS_IMAGE = "redis:8"
_REDIS_READY_TIMEOUT_SECONDS = 15.0
_GATEWAY_READY_TIMEOUT_SECONDS = 10.0
_POLL_INTERVAL_SECONDS = 0.5
_DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
_DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765"
_DEFAULT_LOCAL_AGENT_MODEL = "claude-haiku"
_SYSTEM_ENV_KEYS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP")
_EMPTY_MAPPING: Mapping[str, str] = {}


def _noop_log(_message: str) -> None:
    return


def _is_loopback(host: str | None) -> bool:
    return (host or "").lower() in _LOOPBACK_HOSTS


def apply_local_defaults(
    environ: Mapping[str, str],
    *,
    config_root: Path,
    resolved_shared_secret: str | None = None,
) -> dict[str, str]:
    """Fill in loopback defaults for URLs/production mode/model.

    Plan 9.96, Task 5: credential resolution (the shared secret projected to
    OPTIMUS_API_KEY) is no longer performed here by re-reading
    .env.gateway/keyring — the launch gate's resolve_launch_candidate()
    resolves it exactly once and the caller passes the result in via
    resolved_shared_secret. This function's own config_root/environ inputs
    are used only for the URL/mode/model default-filling that has nothing to
    do with credentials.
    """
    resolved = dict(environ)

    if not resolved.get("OPTIMUS_REDIS_URL", "").strip():
        resolved["OPTIMUS_REDIS_URL"] = _DEFAULT_REDIS_URL
    if not resolved.get("OPTIMUS_GATEWAY_URL", "").strip():
        resolved["OPTIMUS_GATEWAY_URL"] = _DEFAULT_GATEWAY_URL

    if not _is_loopback(urlparse(resolved["OPTIMUS_GATEWAY_URL"]).hostname):
        return resolved

    if not resolved.get("OPTIMUS_PRODUCTION_MODE", "").strip():
        resolved["OPTIMUS_PRODUCTION_MODE"] = "false"
    if not resolved.get("OPTIMUS_AGENT_MODEL", "").strip():
        resolved["OPTIMUS_AGENT_MODEL"] = _DEFAULT_LOCAL_AGENT_MODEL
    if not resolved.get("OPTIMUS_API_KEY", "").strip() and resolved_shared_secret:
        resolved["OPTIMUS_API_KEY"] = resolved_shared_secret

    return resolved


def strip_local_provider_keys(environ: Mapping[str, str]) -> dict[str, str]:
    """Produce the agent-facing environ view: never contains a real vendor key or the local
    gateway's own auth secret under its gateway-side name.

    ensure_local_gateway() legitimately reads provider keys and the shared secret from the
    UNSANITIZED environ to construct the spawned gateway's own child env. But
    OptimusGatewaySettings.from_env() — reached from build_configured_server and, in strict mode,
    run_preflight — explicitly rejects any LOCAL_PROVIDER_KEY_NAMES entry with
    ProviderKeyViolation (the anthropic-provider collision), and even where a name isn't on that
    reject list (OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY for openai/openrouter), it's still a real
    provider API key that should never sit in the agent's own view — see
    _AGENT_ENVIRON_EXCLUDED_KEYS above. The two call sites must never share one environ object.
    Callers pass this function's output to build_configured_server/run_preflight; they pass the
    original, unsanitized environ to ensure_local_gateway.
    """
    return {key: value for key, value in environ.items() if key not in _AGENT_ENVIRON_EXCLUDED_KEYS}


def _tcp_reachable(host: str, port: int, *, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _docker_daemon_reachable(docker: str) -> bool:
    try:
        result = subprocess.run([docker, "ps"], capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _container_exists(docker: str, name: str) -> bool:
    try:
        result = subprocess.run(
            [docker, "ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return name in result.stdout.split()


def ensure_local_redis(redis_url: str, *, log: Callable[[str], None] = _noop_log) -> None:
    parsed = urlparse(redis_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    if not _is_loopback(host):
        return
    if _tcp_reachable(host, port):
        return

    docker = shutil.which("docker")
    if docker is None:
        log("optimus-agent: docker not found on PATH; leaving Redis pre-flight to fail closed.")
        return
    if not _docker_daemon_reachable(docker):
        log("optimus-agent: Docker daemon not reachable; leaving Redis pre-flight to fail closed.")
        return

    if _container_exists(docker, _REDIS_CONTAINER_NAME):
        log(f"optimus-agent: starting existing {_REDIS_CONTAINER_NAME} container...")
        subprocess.run([docker, "start", _REDIS_CONTAINER_NAME], capture_output=True, text=True, check=False)
    else:
        log(f"optimus-agent: creating {_REDIS_CONTAINER_NAME} container ({_REDIS_IMAGE})...")
        subprocess.run(
            [docker, "run", "-d", "--name", _REDIS_CONTAINER_NAME, "-p", f"127.0.0.1:{port}:6379", _REDIS_IMAGE],
            capture_output=True,
            text=True,
            check=False,
        )

    deadline = time.monotonic() + _REDIS_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _tcp_reachable(host, port):
            return
        time.sleep(_POLL_INTERVAL_SECONDS)
    log(f"optimus-agent: {_REDIS_CONTAINER_NAME} did not become reachable in time; leaving pre-flight to fail closed.")


@dataclass
class LocalGatewayProcess:
    process: subprocess.Popen | None
    log_path: Path | None

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def ensure_local_gateway(
    *,
    gateway_url: str,
    provider_credentials: ProviderCredentialResolution | None,
    shared_secret: str | None,
    workspace_digest: str,
    security_snapshot_digest: str,
    manifest_hmac_key: bytes,
    policy_version: str,
    runtime_root: Path,
    system_env: Mapping[str, str] = _EMPTY_MAPPING,
    log: Callable[[str], None] = _noop_log,
) -> LocalGatewayProcess | None:
    """Start the local Gateway child using ALREADY-RESOLVED credentials.

    Plan 9.96, Task 5 Step 3/4: this function no longer re-resolves provider
    credentials or the shared secret from .env.gateway/keyring/environment —
    the caller (the authorized launch gate) resolved them exactly once and
    passes the resulting immutable objects in directly. This function builds
    a short-lived HMAC-signed GatewayChildManifest bound to the caller's
    workspace/security-snapshot digests and passes bind_host/bind_port as
    explicit CLI arguments — never through OPTIMUS_LOCAL_GATEWAY_BIND_HOST/
    PORT — closing the standalone bind seam from the parent side.
    """
    parsed = urlparse(gateway_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765
    if not _is_loopback(host):
        return None
    if _tcp_reachable(host, port):
        return None  # already up - ours from an earlier session, or someone else's; don't own it

    if provider_credentials is None:
        log(
            "optimus-agent: no compatible local gateway credentials found "
            "(run `optimus-trust setup-credentials`); leaving Gateway pre-flight to fail closed."
        )
        return None
    for warning in provider_credentials.warnings:
        log(warning)

    provider_secrets = provider_credentials.secrets
    if provider_secrets is None or not shared_secret:
        log(
            "optimus-agent: no compatible local gateway credentials found "
            "(run `optimus-trust setup-credentials`); leaving Gateway pre-flight to fail closed."
        )
        return None

    child_env: dict[str, str] = {
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER": provider_secrets.provider,
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": shared_secret,
        **provider_secrets.as_gateway_child_env(),
    }
    for key in _SYSTEM_ENV_KEYS:
        value = system_env.get(key, "")
        if value:
            child_env[key] = value

    manifest = build_gateway_child_manifest(
        workspace_digest=workspace_digest,
        security_snapshot_digest=security_snapshot_digest,
        provider=provider_secrets.provider,
        base_url=provider_secrets.base_url,
        bind_host=host,
        bind_port=port,
        provider_api_key=provider_secrets.model_provider_api_key,
        shared_secret=shared_secret,
        hmac_key=manifest_hmac_key,
        policy_version=policy_version,
    )
    serialized_manifest = serialize_gateway_child_manifest(manifest)

    log_path = runtime_root / "local-gateway.log"
    try:
        runtime_root.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "ab")
    except OSError as exc:
        log(f"optimus-agent: could not prepare local gateway log file ({exc}); leaving Gateway pre-flight to fail closed.")
        return None

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "optimus_gateway",
                "--bind-host",
                host,
                "--port",
                str(port),
                "--manifest",
                serialized_manifest,
            ],
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        log(f"optimus-agent: could not start local gateway process ({exc}); leaving Gateway pre-flight to fail closed.")
        return None
    finally:
        log_file.close()  # the child holds its own duplicated fd; the parent doesn't need this one
    log(f"optimus-agent: starting local gateway (pid {process.pid}); logging to {log_path}")

    deadline = time.monotonic() + _GATEWAY_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log(f"optimus-agent: local gateway exited early (code {process.returncode}); see {log_path}")
            return None
        if _tcp_reachable(host, port):
            return LocalGatewayProcess(process=process, log_path=log_path)
        time.sleep(_POLL_INTERVAL_SECONDS)

    log(f"optimus-agent: local gateway did not become ready in time; see {log_path}")
    LocalGatewayProcess(process=process, log_path=log_path).stop()
    return None
