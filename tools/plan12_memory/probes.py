"""Plan 12.7 memory feasibility probes (M0a-3): config admission, attributable records and dispatch.

Each probe runs under a validated `ProbeConfig` and returns a `ProbeResult`. Execution outcome and
administrative disposition are separate fields: a handed-off probe is never a PASS. Records are
sanitized and written once; a later attempt never replaces an earlier one. Synthetic bodies stay in
RAM: a record that would contain one is refused. Nothing runs at import time.

    python -m tools.plan12_memory.probes --kind packages --config reports/plan12-memory-feasibility/probe-config.json

The package, embedding and Postgres bodies live here; Redis is `redis_probe`, ACP/Zed is `client_probe`.
Candidate packages run only in an isolated probe venv, through `probe_child`.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
KINDS = ("packages", "embedding", "redis", "postgres", "zed")
OUTCOMES = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "UNRUN", "UNAVAILABLE", "ERROR"})
DISPOSITIONS = frozenset({"concluded", "handoff", "open"})
CONFIG_ENV = "OPTIMUS_PLAN12_PROBE_CONFIG"
# The shared test/product Redis: every database on it, under every loopback alias, is refused.
PROTECTED_REDIS_PORTS = frozenset({6379})
# Read only to protect what they name, never as a fallback endpoint.
_SHARED_REDIS_ENV = ("OPTIMUS_REDIS_URL", "REDIS_URL")
# The default PostgreSQL port; evidence-handoff and any local server keep it.
PROTECTED_POSTGRES_PORTS = frozenset({5432})
DEFAULT_OUT = Path("reports/plan12-memory-feasibility/attempts")
_MAX_STRING = 2048
_MIN_BODY = 16
_SECRET_PATTERNS = (
    ("openai-style-key", re.compile(r"sk-[A-Za-z0-9_-]{8,}")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("credential-assignment", re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+")),
    ("url-userinfo", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/@\s:]*:[^/@\s]+@")),
)
_TOP_KEYS = {"schema_version", "run_label", "authorization", "limits", "allowed_hosts", "redis", "postgres", "zed",
             "packages", "embedding", "targets"}
_REDIS_KEYS = {"endpoint", "container", "image", "image_id", "volume", "username", "credential_env"}
_POSTGRES_KEYS = {"host", "port", "container", "image_id", "volume", "user", "database", "credential_env"}
REDIS_TARGETS = ("items", "vector_dimensions", "item_bytes", "concurrency", "maxmemory_bytes", "admission_reserve_bytes",
                 "physical_ram_bytes", "disk_bytes", "ack_latency_p95_ms", "projection_latency_p95_ms",
                 "restart_to_usable_seconds", "logical_purge_seconds", "physical_erasure_seconds")


class ConfigError(ValueError):
    """The probe config is malformed; nothing ran."""


class AdmissionError(RuntimeError):
    """An endpoint or resource was refused before any client was constructed."""


class PersistenceRefused(RuntimeError):
    """A record would have carried a RAM-only body; it was not written."""


@dataclass(frozen=True)
class RedisResource:
    endpoint: str
    container: str
    image: str
    image_id: str
    volume: str
    username: str | None = None
    credential_env: str | None = None


@dataclass(frozen=True)
class ProbeConfig:
    run_label: str
    authorization: str
    timeout_seconds: float
    max_download_bytes: int
    allowed_hosts: tuple[str, ...]
    sections: Mapping[str, Any]
    targets: Mapping[str, Mapping[str, float]]
    redis: RedisResource | None
    sha256: str

    def redis_targets_complete(self) -> bool:
        values = self.targets.get("redis", {})
        return all(isinstance(values.get(name), int | float) and values[name] > 0 for name in REDIS_TARGETS)


@dataclass
class ProbeResult:
    kind: str
    run_label: str
    config_sha256: str
    outcome: str = "UNRUN"
    disposition: str = "open"
    attempt_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_utc: str = ""
    ended_utc: str = ""
    source: Mapping[str, Any] = field(default_factory=dict)
    environment: Mapping[str, Any] = field(default_factory=dict)
    observations: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    cleanup: list[dict[str, Any]] = field(default_factory=list)
    owner: str = "claude"
    follow_up: str = ""
    redactions: int = 0


@dataclass
class ProbeContext:
    """What a probe body receives: its config, a cancel signal, RAM-only bodies and a cleanup journal."""

    config: ProbeConfig
    cancelled: threading.Event = field(default_factory=threading.Event)
    ram_only: set[str] = field(default_factory=set)
    cleanups: list[tuple[str, Callable[[], object]]] = field(default_factory=list)

    def on_cleanup(self, description: str, action: Callable[[], object]) -> None:
        self.cleanups.append((description, action))

    def check(self) -> None:
        if self.cancelled.is_set():
            raise TimeoutError("probe cancelled at its deadline")


def _utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _require(mapping: Mapping[str, Any], key: str, kind: Any, where: str) -> Any:
    value = mapping.get(key)
    if not isinstance(value, kind) or (isinstance(value, bool) and kind is not bool):
        raise ConfigError(f"{where}.{key} is missing or has the wrong type")
    return value


def _section(data: Mapping[str, Any], name: str, keys: set[str], required: Sequence[str]) -> dict[str, Any]:
    section = _require(data, name, dict, "config")
    if unknown := set(section) - keys:
        raise ConfigError(f"unknown {name} keys: {sorted(unknown)}")
    for key in required:
        _require(section, key, str, name)
    return section


def parse_config(raw: bytes) -> ProbeConfig:
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigError(f"config is not JSON: {error.__class__.__name__}") from None
    if not isinstance(data, dict):
        raise ConfigError("config must be an object")
    if unknown := set(data) - _TOP_KEYS:
        raise ConfigError(f"unknown config keys: {sorted(unknown)}")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ConfigError(f"schema_version must be {SCHEMA_VERSION}")
    limits = _require(data, "limits", dict, "config")
    timeout = _require(limits, "timeout_seconds", int | float, "limits")
    max_download = _require(limits, "max_download_bytes", int, "limits")
    if timeout <= 0 or max_download < 0:
        raise ConfigError("limits must be positive")
    hosts = data.get("allowed_hosts", [])
    if not isinstance(hosts, list) or not all(isinstance(host, str) and host for host in hosts):
        raise ConfigError("allowed_hosts must be a list of host names")
    targets = data.get("targets", {})
    if not isinstance(targets, dict) or not all(
        isinstance(group, dict) and all(isinstance(v, int | float) and not isinstance(v, bool) for v in group.values())
        for group in targets.values()
    ):
        raise ConfigError("targets must map probe names to numeric bounds")
    redis = None
    if "redis" in data:
        redis = RedisResource(**_section(data, "redis", _REDIS_KEYS, ("endpoint", "container", "image", "image_id", "volume")))
    if "postgres" in data:
        _section(data, "postgres", _POSTGRES_KEYS, ("host", "container", "image_id", "volume", "user", "database"))
        _require(data["postgres"], "port", int, "postgres")
    return ProbeConfig(
        run_label=_require(data, "run_label", str, "config"),
        authorization=_require(data, "authorization", str, "config"),
        timeout_seconds=float(timeout),
        max_download_bytes=max_download,
        allowed_hosts=tuple(host.lower() for host in hosts),
        sections={key: data[key] for key in ("postgres", "zed", "packages", "embedding") if key in data},
        targets=targets,
        redis=redis,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_config(path: Path) -> ProbeConfig:
    return parse_config(path.read_bytes())


def config_from_environment(environ: Mapping[str, str] | None = None) -> ProbeConfig | None:
    """The explicit probe config, or None. Generic Redis variables never supply one."""
    value = (os.environ if environ is None else environ).get(CONFIG_ENV, "")
    return load_config(Path(value)) if value else None


def allowed_url(url: str, config: ProbeConfig) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "").lower() in config.allowed_hosts


def _resolved(host: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return {ipaddress.ip_address(host)}
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise AdmissionError(f"host {host!r} does not resolve") from None
    return {ipaddress.ip_address(str(info[4][0]).split("%", 1)[0]) for info in infos}


def admit_loopback(host: str, port: int, protected: set[int] | frozenset[int]) -> None:
    addresses = _resolved(host)
    if not addresses or not all(address.is_loopback for address in addresses):
        raise AdmissionError("endpoint must resolve only to loopback")
    if port in protected:
        raise AdmissionError(f"port {port} belongs to a shared server (refused on every database and alias)")


def _protected_redis_ports(environ: Mapping[str, str]) -> set[int]:
    ports = set(PROTECTED_REDIS_PORTS)
    for name in _SHARED_REDIS_ENV:
        if value := environ.get(name):
            try:
                ports.add(urlsplit(value).port or 6379)
            except ValueError:
                ports.add(6379)
    return ports


def admit_redis_endpoint(resource: RedisResource, *, environ: Mapping[str, str] | None = None) -> tuple[str, int, int]:
    """Parse and refuse before any client exists: loopback only, never a protected server on any database."""
    parts = urlsplit(resource.endpoint)
    try:
        port = parts.port
    except ValueError:
        raise AdmissionError("redis endpoint has an invalid port") from None
    if parts.scheme != "redis" or not parts.hostname or port is None:
        raise AdmissionError("redis endpoint must be redis://<loopback-host>:<port>/<db>")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise AdmissionError("redis endpoint must carry no credentials, query or fragment")
    path = parts.path.strip("/") or "0"
    if not path.isdigit():
        raise AdmissionError("redis endpoint database must be a number")
    admit_loopback(parts.hostname, port, _protected_redis_ports(os.environ if environ is None else environ))
    return parts.hostname, port, int(path)


def _check_container(info: Mapping[str, Any], *, name: str, image_id: str, container_port: str, host_port: int,
                     volume: str, destination: str) -> dict[str, Any]:
    actual = str(info.get("Name", "")).lstrip("/")
    if actual != name:
        raise AdmissionError(f"inspected container is {actual!r}, not the released {name!r}")
    if info.get("Image") != image_id:
        raise AdmissionError("container image does not match the released image id")
    if not (info.get("State") or {}).get("Running"):
        raise AdmissionError("released container is not running")
    bindings = ((info.get("HostConfig") or {}).get("PortBindings") or {})
    if bindings != {container_port: [{"HostIp": "127.0.0.1", "HostPort": str(host_port)}]}:
        raise AdmissionError(f"container must publish only {container_port} on 127.0.0.1:{host_port}")
    mounts = info.get("Mounts") or []
    if [(m.get("Type"), m.get("Name"), m.get("Destination")) for m in mounts] != [("volume", volume, destination)]:
        raise AdmissionError(f"container must mount exactly the released volume at {destination}")
    return {"container": actual, "container_id": info.get("Id"), "image_id": image_id, "volume": volume,
            "host_port": host_port}


def admit_redis_resource(resource: RedisResource, inspect: Callable[[str], Mapping[str, Any]], *,
                         environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Bind the endpoint to the released disposable container and its own volume through inspected metadata."""
    _, port, _ = admit_redis_endpoint(resource, environ=environ)
    return _check_container(inspect(resource.container), name=resource.container, image_id=resource.image_id,
                            container_port="6379/tcp", host_port=port, volume=resource.volume, destination="/data")


