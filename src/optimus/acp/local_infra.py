from __future__ import annotations

import contextlib
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from contextvars import copy_context
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from pydantic import SecretStr

from optimus.acp.launch_policy import project_gateway_tool_child_env
from optimus.acp.local_gateway_secrets import ProviderCredentialResolution, _parse_env_gateway_file
from optimus.acp.process_lifecycle import cleanup_failure, raise_preserving_failure
from optimus.agent.defaults import default_agent_model
from optimus.config.gateway import _LOOPBACK_HOSTS, LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.usage.savings_report import ReportTransportError, gateway_post
from optimus_model_policy.binding import operator_override, trusted_snapshot
from optimus_security import gateway_identity
from optimus_security.accounting_config import AccountingConfigError, accounting_literal, accounting_root, config_literal
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
# docs/superpowers/plans/archive/2026-07-07-local-optimus-gateway-service.md, Scope item 5), so it would
# otherwise leak through untouched even though it is still a real provider API key. Also strip
# OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET: once apply_local_defaults() has copied its value into
# OPTIMUS_API_KEY, the agent view should keep only that public contract name, not the
# gateway-internal duplicate under its own name. Found in 2026-07-08 review, round 3.
# Retired Plan 11.4 trust-seam names remain strip-only exclusions (not launch-registry
# members); keep them as plain literals so Task 9 retirement rg can still see them.
RETIRED_AGENT_ENVIRON_KEYS = frozenset(
    {
        "OPTIMUS_PRODUCTION_MODE",
        "OPTIMUS_EXTRA_GATEWAY_ORIGINS",
    }
)
_AGENT_ENVIRON_EXCLUDED_KEYS = LOCAL_PROVIDER_KEY_NAMES | {
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",
    "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
} | RETIRED_AGENT_ENVIRON_KEYS

_REDIS_CONTAINER_NAME = "optimus-redis"
_REDIS_IMAGE = "redis:8"
_REDIS_READY_TIMEOUT_SECONDS = 15.0
_GATEWAY_READY_TIMEOUT_SECONDS = 10.0
_POLL_INTERVAL_SECONDS = 0.5
_DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
DEFAULT_REDIS_URL = _DEFAULT_REDIS_URL
_DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765"
_PHOENIX_CONTAINER_NAME = "optimus-phoenix"
_PHOENIX_IMAGE = "arizephoenix/phoenix:latest"
_PHOENIX_PORT = 6006
_PHOENIX_READY_TIMEOUT_SECONDS = 30.0
LOCAL_PHOENIX_BASE_URL = "http://127.0.0.1:6006"
LOCAL_PHOENIX_OTLP_ENDPOINT = "http://127.0.0.1:6006/v1/traces"
_PHOENIX_HEALTHZ_URL = f"{LOCAL_PHOENIX_BASE_URL}/healthz"
_SYSTEM_ENV_KEYS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP")
_EMPTY_MAPPING: Mapping[str, str] = {}


@dataclass(frozen=True)
class LocalInfrastructureError(Exception):
    code: str
    user_message: str

    def __str__(self) -> str:
        return self.user_message


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
    """Fill in loopback defaults for URLs and model.

    Plan 9.96, Task 5: credential resolution (the shared secret projected to
    OPTIMUS_API_KEY) is no longer performed here by re-reading
    .env.gateway/keyring — the launch gate's resolve_launch_candidate()
    resolves it exactly once and the caller passes the result in via
    resolved_shared_secret. This function's own config_root/environ inputs
    are used only for the URL/model default-filling that has nothing to
    do with credentials.
    """
    resolved = dict(environ)

    if not resolved.get("OPTIMUS_REDIS_URL", "").strip():
        resolved["OPTIMUS_REDIS_URL"] = _DEFAULT_REDIS_URL
    if not resolved.get("OPTIMUS_GATEWAY_URL", "").strip():
        resolved["OPTIMUS_GATEWAY_URL"] = _DEFAULT_GATEWAY_URL

    if not _is_loopback(urlparse(resolved["OPTIMUS_GATEWAY_URL"]).hostname):
        return resolved

    if not resolved.get("OPTIMUS_AGENT_MODEL", "").strip():
        # Plan 12.2 Task 5: one default source -- today's alias while registry enforcement is
        # inactive, the trusted registry's medium default once it is active.
        resolved["OPTIMUS_AGENT_MODEL"] = default_agent_model(trusted_snapshot())
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