def admit_postgres_resource(section: Mapping[str, Any], inspect: Callable[[str], Mapping[str, Any]]) -> dict[str, Any]:
    admit_loopback(section["host"], section["port"], PROTECTED_POSTGRES_PORTS)
    return _check_container(inspect(section["container"]), name=section["container"], image_id=section["image_id"],
                            container_port="5432/tcp", host_port=section["port"], volume=section["volume"],
                            destination="/var/lib/postgresql/data")


def _redact(text: str) -> tuple[str, int]:
    count = 0
    for label, pattern in _SECRET_PATTERNS:
        text, hits = pattern.subn(f"[REDACTED:{label}]", text)
        count += hits
    return text, count


def sanitize(value: Any) -> tuple[Any, int]:
    """JSON values only; strings redacted and bounded."""
    if value is None or isinstance(value, bool | int | float):
        return value, 0
    if isinstance(value, str):
        text, count = _redact(value)
        return (text if len(text) <= _MAX_STRING else text[:_MAX_STRING] + "...[truncated]"), count
    if isinstance(value, Mapping):
        out, total = {}, 0
        for key, item in value.items():
            clean_key, key_hits = sanitize(str(key))
            out[clean_key], hits = sanitize(item)
            total += key_hits + hits
        return out, total
    if isinstance(value, list | tuple | set | frozenset):
        items = [sanitize(item) for item in (sorted(value, key=str) if isinstance(value, set | frozenset) else value)]
        return [item for item, _ in items], sum(hits for _, hits in items)
    return sanitize(repr(value))


def record_bytes(result: ProbeResult, ram_only: set[str]) -> bytes:
    data, count = sanitize(asdict(result))
    data["redactions"] = result.redactions + count
    text = json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    for body in ram_only:
        if len(body) >= _MIN_BODY and (body in text or json.dumps(body, ensure_ascii=True)[1:-1] in text):
            raise PersistenceRefused("record would contain a RAM-only synthetic body")
    return text.encode("ascii")


def write_attempt(result: ProbeResult, out_dir: Path, ram_only: set[str] | None = None) -> Path:
    """Write once: an existing record is never replaced, and a partial write never takes the final name."""
    try:
        payload = record_bytes(result, ram_only or set())
    except PersistenceRefused as refused:
        stripped = ProbeResult(kind=result.kind, run_label=result.run_label, config_sha256=result.config_sha256,
                               outcome="ERROR", disposition="open", attempt_id=result.attempt_id,
                               started_utc=result.started_utc, ended_utc=result.ended_utc, source=result.source,
                               environment=result.environment, limitations=[str(refused)], owner=result.owner)
        payload = record_bytes(stripped, set())
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"{result.kind}-{result.started_utc[:10]}-{result.attempt_id}.json"
    partial = final.with_name(final.name + ".partial")
    with partial.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(partial, final)  # fails if the final name exists, on Windows and POSIX alike
    finally:
        partial.unlink()
    return final