def _is_established_default_redis_url(redis_url: str) -> bool:
    parsed = urlparse(redis_url)
    host = (parsed.hostname or "127.0.0.1").lower()
    if host == "localhost":
        host = "127.0.0.1"
    port = parsed.port or 6379
    path = parsed.path or "/0"
    if path in ("", "/"):
        path = "/0"
    return (
        host == "127.0.0.1"
        and port == 6379
        and path == "/0"
        and not parsed.username
        and not parsed.password
    )


def _docker_published_port_owners(docker: str, port: int) -> list[tuple[str, str]]:
    """Return exact (name, image) pairs publishing ``port`` on the Docker host."""
    try:
        result = subprocess.run(
            [docker, "ps", "--filter", f"publish={port}", "--format", "{{.Names}}\t{{.Image}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    owners: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        name, sep, image = line.partition("\t")
        if not sep or not name.strip():
            continue
        owners.append((name.strip(), image.strip()))
    return owners


def _assert_default_redis_port_owner(*, docker: str | None, port: int, log: Callable[[str], None]) -> None:
    """Fail closed only when Docker reports a non-optimus-redis owner of the default port."""
    if docker is None:
        log(
            "optimus-agent: Docker not available; treating reachable Redis on the default port "
            "as a native/operator-managed listener and leaving TimeSeries preflight to decide."
        )
        return
    owners = _docker_published_port_owners(docker, port)
    if not owners:
        log(
            "optimus-agent: no Docker container owns the default Redis port; treating the "
            "reachable listener as native/operator-managed and leaving TimeSeries preflight to decide."
        )
        return
    names = [name for name, _image in owners]
    if names and all(name == _REDIS_CONTAINER_NAME for name in names):
        return
    observed = ", ".join(names)
    raise LocalInfrastructureError(
        code="REDIS_PORT_CONFLICT",
        user_message=(
            f"Default Redis port {port} is owned by Docker container {observed}, "
            f"not {_REDIS_CONTAINER_NAME}. Stop or reconfigure that container yourself, "
            "or set an explicit OPTIMUS_REDIS_URL and re-approve; Optimus will not stop "
            "or delete the conflicting container."
        ),
    )


def ensure_local_redis(redis_url: str, *, log: Callable[[str], None] = _noop_log) -> None:
    parsed = urlparse(redis_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    if not _is_loopback(host):
        return
    if _tcp_reachable(host, port):
        if _is_established_default_redis_url(redis_url):
            docker = shutil.which("docker")
            _assert_default_redis_port_owner(docker=docker, port=port, log=log)
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


def _phoenix_health_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:
            return 200 <= int(getattr(response, "status", 200)) < 300
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def _docker_container_image(docker: str, name: str) -> str | None:
    try:
        result = subprocess.run(
            [docker, "inspect", "--format", "{{.Config.Image}}", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    image = result.stdout.strip()
    return image or None


def _assert_phoenix_port_identity(*, docker: str, log: Callable[[str], None]) -> None:
    owners = _docker_published_port_owners(docker, _PHOENIX_PORT)
    if not owners:
        return
    names = [name for name, _image in owners]
    if any(name != _PHOENIX_CONTAINER_NAME for name in names):
        observed = ", ".join(names)
        raise LocalInfrastructureError(
            code="PHOENIX_PORT_CONFLICT",
            user_message=(
                f"Local Phoenix port {_PHOENIX_PORT} is owned by Docker container {observed}, "
                f"not {_PHOENIX_CONTAINER_NAME}. Stop or reconfigure that container yourself; "
                "Optimus will not stop or delete the conflicting container."
            ),
        )
    for name, image in owners:
        if image != _PHOENIX_IMAGE:
            raise LocalInfrastructureError(
                code="PHOENIX_IMAGE_CONFLICT",
                user_message=(
                    f"Named container {name} is running image {image!r}, expected {_PHOENIX_IMAGE!r}. "
                    "Stop or recreate the container yourself; Optimus will not mutate it."
                ),
            )


def ensure_local_phoenix(*, log: Callable[[str], None] = _noop_log) -> str:
    """Return the fixed OTLP endpoint after named-container health succeeds."""
    docker = shutil.which("docker")
    if docker is None:
        raise LocalInfrastructureError(
            code="PHOENIX_DOCKER_MISSING",
            user_message="docker not found on PATH; cannot start local Phoenix.",
        )
    if not _docker_daemon_reachable(docker):
        raise LocalInfrastructureError(
            code="PHOENIX_DOCKER_UNREACHABLE",
            user_message="Docker daemon not reachable; cannot start local Phoenix.",
        )

    _assert_phoenix_port_identity(docker=docker, log=log)

    if _container_exists(docker, _PHOENIX_CONTAINER_NAME):
        configured = _docker_container_image(docker, _PHOENIX_CONTAINER_NAME)
        if configured is not None and configured != _PHOENIX_IMAGE:
            raise LocalInfrastructureError(
                code="PHOENIX_IMAGE_CONFLICT",
                user_message=(
                    f"Named container {_PHOENIX_CONTAINER_NAME} is configured with image "
                    f"{configured!r}, expected {_PHOENIX_IMAGE!r}. Stop or recreate it yourself; "
                    "Optimus will not mutate it."
                ),
            )
        if not _phoenix_health_ready(_PHOENIX_HEALTHZ_URL):
            log(f"optimus-agent: starting existing {_PHOENIX_CONTAINER_NAME} container...")
            subprocess.run(
                [docker, "start", _PHOENIX_CONTAINER_NAME],
                capture_output=True,
                text=True,
                check=False,
            )
    else:
        log(f"optimus-agent: creating {_PHOENIX_CONTAINER_NAME} container ({_PHOENIX_IMAGE})...")
        subprocess.run(
            [
                docker,
                "run",
                "-d",
                "--name",
                _PHOENIX_CONTAINER_NAME,
                "-p",
                f"127.0.0.1:{_PHOENIX_PORT}:{_PHOENIX_PORT}",
                _PHOENIX_IMAGE,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    deadline = time.monotonic() + _PHOENIX_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _phoenix_health_ready(_PHOENIX_HEALTHZ_URL):
            return LOCAL_PHOENIX_OTLP_ENDPOINT
        time.sleep(_POLL_INTERVAL_SECONDS)
    raise LocalInfrastructureError(
        code="PHOENIX_NOT_READY",
        user_message=(
            f"{_PHOENIX_CONTAINER_NAME} did not become healthy at {_PHOENIX_HEALTHZ_URL} in time."
        ),
    )


@dataclass
class LocalGatewayProcess:
    process: subprocess.Popen | None
    log_path: Path | None
    _stop_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)
    _stop_thread: threading.Thread | None = field(default=None, init=False, repr=False, compare=False)
    _stop_error: BaseException | None = field(default=None, init=False, repr=False, compare=False)

    @property
    def stop_pending(self) -> bool:
        return self._stop_thread is not None and self._stop_thread.is_alive()

    @property
    def stop_failure(self) -> BaseException | None:
        return self._stop_error

    def stop(self) -> None:
        with self._stop_lock:
            if self._stop_thread is None:
                if self.process is None or self.process.poll() is not None:
                    return
                self._stop_thread = threading.Thread(
                    target=copy_context().run, args=(self._stop_owned_process,), name="optimus-gateway-stop", daemon=False,
                )
                try:
                    self._stop_thread.start()
                except BaseException:
                    self._stop_thread = None
                    raise
            worker = self._stop_thread
        worker.join()
        if self._stop_error is not None:
            raise_preserving_failure(self._stop_error)

    def _stop_owned_process(self) -> None:
        try:
            if self.process is None or self.process.poll() is not None:
                return
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        except BaseException as exc:
            self._stop_error = exc


def _gateway_destination(gateway_url: str) -> tuple[str, int]:
    """The host and port this launch's requests go to. The HTTP senders use a URL's explicit port, otherwise its scheme's
    default, so a Gateway is started and confirmed there and nowhere else."""
    parsed = urlparse(gateway_url)
    return parsed.hostname or "127.0.0.1", parsed.port or (443 if parsed.scheme == "https" else 80)


def _listener_label(gateway_url: str) -> str:
    """A Gateway URL may carry a path or query the settings allow; what is shown or logged names only the address."""
    host, port = _gateway_destination(gateway_url)
    return f"{urlparse(gateway_url).scheme}://{f'[{host}]' if ':' in host else host}:{port}"


def gateway_tool_environ(config_root: Path | None, system_env: Mapping[str, str]) -> dict[str, str]:
    """The Gateway's tool configuration from `.env.gateway`, with inherited values filling what it omits."""
    tool_env: dict[str, str] = {}
    if config_root is not None:
        tool_env = project_gateway_tool_child_env(_parse_env_gateway_file(config_root / ".env.gateway"))
    return {**project_gateway_tool_child_env(system_env), **tool_env}


def gateway_accounting(
    config_root: Path, approved: str | None, *, log: Callable[[str], None] = _noop_log
) -> tuple[Path | None, str | None]:
    """Plan 12.8 (ADR-032): the Gateway's accounting root under the authorized config root and the literal its manifest
    binds, when the configuration found there is the approved one; otherwise the Gateway runs without accounting."""
    accounting_dir = accounting_root(config_root)
    try:
        current = config_literal(accounting_dir)
    except AccountingConfigError as exc:
        current = f"unusable:{exc.code}"
    if current != approved:
        log("optimus-agent: the accounting configuration is not the approved one; the Gateway starts without accounting.")
        return None, None
    return accounting_dir, accounting_literal(accounting_dir, current)


def expected_gateway_identity(
    *,
    gateway_url: str,
    provider_credentials: ProviderCredentialResolution | None,
    shared_secret: str | None,
    manifest_hmac_key: bytes,
    system_env: Mapping[str, str] = _EMPTY_MAPPING,
    config_root: Path | None = None,
    model_registry: str | None = None,
    test_profile: str | None = None,
    stage_c_envelope: str | None = None,
    auto_composition: bool = False,
    usage_accounting: bool = False,
    approved_accounting_config: str | None = None,
) -> gateway_identity.GatewayIdentity | None:
    """#465 (ADR-036): the identity of the Gateway this launch would start. None when the launch names no local upstream:
    a remote Gateway, or a host given only the Gateway URL and key, whose approval binds no upstream to compare."""
    if not _is_loopback(urlparse(gateway_url).hostname):
        return None
    secrets = None if provider_credentials is None else provider_credentials.secrets
    if secrets is None or not shared_secret:
        return None
    accounting = None
    if usage_accounting and config_root is not None:
        accounting = gateway_accounting(config_root, approved_accounting_config)[1]
    if test_profile is not None:
        composition = gateway_identity.profile_composition(test_profile)
    else:
        composition = gateway_identity.COMPOSITION_AUTO if auto_composition else gateway_identity.COMPOSITION_STANDARD
    return gateway_identity.compose_identity(
        provider=secrets.provider,
        base_url=secrets.base_url,
        provider_api_key=secrets.model_provider_api_key,
        shared_secret=shared_secret,
        composition=composition,
        model_registry=model_registry,
        stage_c_envelope=stage_c_envelope,
        accounting=accounting,
        tool_environ=gateway_tool_environ(config_root, system_env),
        hmac_key=manifest_hmac_key,
    )


_ATTACH_REMEDY = (
    "Stop that listener (another Optimus agent or `optimus-trust run-gateway` may own it), or give this agent entry its "
    "own OPTIMUS_GATEWAY_URL port and approve the launch again."
)


def verify_local_gateway(
    gateway_url: str,
    *,
    api_key: str | None,
    hmac_key: bytes,
    expected: gateway_identity.GatewayIdentity | None,
    log: Callable[[str], None] = _noop_log,
) -> None:
    """Confirm that what listens at ``gateway_url`` is a Gateway serving this launch's configuration, or refuse with a
    stated reason (`LocalInfrastructureError`). One bounded authenticated request that calls no upstream; a listener
    that is refused is never terminated. With no ``expected`` it can only confirm a current Gateway answers this key."""
    if not api_key:
        log("optimus-agent: no Gateway key to confirm the listening Gateway with; leaving pre-flight to fail closed.")
        return
    settings = OptimusGatewaySettings(gateway_url=gateway_url, optimus_api_key=SecretStr(api_key))
    nonce = gateway_identity.new_nonce()
    listener = _listener_label(gateway_url)
    unconfirmed = LocalInfrastructureError(
        code="GATEWAY_IDENTITY_UNCONFIRMED",
        user_message=(
            f"Something is listening at {listener}, but it did not confirm that it is a current Optimus Gateway: it may "
            f"be an older Gateway or another program. This agent will not use it, so no model request was sent. {_ATTACH_REMEDY}"
        ),
    )
    try:
        post = gateway_post(settings, timeout=gateway_identity.READ_SECONDS, path=gateway_identity.PATH)
        status, reply = post(gateway_identity.build_request(nonce))
    except ReportTransportError:
        raise unconfirmed from None
    if status in {401, 403}:
        raise LocalInfrastructureError(
            code="GATEWAY_KEY_REJECTED",
            user_message=(
                f"The Gateway at {listener} refused this agent's key, so it was started with a different configuration. "
                f"This agent will not use it, so no model request was sent. {_ATTACH_REMEDY}"
            ),
        )
    if status != 200:
        raise unconfirmed
    try:
        reported = gateway_identity.read_reply(reply, nonce=nonce, hmac_key=hmac_key)
    except gateway_identity.IdentityReplyError:
        raise unconfirmed from None
    if expected is None or reported.digest == expected.digest:
        return
    differing = ", ".join(gateway_identity.FIELD_LABELS[name] for name in gateway_identity.differing_fields(expected, reported))
    raise LocalInfrastructureError(
        code="GATEWAY_CONFIGURATION_MISMATCH",
        user_message=(
            f"A Gateway is already running at {listener} with a different configuration ({differing}). This agent will "
            f"not use it, so no model request was sent. {_ATTACH_REMEDY}"
        ),
    )


def record_gateway_refusal(runtime_root: Path, *, code: str, reason: str) -> None:
    """One JSON line in the launch's Gateway log: the refusal's cause outlives the session that showed it. Its text names a
    loopback URL and configuration labels only. A log that cannot be written never stops the refusal it describes."""
    line = json.dumps({"event": "gateway_refused", "at": datetime.now(timezone.utc).isoformat(), "code": code, "reason": reason})
    with contextlib.suppress(OSError):
        runtime_root.mkdir(parents=True, exist_ok=True)
        with open(runtime_root / "local-gateway.log", "ab") as log_file:
            log_file.write(line.encode("utf-8") + b"\n")


def confirm_running_gateway(
    gateway_url: str,
    *,
    api_key: str | None,
    hmac_key: bytes,
    expected: gateway_identity.GatewayIdentity | None,
    log: Callable[[str], None] = _noop_log,
) -> None:
    """For a launch that starts nothing (`--no-auto-start`): confirm a local Gateway that is listening. A remote one, or
    none at all, is left to pre-flight as before."""
    host, port = _gateway_destination(gateway_url)
    if _is_loopback(host) and _tcp_reachable(host, port):
        verify_local_gateway(gateway_url, api_key=api_key, hmac_key=hmac_key, expected=expected, log=log)


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
    config_root: Path | None = None,
    otlp_endpoint: str | None = None,
    log: Callable[[str], None] = _noop_log,
    model_registry: str | None = None,
    test_profile: str | None = None,
    stage_c_envelope: str | None = None,
    stage_c_ledger: Path | None = None,
    auto_composition: bool = False,
    usage_accounting: bool = False,
    approved_accounting_config: str | None = None,
    api_key: str | None = None,
    expected_identity: gateway_identity.GatewayIdentity | None = None,
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

    When ``config_root`` is provided, Gateway tool-provider variables from
    ``.env.gateway`` (Tavily, domain allowlist, tool Redis URL, OSV, registry
    base URLs, call caps) are projected into the child env so
    ``build_tool_dependencies`` can return a real dependency bundle.

    #465 (ADR-036): a Gateway already listening is reused only after it proves ``expected_identity``; anything else raises
    `LocalInfrastructureError` with the reason, and the listener is left running. Returns None for a reused Gateway.
    """
    host, port = _gateway_destination(gateway_url)
    if not _is_loopback(host):
        return None

    def confirm_listener() -> None:
        verify_local_gateway(gateway_url, api_key=api_key or shared_secret, hmac_key=manifest_hmac_key,
                             expected=expected_identity, log=log)

    if _tcp_reachable(host, port):
        confirm_listener()
        return None  # a compatible Gateway, from an earlier session or another workspace; don't own it

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

    tool_env = gateway_tool_environ(config_root, system_env)

    child_env: dict[str, str] = {
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER": provider_secrets.provider,
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": shared_secret,
        **provider_secrets.as_gateway_child_env(),
        **tool_env,
    }
    if otlp_endpoint:
        child_env["OTEL_EXPORTER_OTLP_ENDPOINT"] = otlp_endpoint
    for key in _SYSTEM_ENV_KEYS:
        value = system_env.get(key, "")
        if value:
            child_env[key] = value

    # Plan 12.8 (ADR-032): the configuration found under the authorized config root, approved by the launch gate. The
    # Gateway composes the same literal itself; the manifest must bind it.
    accounting_dir = accounting = None
    if usage_accounting and config_root is not None:
        accounting_dir, accounting = gateway_accounting(config_root, approved_accounting_config, log=log)
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
        model_registry=model_registry,
        stage_c_envelope=stage_c_envelope,
        accounting=accounting,
    )
    serialized_manifest = serialize_gateway_child_manifest(manifest)

    log_path = runtime_root / "local-gateway.log"
    try:
        runtime_root.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "ab")
    except OSError as exc:
        log(f"optimus-agent: could not prepare local gateway log file ({exc}); leaving Gateway pre-flight to fail closed.")
        return None

    process = None
    owned: LocalGatewayProcess | None = None
    stop_attempted = False
    try:
        try:
            # A named Plan 12.2 test profile is passed by name only: the Gateway composes it from its own
            # reviewed source and refuses unless the signed manifest binds that hash (release supplement V2).
            profile_argv = [] if test_profile is None else ["--plan12-test-profile", test_profile]
            # Plan 12.2 Task 13 (Stage C): the resolved ledger is passed by path; the Gateway composes the
            # envelope itself and refuses unless the signed manifest binds exactly that envelope.
            if stage_c_ledger is not None:
                profile_argv += ["--plan12-stage-c-ledger", str(stage_c_ledger)]
            # ADR-025: the operator's registry override is passed by path; the Gateway composes it itself and refuses unless
            # the signed manifest binds the resulting hash. A test profile never reads it.
            override = None if test_profile is not None or config_root is None else operator_override(config_root)
            if override is not None:
                profile_argv += ["--registry-override", str(override)]
            # Plan 12.4 Design 1: an Auto launch's Gateway composes the Auto registry itself; the signed manifest must bind
            # that hash, so a Gateway composing anything else refuses to start.
            if auto_composition:
                profile_argv.append("--auto-composition")
            if accounting_dir is not None:
                profile_argv += ["--accounting-root", str(accounting_dir)]
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
                    *profile_argv,
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
        owned = LocalGatewayProcess(process=process, log_path=log_path)
        log(f"optimus-agent: starting local gateway (pid {process.pid}); logging to {log_path}")

        deadline = time.monotonic() + _GATEWAY_READY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log(f"optimus-agent: local gateway exited early (code {process.returncode}); see {log_path}")
                # Two launches can start at once; the loser's child cannot bind. What holds the port is not this launch's.
                if _tcp_reachable(host, port):
                    confirm_listener()
                return None
            if _tcp_reachable(host, port):
                confirm_listener()  # the port may be another launch's while this child is still starting
                return owned
            time.sleep(_POLL_INTERVAL_SECONDS)

        log(f"optimus-agent: local gateway did not become ready in time; see {log_path}")
        stop_attempted = True
        assert owned is not None
        owned.stop()
        return None
    except BaseException as primary:
        if process is None:
            raise
        if owned is None:
            owned = LocalGatewayProcess(process=process, log_path=log_path)
        if not stop_attempted:
            try:
                owned.stop()
            except BaseException as cleanup:
                failure = cleanup_failure([("startup", primary), ("gateway", cleanup)])
                failure.__dict__["_optimus_cleanup_stages"] = ("gateway",)
                if owned.stop_pending or (owned.process is not None and owned.process.poll() is None):
                    failure.__dict__["_optimus_pending_gateway"] = owned
                raise_preserving_failure(failure)
        elif owned.stop_failure is not None:
            primary.__dict__["_optimus_cleanup_stages"] = ("gateway",)
        if owned.stop_pending or (owned.process is not None and owned.process.poll() is None):
            primary.__dict__["_optimus_pending_gateway"] = owned
        raise