def _environment() -> dict[str, Any]:
    return {"python": sys.version.split()[0], "implementation": platform.python_implementation(),
            "system": platform.system(), "release": platform.release(), "machine": platform.machine()}


ProbeBody = Callable[[ProbeContext, ProbeResult], None]


def _bodies() -> dict[str, ProbeBody]:
    from tools.plan12_memory import client_probe, redis_probe

    return {"packages": run_packages, "embedding": run_embedding, "redis": redis_probe.run_redis,
            "postgres": run_postgres, "zed": client_probe.run_zed}


def run_probe(kind: str, config: ProbeConfig, *, source: Mapping[str, Any] | None = None,
              bodies: Mapping[str, ProbeBody] | None = None, grace_seconds: float = 5.0) -> tuple[ProbeResult, ProbeContext]:
    """Run one probe body under its deadline. Any failure becomes an attributable outcome, never an exception."""
    if kind not in KINDS:
        raise ConfigError(f"unknown probe kind {kind!r}")
    result = ProbeResult(kind=kind, run_label=config.run_label, config_sha256=config.sha256,
                         source=dict(source or {}), environment=_environment(), started_utc=_utc())
    context = ProbeContext(config=config)
    body = (bodies if bodies is not None else _bodies())[kind]
    failure: list[Exception] = []

    def target() -> None:
        try:
            body(context, result)
        except Exception as error:
            failure.append(error)

    worker = threading.Thread(target=target, name=f"plan12-probe-{kind}", daemon=True)
    worker.start()
    worker.join(config.timeout_seconds)
    if worker.is_alive():
        context.cancelled.set()
        worker.join(grace_seconds)
        result.outcome = "INCONCLUSIVE"
        result.limitations.append(f"timed out after {config.timeout_seconds}s; stopped after cancel: {not worker.is_alive()}")
    elif failure:
        error = failure[0]
        result.outcome = "INCONCLUSIVE" if isinstance(error, TimeoutError) else "ERROR"
        result.limitations.append(f"{type(error).__name__}: {error}")
    elif result.outcome not in OUTCOMES or result.disposition not in DISPOSITIONS:
        result.limitations.append(f"malformed probe result: outcome {result.outcome!r}, disposition {result.disposition!r}")
        result.outcome, result.disposition = "INCONCLUSIVE", "open"
    if result.outcome == "PASS" and result.disposition == "handoff":
        result.limitations.append("a handed-off probe cannot be a PASS")
        result.outcome = "INCONCLUSIVE"
    for description, action in reversed(context.cleanups):
        try:
            action()
            result.cleanup.append({"action": description, "status": "done"})
        except Exception as error:  # recorded; a cleanup failure never hides the probe result
            result.cleanup.append({"action": description, "status": f"failed: {type(error).__name__}: {error}"})
    result.ended_utc = _utc()
    return result, context


# --- native helpers (live probes only; unit tests inject doubles) ---

Runner = Callable[..., subprocess.CompletedProcess[str]]


def run_command(argv: Sequence[str], timeout: float, env: Mapping[str, str] | None = None,
                stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, check=False, env=None if env is None else {**os.environ, **env})


def docker_inspect(name: str, runner: Runner = run_command) -> dict[str, Any]:
    completed = runner(["docker", "inspect", "--type", "container", name], 60, None)
    if completed.returncode:
        raise AdmissionError(f"container {name!r} cannot be inspected")
    return json.loads(completed.stdout)[0]


def _tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _child_json(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """The child prints one JSON object on its last stdout line; anything else is a malformed native result."""
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    try:
        value = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        raise ValueError(f"malformed child result (exit {completed.returncode})") from None
    if not isinstance(value, dict):
        raise ValueError("malformed child result: not an object")
    return value


_CHILD = Path(__file__).with_name("probe_child.py")


def run_packages(context: ProbeContext, result: ProbeResult, runner: Runner = run_command) -> None:
    """P1: resolve each candidate alone (wheels only) for this interpreter, install the supported set by hash, smoke it."""
    section = context.config.sections.get("packages") or {}
    index_url, candidates = section.get("index_url", ""), list(section.get("candidates", []))
    venv = Path(section.get("venv", "tmp/plan12-probe-venv"))
    if not allowed_url(index_url, context.config) or not candidates:
        result.outcome, result.disposition = "UNRUN", "open"
        result.limitations.append("packages section needs an allowed https index_url and candidates")
        return
    result.observations["inputs"] = section.get("inputs", {})
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    common = ["--index-url", index_url, "--python-version", python_version, "--only-binary", ":all:", "--no-header"]
    matrix: dict[str, Any] = {}
    supported: list[str] = []
    for name in candidates:
        context.check()
        completed = runner(["uv", "pip", "compile", "-", *common], 300, None, name + "\n")
        pins = [line.split()[0] for line in completed.stdout.splitlines() if "==" in line and not line.startswith(("#", " "))]
        matrix[name] = {"resolved": completed.returncode == 0, "pins": pins,
                        "error": "" if completed.returncode == 0 else completed.stderr.strip().splitlines()[-1:]}
        if completed.returncode == 0:
            supported.append(name)
    result.observations["resolution"] = matrix
    if not supported:
        result.outcome, result.disposition = "FAIL", "concluded"
        return
    requirements = venv.with_name(venv.name + "-requirements.txt")
    requirements.parent.mkdir(parents=True, exist_ok=True)
    pinned = [f"{name}=={version}" for name, version in (section.get("inputs") or {}).items()]
    compiled = runner(["uv", "pip", "compile", "-", "--generate-hashes", *common, "-o", str(requirements)], 300, None,
                      "\n".join(supported + pinned) + "\n")
    if compiled.returncode:
        result.outcome, result.disposition = "FAIL", "concluded"
        result.limitations.append("the supported candidates do not resolve together: " + compiled.stderr.strip()[-400:])
        return
    if venv.exists():
        shutil.rmtree(venv)
    for argv in (["uv", "venv", "--python", sys.executable, str(venv)],
                 ["uv", "pip", "install", "--python", str(_venv_python(venv)), "--require-hashes", "--index-url",
                  index_url, "--only-binary", ":all:", "-r", str(requirements)]):
        context.check()
        completed = runner(argv, 900, None)
        if completed.returncode:
            result.outcome, result.disposition = "FAIL", "concluded"
            result.limitations.append(f"{argv[1]} failed: " + completed.stderr.strip()[-400:])
            return
    installed_bytes = _tree_bytes(venv)
    result.observations["venv_bytes"] = installed_bytes
    smoke = _child_json(runner([str(_venv_python(venv)), str(_CHILD), "smoke", *supported, *(section.get("inputs") or {})],
                                  600, None))
    result.observations["smoke"] = smoke
    unsupported = [name for name in candidates if name not in supported]
    failed = [name for name, row in smoke.get("packages", {}).items() if not row.get("ok")]
    if installed_bytes > context.config.max_download_bytes:
        result.limitations.append(f"isolated venv is {installed_bytes} bytes, over the {context.config.max_download_bytes} limit")
    result.outcome = "PASS" if not unsupported and not failed and installed_bytes <= context.config.max_download_bytes else "FAIL"
    result.disposition = "concluded"
    result.follow_up = "M1 re-runs any unsupported combination before relying on it; M3 owns the encryption dependency"


def run_embedding(context: ProbeContext, result: ProbeResult, runner: Runner = run_command) -> None:
    """P2: embed a finite synthetic corpus in the isolated venv, then cancel/resume and owner-exit/restart its cursor."""
    section = context.config.sections.get("embedding") or {}
    venv = Path(section.get("venv", "tmp/plan12-probe-venv"))
    python = _venv_python(venv)
    if not python.exists() or not section.get("model"):
        result.outcome, result.disposition = "UNRUN", "open"
        result.limitations.append("needs the P1 isolated venv and an embedding model name")
        return
    work = Path(section.get("work_dir", "tmp/plan12-probe-embedding")) / result.attempt_id[:12]
    work.mkdir(parents=True, exist_ok=True)
    base = [str(python), str(_CHILD), "embed", "--model", section["model"], "--cache", section.get("cache_dir", "tmp/plan12-probe-models"),
            "--items", str(section.get("items", 2000)), "--batch", str(section.get("batch", 64))]
    hf_env = {"HF_HUB_DISABLE_TELEMETRY": "1"}
    full = _child_json(runner([*base, "--cursor", str(work / "full.json")], context.config.timeout_seconds, hf_env))
    result.observations["full_run"] = full
    if not full.get("ok"):
        result.outcome, result.disposition = "FAIL", "concluded"
        return
    offline = {**hf_env, "HF_HUB_OFFLINE": "1"}
    stop_after = int(section.get("stop_after_batches", 5))
    cancel = _child_json(runner([*base, "--cursor", str(work / "cancel.json"), "--stop-after", str(stop_after)],
                                context.config.timeout_seconds, offline))
    resumed = _child_json(runner([*base, "--cursor", str(work / "cancel.json")], context.config.timeout_seconds, offline))
    killed = _owner_exit(base + ["--cursor", str(work / "killed.json")], work / "killed.json", stop_after, offline,
                         context.config.timeout_seconds)
    restarted = _child_json(runner([*base, "--cursor", str(work / "killed.json")], context.config.timeout_seconds, offline))
    result.observations["cancel_resume"] = {"cancelled": cancel, "resumed": resumed,
                                            "identical": resumed.get("output_sha256") == full.get("output_sha256")}
    result.observations["owner_exit_restart"] = {"killed": killed, "restarted": restarted,
                                                 "identical": restarted.get("output_sha256") == full.get("output_sha256")}
    identical = result.observations["cancel_resume"]["identical"] and result.observations["owner_exit_restart"]["identical"]
    result.outcome = "PASS" if identical and cancel.get("status") == "stopped" and killed.get("killed") else "FAIL"
    result.disposition = "concluded"
    result.limitations.append("a feasibility cursor, not the persisted-generation production indexer (M1)")
    result.follow_up = "M1 qualifies the production worker and model choice on the real corpus"


def _owner_exit(argv: list[str], cursor: Path, after: int, env: Mapping[str, str], timeout: float) -> dict[str, Any]:
    """Start the worker, kill it once its cursor passes `after` batches: the owner exits without warning."""
    process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, **env})
    deadline = time.monotonic() + timeout
    seen = 0
    try:
        while time.monotonic() < deadline and process.poll() is None:
            try:
                seen = json.loads(cursor.read_text(encoding="utf-8")).get("next_batch", 0)
            except (OSError, json.JSONDecodeError):
                seen = 0
            if seen >= after:
                process.kill()
                break
            time.sleep(0.05)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(30)
    return {"killed": seen >= after, "batches_at_kill": seen, "returncode": process.returncode}


def run_postgres(context: ProbeContext, result: ProbeResult, runner: Runner = run_command,
                 connect: Callable[..., Any] | None = None) -> None:
    """P4: native driver commit/readback, rollback, failure and disconnect/reconnect on the released disposable server."""
    section = context.config.sections.get("postgres")
    if not section:
        result.outcome, result.disposition = "UNRUN", "open"
        result.limitations.append("no released postgres section")
        return
    identity = admit_postgres_resource(section, lambda name: docker_inspect(name, runner))
    password = os.environ.get(section.get("credential_env", ""), "")
    if not password:
        raise AdmissionError("postgres password environment variable is not set")
    context.ram_only.add(password)
    import psycopg

    connect = connect or psycopg.connect
    params = {"host": section["host"], "port": section["port"], "user": section["user"], "password": password,
              "dbname": section["database"], "connect_timeout": 10}
    observations: dict[str, Any] = {"identity": identity, "driver": {"psycopg": psycopg.__version__,
                                                                       "libpq": psycopg.pq.version()}}
    checks: dict[str, bool] = {}
    with connect(**params) as conn:
        observations["server_version"] = conn.info.server_version
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS p127probe")
            cur.execute("CREATE TABLE IF NOT EXISTS p127probe.rows (id text PRIMARY KEY, n int NOT NULL)")
        conn.commit()
        token = uuid.uuid4().hex
        with conn.cursor() as cur:
            cur.execute("INSERT INTO p127probe.rows VALUES (%s, 1)", (f"commit-{token}",))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("INSERT INTO p127probe.rows VALUES (%s, 2)", (f"rollback-{token}",))
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM p127probe.rows WHERE id LIKE %s", (f"%{token}",))
            found = sorted(row[0].split("-")[0] for row in cur.fetchall())
        checks["commit_readback"] = "commit" in found
        checks["rollback_discards"] = "rollback" not in found
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO p127probe.rows VALUES (%s, 3)", (f"commit-{token}",))
            checks["duplicate_rejected"] = False
        except psycopg.errors.UniqueViolation:
            checks["duplicate_rejected"] = True
            conn.rollback()
    restarted = runner(["docker", "restart", "--time", "10", section["container"]], 120, None)
    checks["server_restarted"] = restarted.returncode == 0
    reconnect_started = time.monotonic()
    reconnected = None
    while time.monotonic() - reconnect_started < 60 and reconnected is None:
        try:
            reconnected = connect(**params)
        except psycopg.OperationalError:
            time.sleep(0.5)
    observations["reconnect_seconds"] = round(time.monotonic() - reconnect_started, 3)
    if reconnected is not None:
        with reconnected as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM p127probe.rows WHERE id = %s", (f"commit-{token}",))
            checks["committed_row_survives_restart"] = cur.fetchone()[0] == 1
    checks["reconnected"] = reconnected is not None
    observations["admission_reidentified"] = admit_postgres_resource(section, lambda name: docker_inspect(name, runner))
    try:
        connect(**{**params, "port": section["port"] + 1, "connect_timeout": 3})
        checks["closed_port_fails_fast"] = False
    except psycopg.OperationalError:
        checks["closed_port_fails_fast"] = True
    observations["checks"] = checks
    result.observations.update(observations)
    result.outcome = "PASS" if all(checks.values()) else "FAIL"
    result.disposition = "concluded"
    result.limitations.append("readiness only: no ledger, outbox, durability or completeness claim (M0b)")
    result.follow_up = "M0b builds the durable ledger on this driver/server pairing"


def _source_identity() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()

    try:
        return {"head": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError) as error:
        return {"head": "UNKNOWN", "error": type(error).__name__}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except (OSError, ConfigError) as error:
        print(f"config refused: {error}", file=sys.stderr)
        return 2
    result, context = run_probe(args.kind, config, source=_source_identity())
    path = write_attempt(result, args.out, context.ram_only)
    print(f"{result.kind}: {result.outcome} ({result.disposition}) -> {path.as_posix()}")
    return 0 if result.outcome in {"PASS", "FAIL", "UNRUN", "UNAVAILABLE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
