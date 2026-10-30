"""Plan 12.7 memory feasibility probes (M0a-3): config admission, attributable records and dispatch.

Each probe runs under a validated `ProbeConfig` and returns a `ProbeResult`. Execution outcome and
administrative disposition are separate fields: a handed-off probe is never a PASS. Records are
sanitized and written once; a later attempt never replaces an earlier one. Synthetic bodies stay in
RAM: a record that would contain one is refused. Nothing runs at import time.

    python -m tools.plan12_memory.probes --kind packages --config reports/plan12-memory-feasibility/probe-config.json

The package, embedding and Postgres bodies live here; Redis is `redis_probe`, ACP/Zed is `client_probe`.
Candidate packages and the embedding model run only in an isolated probe venv, through `probe_child`.
Every native wait is bounded by the probe deadline, and files are created or removed only under the
released `tmp/plan12-probe*` directories.
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
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
KINDS = ("packages", "embedding", "redis", "postgres", "zed")
# The runner's own containment self-test, never a feasibility probe.
SELFTEST = "selftest"
OUTCOMES = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "UNRUN", "UNAVAILABLE", "ERROR"})
DISPOSITIONS = frozenset({"concluded", "handoff", "open"})
CONFIG_ENV = "OPTIMUS_PLAN12_PROBE_CONFIG"
# The shared test/product Redis: every database on it, under every loopback alias, is refused.
PROTECTED_REDIS_PORTS = frozenset({6379})
# Read only to protect what they name, never as a fallback endpoint.
_SHARED_REDIS_ENV = ("OPTIMUS_REDIS_URL", "REDIS_URL")
# The default PostgreSQL port; evidence-handoff and any local server keep it.
PROTECTED_POSTGRES_PORTS = frozenset({5432})
REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASED_ROOT = REPO_ROOT / "tmp"
RELEASED_PREFIX = "plan12-probe"
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
_TOP_KEYS = {"schema_version", "run_label", "authorization", "limits", "allowed_hosts", "allowed_licenses", "redis",
             "postgres", "zed", "packages", "embedding", "selftest", "targets"}
_REDIS_KEYS = {"endpoint", "container", "image", "image_id", "volume", "username", "credential_env"}
_POSTGRES_KEYS = {"host", "port", "container", "image_id", "volume", "user", "database", "credential_env"}
REDIS_TARGETS = ("items", "vector_dimensions", "item_bytes", "concurrency", "maxmemory_bytes", "admission_reserve_bytes",
                 "physical_ram_bytes", "disk_bytes", "ack_latency_p95_ms", "projection_latency_p95_ms",
                 "restart_to_usable_seconds", "logical_purge_seconds", "physical_erasure_seconds")
# Trove classifiers mapped to the SPDX identifiers the allowlist names.
_CLASSIFIER_LICENSES = {"MIT License": "MIT", "Apache Software License": "Apache-2.0", "BSD License": "BSD-3-Clause",
                        "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0", "ISC License (ISCL)": "ISC",
                        "Python Software Foundation License": "PSF-2.0", "The Unlicense (Unlicense)": "Unlicense",
                        "zlib/libpng License": "Zlib", "Historical Permission Notice and Disclaimer (HPND)": "HPND"}


class ConfigError(ValueError):
    """The probe config is malformed; nothing ran."""


class AdmissionError(RuntimeError):
    """An endpoint, resource, path or artifact was refused before it was used."""


class PersistenceRefused(RuntimeError):
    """A record would have carried a RAM-only body; it was not written."""


class MalformedEvidence(ValueError):
    """Native evidence could not be validated; the result is INCONCLUSIVE, never a pass or a fail."""


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
    grace_seconds: float
    max_download_bytes: int
    allowed_hosts: tuple[str, ...]
    allowed_licenses: tuple[str, ...]
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
    """What a probe body receives: its config, a deadline and cancel signal, RAM-only bodies and a cleanup journal."""

    config: ProbeConfig
    deadline: float = field(default_factory=lambda: time.monotonic() + 3600)
    cancelled: threading.Event = field(default_factory=threading.Event)
    ram_only: set[str] = field(default_factory=set)
    cleanups: list[tuple[str, Callable[[], object]]] = field(default_factory=list)

    def on_cleanup(self, description: str, action: Callable[[], object]) -> None:
        self.cleanups.append((description, action))

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def check(self) -> None:
        if self.cancelled.is_set() or self.remaining() <= 0:
            raise TimeoutError("probe cancelled at its deadline")

    def timeout(self, cap: float) -> float:
        """A native call's timeout: its own cap, never past the probe deadline."""
        self.check()
        return min(cap, self.remaining())


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


def _strings(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    values = data.get(key, [])
    if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
        raise ConfigError(f"{key} must be a list of non-empty strings")
    return tuple(values)


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
    grace = limits.get("grace_seconds", 5)
    if not isinstance(grace, int | float) or isinstance(grace, bool) or grace <= 0:
        raise ConfigError("limits.grace_seconds must be a positive number")
    max_download = _require(limits, "max_download_bytes", int, "limits")
    if timeout <= 0 or max_download < 0:
        raise ConfigError("limits must be positive")
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
        grace_seconds=float(grace),
        max_download_bytes=max_download,
        allowed_hosts=tuple(host.lower() for host in _strings(data, "allowed_hosts")),
        allowed_licenses=_strings(data, "allowed_licenses"),
        sections={key: data[key] for key in ("postgres", "zed", "packages", "embedding", "selftest") if key in data},
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


def released_path(value: str | Path) -> Path:
    """A path the probes may create or remove: under repo `tmp/plan12-probe*`, with no alias anywhere on the way."""
    path = Path(value)
    absolute = Path(os.path.normpath(path if path.is_absolute() else REPO_ROOT / path))
    resolved = absolute.resolve()
    if os.path.normcase(str(resolved)) != os.path.normcase(str(absolute)):
        raise AdmissionError(f"{path.as_posix()} goes through a link or alias")
    try:
        relative = resolved.relative_to(RELEASED_ROOT.resolve())
    except ValueError:
        raise AdmissionError(f"{path.as_posix()} is outside the released tmp/{RELEASED_PREFIX}* directories") from None
    if not relative.parts or not relative.parts[0].startswith(RELEASED_PREFIX):
        raise AdmissionError(f"{path.as_posix()} is outside the released tmp/{RELEASED_PREFIX}* directories")
    return resolved


def remove_released(value: str | Path) -> None:
    target = released_path(value)  # re-verified immediately before deletion
    if target.exists():
        shutil.rmtree(target)


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


_BARE_HEX = re.compile(r"[0-9a-f]{32,}")


def tag_digests(value: Any) -> Any:
    """Render each bare hex digest (SHA-256, Git and container ids) as `hex:<digest>`: still exact, self-describing,
    and not mistaken by the secret scan for key material, so records need no baseline exception."""
    if isinstance(value, str):
        return f"hex:{value}" if _BARE_HEX.fullmatch(value) else value
    if isinstance(value, dict):
        return {key: tag_digests(item) for key, item in value.items()}
    if isinstance(value, list):
        return [tag_digests(item) for item in value]
    return value


def record_bytes(result: ProbeResult, ram_only: set[str]) -> bytes:
    raw = json.dumps(asdict(result), ensure_ascii=True, default=repr)
    if any(len(body) >= _MIN_BODY and json.dumps(body, ensure_ascii=True)[1:-1] in raw for body in ram_only):
        raise PersistenceRefused("record would contain a RAM-only synthetic body")
    data, count = sanitize(asdict(result))
    data["redactions"] = result.redactions + count
    text = json.dumps(tag_digests(data), ensure_ascii=True, indent=2, sort_keys=True) + "\n"
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
            "postgres": run_postgres, "zed": client_probe.run_zed, SELFTEST: run_selftest}


def _run_cleanups(context: ProbeContext, journal: list[dict[str, Any]]) -> None:
    for description, action in reversed(context.cleanups):
        try:
            action()
            journal.append({"action": description, "status": "done"})
        except Exception as error:  # recorded; a cleanup failure never hides the probe result
            journal.append({"action": description, "status": f"failed: {type(error).__name__}: {error}"})
    context.cleanups.clear()


def run_probe(kind: str, config: ProbeConfig, *, source: Mapping[str, Any] | None = None,
              bodies: Mapping[str, ProbeBody] | None = None, grace_seconds: float | None = None,
              ) -> tuple[ProbeResult, ProbeContext]:
    """Run one probe body under its deadline. Any failure becomes an attributable outcome, never an exception.

    Cleanups run only once the body has stopped, or as the last means of stopping it. A body that is
    still running after that is abandoned: its result object is never returned or recorded.
    """
    if kind not in (*KINDS, SELFTEST):
        raise ConfigError(f"unknown probe kind {kind!r}")
    grace_seconds = config.grace_seconds if grace_seconds is None else grace_seconds
    started = _utc()
    working = ProbeResult(kind=kind, run_label=config.run_label, config_sha256=config.sha256,
                          source=dict(source or {}), environment=_environment(), started_utc=started)
    context = ProbeContext(config=config, deadline=time.monotonic() + config.timeout_seconds)
    body = (bodies if bodies is not None else _bodies())[kind]
    failure: list[Exception] = []

    def target() -> None:
        try:
            body(context, working)
        except Exception as error:
            failure.append(error)

    worker = threading.Thread(target=target, name=f"plan12-probe-{kind}", daemon=True)
    worker.start()
    worker.join(config.timeout_seconds)
    cleanup: list[dict[str, Any]] = []
    if worker.is_alive():
        context.cancelled.set()
        worker.join(grace_seconds)
        if worker.is_alive():
            _run_cleanups(context, cleanup)  # closing clients and killing children unblocks native waits
            worker.join(grace_seconds)
    stopped = not worker.is_alive()
    if not stopped:
        result = ProbeResult(kind=kind, run_label=config.run_label, config_sha256=config.sha256,
                             attempt_id=working.attempt_id, source=dict(source or {}), environment=working.environment,
                             started_utc=started, outcome="INCONCLUSIVE", disposition="open")
        result.limitations.append(f"timed out after {config.timeout_seconds}s and did not stop; partial observations discarded")
        result.cleanup = cleanup
        result.ended_utc = _utc()
        return result, context
    result = working
    if context.cancelled.is_set() or (failure and isinstance(failure[0], TimeoutError | subprocess.TimeoutExpired)):
        result.outcome, result.disposition = "INCONCLUSIVE", "open"
        result.limitations.append(f"timed out after {config.timeout_seconds}s; stopped after cancel")
    elif failure:
        error = failure[0]
        result.outcome = ("INCONCLUSIVE" if isinstance(error, TimeoutError | subprocess.TimeoutExpired | MalformedEvidence)
                          else "ERROR")
        result.disposition = "open"
        result.limitations.append(f"{type(error).__name__}: {error}")
    elif result.outcome not in OUTCOMES or result.disposition not in DISPOSITIONS:
        result.limitations.append(f"malformed probe result: outcome {result.outcome!r}, disposition {result.disposition!r}")
        result.outcome, result.disposition = "INCONCLUSIVE", "open"
    if result.outcome == "PASS" and result.disposition == "handoff":
        result.limitations.append("a handed-off probe cannot be a PASS")
        result.outcome = "INCONCLUSIVE"
    _run_cleanups(context, cleanup)
    result.cleanup = cleanup
    result.ended_utc = _utc()
    return result, context


def verdict(checks: Mapping[str, bool | None]) -> str:
    """FAIL if any check failed; INCONCLUSIVE if any could not be established; PASS only when every check held."""
    values = list(checks.values())
    return "FAIL" if False in values else "INCONCLUSIVE" if None in values or not values else "PASS"


# --- native helpers (live probes only; unit tests inject doubles) ---

Runner = Callable[..., subprocess.CompletedProcess[str]]
Fetch = Callable[[str, float], Any]


def run_command(argv: Sequence[str], timeout: float, env: Mapping[str, str] | None = None,
                stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """subprocess.run kills the child when its timeout expires, so no owned child outlives its bound."""
    return subprocess.run(list(argv), input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, check=False, env=None if env is None else {**os.environ, **env})


def fetch_json(url: str, timeout: float) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - callers pass allowlisted https URLs
        return json.loads(response.read(8 * 1024 * 1024))


def docker_inspect(name: str, runner: Runner = run_command, timeout: float = 60) -> dict[str, Any]:
    completed = runner(["docker", "inspect", "--type", "container", name], timeout, None)
    if completed.returncode:
        raise AdmissionError(f"container {name!r} cannot be inspected")
    return json.loads(completed.stdout)[0]


def _tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


_HEX64 = re.compile(r"[0-9a-f]{64}")
_TYPE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,80}")


def child_json(completed: subprocess.CompletedProcess[str], mode: str, names: Sequence[str] = ()) -> dict[str, Any]:
    """Validate a probe_child result for its mode; anything else is malformed evidence."""
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    try:
        value = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        raise MalformedEvidence(f"{mode}: no JSON result (exit {completed.returncode})") from None
    if completed.returncode or not isinstance(value, dict):
        raise MalformedEvidence(f"{mode}: child exited {completed.returncode}")
    if not value.get("ok"):
        error = str(value.get("error", ""))
        # Only a bare exception type crosses this boundary; free text could quote input bodies.
        raise MalformedEvidence(f"{mode}: child reported {error if _TYPE_NAME.fullmatch(error) else 'an unprintable error'}")
    if mode == "smoke":
        rows = value.get("packages")
        if not isinstance(rows, dict) or set(rows) != set(names) or not all(
                isinstance(row, dict) and isinstance(row.get("ok"), bool) and (not row["ok"] or isinstance(row.get("version"), str))
                for row in rows.values()):
            raise MalformedEvidence("smoke: package rows are missing or malformed")
    elif mode == "embed":
        status = value.get("status")
        if status == "complete":
            if not _HEX64.fullmatch(str(value.get("output_sha256", ""))) or not isinstance(value.get("dimensions"), int):
                raise MalformedEvidence("embed: a complete run needs an output hash and dimensions")
        elif status != "stopped" or not isinstance(value.get("next_batch"), int):
            raise MalformedEvidence("embed: status must be complete or stopped at a batch")
    elif mode == "model-info":
        if not isinstance(value.get("files"), list) or not value.get("revision") or not value.get("repo"):
            raise MalformedEvidence("model-info: repo, revision and file list are required")
    elif mode == "model-fetch":
        if not isinstance(value.get("files"), dict) or not isinstance(value.get("bytes"), int) or not isinstance(
                value.get("snapshot_path"), str):
            raise MalformedEvidence("model-fetch: file digests, byte count and snapshot path are required")
    return value


_SPDX_EXPRESSION = re.compile(r"[A-Za-z0-9.+-]+(?:\s+(?:AND|OR)\s+[A-Za-z0-9.+-]+)*")
_TEXT_LICENSES = {"MIT License": "MIT", "3-Clause BSD License": "BSD-3-Clause", "BSD 3-Clause": "BSD-3-Clause",
                  "BSD-3-Clause License": "BSD-3-Clause", "Apache 2.0": "Apache-2.0", "Apache License 2.0": "Apache-2.0",
                  "Apache License, Version 2.0": "Apache-2.0", "Apache Software License": "Apache-2.0"}


def license_ids(info: Mapping[str, Any]) -> set[str]:
    """SPDX identifiers from PyPI metadata: License-Expression first, then trove classifiers, then a short License
    field (itself an SPDX expression or a known license name). Empty when the metadata names none."""
    expression = str(info.get("license_expression") or "")
    if expression:
        return {part.strip("() ") for part in re.split(r"\s+(?:AND|OR|WITH)\s+", expression) if part.strip("() ")}
    found = {_CLASSIFIER_LICENSES[name] for value in info.get("classifiers") or []
             if value.startswith("License ::") and (name := value.split("::")[-1].strip()) in _CLASSIFIER_LICENSES}
    text = str(info.get("license") or "").strip()
    if not found and text and len(text) <= 80 and "\n" not in text:
        if text in _TEXT_LICENSES:
            found = {_TEXT_LICENSES[text]}
        elif _SPDX_EXPRESSION.fullmatch(text):
            found = set(re.split(r"\s+(?:AND|OR)\s+", text))
    return found


def _compiled_pins(text: str) -> dict[str, dict[str, Any]]:
    """`name==version` lines from uv pip compile, with any `--hash=sha256:` lines that follow them."""
    pins: dict[str, dict[str, Any]] = {}
    current = None
    for line in text.splitlines():
        if line and not line.startswith(("#", " ")) and "==" in line:
            name, version = line.split()[0].split("==", 1)
            current = pins.setdefault(name.lower(), {"version": version, "hashes": []})
        elif current is not None and "--hash=sha256:" in line:
            current["hashes"].append(line.split("--hash=sha256:", 1)[1].split()[0].strip("\\ "))
    return pins


def _compatible_wheel(files: list[Mapping[str, Any]], hashes: Sequence[str]) -> Mapping[str, Any] | None:
    from packaging.tags import sys_tags
    from packaging.utils import parse_wheel_filename

    priority = {tag: rank for rank, tag in enumerate(sys_tags())}
    best = None
    for item in files:
        name, digest = item.get("filename", ""), (item.get("digests") or {}).get("sha256")
        if not name.endswith(".whl") or digest not in hashes:
            continue
        rank = min((priority[tag] for tag in parse_wheel_filename(name)[3] if tag in priority), default=None)
        if rank is not None and (best is None or rank < best[0]):
            best = (rank, item)
    return None if best is None else best[1]


def run_packages(context: ProbeContext, result: ProbeResult, runner: Runner = run_command,
                 fetch: Fetch = fetch_json) -> None:
    """P1 in two phases. Discovery resolves each candidate alone (wheels only) and gates every pin's license.
    Admission binds one compatible wheel per pin by hash and size, refuses the set over the download
    budget, and only then installs it, by hash, into the released isolated venv and smokes it there."""
    config, section = context.config, context.config.sections.get("packages") or {}
    index_url, candidates = section.get("index_url", ""), list(section.get("candidates", []))
    if not allowed_url(index_url, config) or not candidates or not allowed_url("https://pypi.org/pypi", config):
        result.outcome, result.disposition = "UNRUN", "open"
        result.limitations.append("packages needs an allowed https index_url, pypi.org metadata access and candidates")
        return
    venv = released_path(section.get("venv", "tmp/plan12-probe-venv"))
    inputs = dict(section.get("inputs") or {})
    result.observations["inputs"] = inputs
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    common = ["--index-url", index_url, "--python-version", python_version, "--only-binary", ":all:", "--no-header",
              "--no-annotate"]
    metadata: dict[tuple[str, str], Mapping[str, Any]] = {}

    def release(name: str, version: str) -> Mapping[str, Any]:
        if (name, version) not in metadata:
            metadata[name, version] = fetch(f"https://pypi.org/pypi/{name}/{version}/json", context.timeout(60))
        return metadata[name, version]

    approved = set(config.allowed_licenses)
    qualifications = dict(section.get("license_qualifications") or {})

    def licenses_of(pin: str, version: str) -> tuple[list[str], str]:
        """Metadata first. A pin whose metadata names no license is admitted only by a recorded qualification
        for that exact version and wheel digest (a human reading of its license file), never by heuristics."""
        data = release(pin, version)
        ids = sorted(license_ids(data.get("info") or {}))
        if ids:
            return ids, "metadata"
        qualified = qualifications.get(f"{pin}=={version}") or {}
        digest = str(qualified.get("wheel_sha256", "")).removeprefix("sha256:")
        published = {(item.get("digests") or {}).get("sha256") for item in data.get("urls") or []}
        if qualified.get("license") and digest and digest in published:
            return [str(qualified["license"])], f"recorded qualification of wheel sha256:{digest}"
        return [], "no license metadata and no recorded qualification for a published wheel"

    matrix: dict[str, Any] = {}
    admitted: list[str] = []
    for name in candidates:
        completed = runner(["uv", "pip", "compile", "-", *common], context.timeout(300), None, name + "\n")
        pins = _compiled_pins(completed.stdout) if completed.returncode == 0 else {}
        row: dict[str, Any] = {"resolved": completed.returncode == 0, "pins": {k: v["version"] for k, v in pins.items()}}
        if completed.returncode:
            row["error"] = completed.stderr.strip().splitlines()[-1:]
        else:
            found = {pin: licenses_of(pin, data["version"]) for pin, data in pins.items()}
            licenses = {pin: ids for pin, (ids, _) in found.items()}
            row["licenses"] = licenses
            row["license_sources"] = {pin: source for pin, (_, source) in found.items() if source != "metadata"}
            row["unapproved"] = sorted(pin for pin, ids in licenses.items() if not ids or not set(ids) <= approved)
            if not row["unapproved"]:
                admitted.append(name)
        matrix[name] = row
    result.observations["discovery"] = matrix
    if not admitted:
        result.outcome, result.disposition = "FAIL", "concluded"
        result.limitations.append("no candidate resolved with approved licenses; nothing was installed")
        return
    joint = runner(["uv", "pip", "compile", "-", "--generate-hashes", *common], context.timeout(300), None,
                   "\n".join(admitted + [f"{k}=={v}" for k, v in inputs.items()]) + "\n")
    if joint.returncode:
        result.outcome, result.disposition = "FAIL", "concluded"
        result.limitations.append("the admitted candidates do not resolve together: " + joint.stderr.strip()[-400:])
        return
    artifacts, unbound, unapproved = {}, [], []
    for pin, data in _compiled_pins(joint.stdout).items():
        ids, source = licenses_of(pin, data["version"])
        bound = (qualifications.get(f"{pin}=={data['version']}") or {}).get("wheel_sha256", "").removeprefix("sha256:")
        wheel = _compatible_wheel(release(pin, data["version"]).get("urls") or [], data["hashes"])
        # A qualification covers only its own wheel: the one selected for install must be exactly that one.
        selected = (wheel or {}).get("digests", {}).get("sha256")
        if not ids or not set(ids) <= approved or (source != "metadata" and selected != bound):
            unapproved.append(f"{pin}=={data['version']}")
        if wheel is None:
            unbound.append(pin)
            continue
        artifacts[pin] = {"version": data["version"], "filename": wheel["filename"], "sha256": wheel["digests"]["sha256"],
                          "bytes": int(wheel.get("size") or 0)}
    total = sum(item["bytes"] for item in artifacts.values())
    result.observations["admission"] = {"artifacts": artifacts, "download_bytes": total, "unapproved": unapproved,
                                        "budget_bytes": config.max_download_bytes, "unbound": unbound}
    if unapproved or unbound or total > config.max_download_bytes or any(not item["bytes"] for item in artifacts.values()):
        result.outcome, result.disposition = "FAIL", "concluded"
        result.limitations.append("refused before install: an artifact is unlicensed, unbound, unsized or over budget")
        return
    requirements = released_path(venv.parent / (venv.name + "-requirements.txt"))
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text("".join(f"{pin}=={item['version']} --hash=sha256:{item['sha256']}\n"
                                    for pin, item in sorted(artifacts.items())), encoding="utf-8")
    remove_released(venv)
    for argv in (["uv", "venv", "--python", sys.executable, str(venv)],
                 ["uv", "pip", "install", "--python", str(_venv_python(venv)), "--require-hashes", "--no-deps",
                  "--index-url", index_url, "--only-binary", ":all:", "-r", str(requirements)]):
        completed = runner(argv, context.timeout(900), None)
        if completed.returncode:
            result.outcome, result.disposition = "FAIL", "concluded"
            result.limitations.append(f"{argv[1]} {argv[2]} failed: " + completed.stderr.strip()[-400:])
            return
    result.observations["venv_bytes"] = _tree_bytes(venv)
    names = [*admitted, *inputs]
    smoke = child_json(runner([str(_venv_python(venv)), str(_CHILD), "smoke", *names], context.timeout(600), None),
                       "smoke", names)
    result.observations["smoke"] = smoke
    failed = sorted(name for name, row in smoke["packages"].items() if not row["ok"])
    refused = sorted(set(candidates) - set(admitted))
    result.outcome = "PASS" if not failed and not refused else "FAIL"
    result.disposition = "concluded"
    result.limitations.append("the index URL and PyPI metadata hosts are allowlisted; CDN redirects are not socket-enforced")
    result.follow_up = "M1 re-runs any refused or failed combination before relying on it; M3 owns the encryption dependency"


_CHILD = Path(__file__).with_name("probe_child.py")


def run_embedding(context: ProbeContext, result: ProbeResult, runner: Runner = run_command) -> None:
    """P2: gate the model on license, source host and size before download, bind its files by digest,
    then embed a finite synthetic corpus offline and exercise cancel/resume and owner-exit/restart."""
    from tools.plan12_memory import probe_child

    config, section = context.config, context.config.sections.get("embedding") or {}
    venv = released_path(section.get("venv", "tmp/plan12-probe-venv"))
    python = _venv_python(venv)
    if not python.exists() or not section.get("model"):
        result.outcome, result.disposition = "UNRUN", "open"
        result.limitations.append("needs the P1 isolated venv and an embedding model name")
        return
    items = int(section.get("items", 2000))
    context.ram_only.update(probe_child.corpus(items))  # the child's corpus, so no record can carry any of it
    cache = released_path(section.get("cache_dir", "tmp/plan12-probe-models"))
    budget = int(section.get("max_model_bytes", 0))
    online = {"HF_HUB_DISABLE_TELEMETRY": "1", "HF_ENDPOINT": "https://huggingface.co"}
    if not allowed_url(online["HF_ENDPOINT"], config):
        result.outcome, result.disposition = "UNRUN", "open"
        result.limitations.append("huggingface.co is not an allowed host")
        return
    info = child_json(runner([str(python), str(_CHILD), "model-info", "--model", section["model"]], context.timeout(120), online),
                      "model-info")
    sizes = [item.get("size") for item in info["files"]]
    sized = bool(sizes) and all(isinstance(size, int) and not isinstance(size, bool) and size >= 0 for size in sizes)
    model_bytes = sum(sizes) if sized else None
    gate = {"repo": info["repo"], "revision": info["revision"], "license": info.get("license"), "bytes": model_bytes,
            "budget_bytes": budget, "license_approved": str(info.get("license") or "").upper() in
            {name.upper() for name in config.allowed_licenses}}
    result.observations["model_gate"] = gate
    if (not gate["license_approved"] or not budget or model_bytes is None or model_bytes > budget
            or not all(item.get("sha256") for item in info["files"])):
        result.outcome, result.disposition = "FAIL", "concluded"
        result.limitations.append("model refused before download: license, complete sizes or file digests not established")
        return
    try:
        fetched = child_json(runner([str(python), str(_CHILD), "model-fetch", "--repo", info["repo"], "--revision",
                                     info["revision"], "--cache", str(cache)], context.timeout(900), online), "model-fetch")
    except (MalformedEvidence, TimeoutError, subprocess.TimeoutExpired):
        remove_released(cache)  # a failed acquisition leaves nothing unverified behind
        raise
    expected = {item["name"]: item["sha256"] for item in info["files"]}
    matches = set(fetched["files"]) == set(expected) and all(expected[name] in fetched["files"][name] for name in expected)
    bound = matches and fetched["bytes"] <= budget
    result.observations["model_fetch"] = {"bytes": fetched["bytes"], "files_match_metadata": matches}
    if not bound:
        remove_released(cache)
        result.outcome, result.disposition = "FAIL", "concluded"
        result.limitations.append("downloaded model files did not match their published digests or the budget; cache removed")
        return
    work = released_path(Path(section.get("work_dir", "tmp/plan12-probe-embedding")) / result.attempt_id[:12])
    work.mkdir(parents=True, exist_ok=True)
    offline = {"HF_HUB_DISABLE_TELEMETRY": "1", "HF_HUB_OFFLINE": "1"}
    base = [str(python), str(_CHILD), "embed", "--model", section["model"], "--model-path", str(fetched["snapshot_path"]),
            "--items", str(items), "--batch", str(section.get("batch", 64))]
    limit = context.config.timeout_seconds

    def embed(cursor: str, *extra: str) -> dict[str, Any]:
        return child_json(runner([*base, "--cursor", str(work / cursor), *extra], context.timeout(limit), offline), "embed")

    full = embed("full.json")
    stop_after = int(section.get("stop_after_batches", 5))
    cancelled = embed("cancel.json", "--stop-after", str(stop_after))
    resumed = embed("cancel.json")
    killed = _owner_exit([*base, "--cursor", str(work / "killed.json")], work / "killed.json", stop_after, offline, context)
    restarted = embed("killed.json")
    result.observations["full_run"] = full
    result.observations["cancel_resume"] = {"cancelled": cancelled, "resumed": resumed}
    result.observations["owner_exit_restart"] = {"killed": killed, "restarted": restarted}
    checks = {"full_run_complete": full["status"] == "complete",
              "cancel_stopped_at_batch": cancelled["status"] == "stopped" and cancelled["next_batch"] == stop_after,
              "resume_identical": resumed["status"] == "complete" and resumed["output_sha256"] == full["output_sha256"],
              "owner_killed_mid_run": killed["killed"],
              "restart_identical": restarted["status"] == "complete" and restarted["output_sha256"] == full["output_sha256"]}
    result.observations["checks"] = checks
    result.outcome, result.disposition = verdict(checks), "concluded"
    result.limitations.append("a feasibility cursor, not the persisted-generation production indexer (M1)")
    result.limitations.append("the Hugging Face endpoint is pinned; its CDN redirects are not socket-enforced")
    result.follow_up = "M1 qualifies the production worker and model choice on the real corpus"


def _owner_exit(argv: list[str], cursor: Path, after: int, env: Mapping[str, str], context: ProbeContext) -> dict[str, Any]:
    """Start the worker, kill it once its cursor passes `after` batches: the owner exits without warning."""
    process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, **env})
    context.on_cleanup("kill owner-exit worker", lambda: process.poll() is None and process.kill())
    seen = 0
    try:
        while process.poll() is None:
            context.check()
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
    """P4: native driver commit/readback, rollback, constraint failure and restart/reconnect on the released server only."""
    section = context.config.sections.get("postgres")
    if not section:
        result.outcome, result.disposition = "UNRUN", "open"
        result.limitations.append("no released postgres section")
        return
    identity = admit_postgres_resource(section, lambda name: docker_inspect(name, runner, context.timeout(60)))
    credential = os.environ.get(section.get("credential_env", ""), "")
    if not credential:
        raise AdmissionError("the postgres credential environment variable is not set")
    context.ram_only.add(credential)
    import psycopg

    connect = connect or psycopg.connect
    params = {"host": section["host"], "port": section["port"], "user": section["user"], "password": credential,
              "dbname": section["database"], "options": "-c statement_timeout=30000"}
    observations: dict[str, Any] = {"identity": identity, "driver": {"psycopg": psycopg.__version__,
                                                                       "libpq": psycopg.pq.version()}}
    checks: dict[str, bool | None] = {}
    token = uuid.uuid4().hex
    with connect(**params, connect_timeout=int(context.timeout(10))) as conn:
        observations["server_version"] = conn.info.server_version
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS p127probe")
            cur.execute("CREATE TABLE IF NOT EXISTS p127probe.rows (id text PRIMARY KEY, n int NOT NULL)")
        conn.commit()
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
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1/0")
            checks["statement_failure_leaves_connection_usable"] = False
        except psycopg.errors.DivisionByZero:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                checks["statement_failure_leaves_connection_usable"] = cur.fetchone()[0] == 1
        held = connect(**params, connect_timeout=int(context.timeout(10)))
        context.on_cleanup("close held postgres connection", held.close)
    restart_started = time.monotonic()
    restarted = runner(["docker", "restart", "--time", "10", section["container"]], context.timeout(120), None)
    checks["server_restarted"] = restarted.returncode == 0
    try:
        held.execute("SELECT 1")
        checks["held_connection_reports_loss"] = False
    except psycopg.OperationalError:
        checks["held_connection_reports_loss"] = True
    reconnected = None
    while reconnected is None and time.monotonic() - restart_started < 60:
        context.check()
        try:
            reconnected = connect(**params, connect_timeout=int(context.timeout(5)))
        except psycopg.OperationalError:
            time.sleep(0.5)
    observations["reconnect_seconds"] = round(time.monotonic() - restart_started, 3)
    checks["reconnected"] = reconnected is not None
    if reconnected is not None:
        with reconnected as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM p127probe.rows WHERE id = %s", (f"commit-{token}",))
            checks["committed_row_survives_restart"] = cur.fetchone()[0] == 1
    else:
        checks["committed_row_survives_restart"] = None
    after = admit_postgres_resource(section, lambda name: docker_inspect(name, runner, context.timeout(60)))
    checks["same_container_and_volume"] = (after["container_id"], after["volume"]) == (identity["container_id"], identity["volume"])
    observations["checks"] = checks
    result.observations.update(observations)
    result.outcome, result.disposition = verdict(checks), "concluded"
    result.limitations.append("readiness only: no ledger, outbox, durability or completeness claim (M0b)")
    result.follow_up = "M0b builds the durable ledger on this driver/server pairing"


def source_identity(runner: Runner = run_command) -> dict[str, Any]:
    """HEAD plus a digest of the uncommitted diff, so dirty-tree evidence is bound to its exact bytes."""
    head = runner(["git", "rev-parse", "HEAD"], 60, None)
    status = runner(["git", "status", "--porcelain", "--untracked-files=no"], 60, None)
    diff = runner(["git", "diff", "HEAD", "--binary"], 120, None)
    if head.returncode or status.returncode or diff.returncode:
        return {"head": "UNKNOWN", "error": "git identity unavailable"}
    return {"head": head.stdout.strip(), "dirty": bool(status.stdout.strip()),
            "diff_sha256": hashlib.sha256(diff.stdout.encode("utf-8", "surrogateescape")).hexdigest()}


def bind_source(result: ProbeResult, before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    """The record names the source it ran on; a change during the run makes the result INCONCLUSIVE."""
    result.source = {"before": dict(before), "after": dict(after)}
    if before != after or before.get("head") == "UNKNOWN":
        result.limitations.append("source identity changed or was unavailable during the run")
        if result.outcome in {"PASS", "FAIL"}:
            result.outcome = "INCONCLUSIVE"


def run_selftest(context: ProbeContext, result: ProbeResult) -> None:
    """Containment self-test: ticks a released file from this process and an orphaned grandchild, ignoring cancel."""
    tick = released_path((context.config.sections.get(SELFTEST) or {})["tick_file"])
    loop = f"import time\nwhile True:\n    open({str(tick)!r}, 'a').write('g')\n    time.sleep(0.02)\n"
    subprocess.Popen([sys.executable, "-c", loop], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    while True:
        with tick.open("a", encoding="ascii") as handle:
            handle.write("c")
        time.sleep(0.02)


_CHILD_MARGIN_SECONDS = 30.0
_STOP_SECONDS = 30.0


def _stop_tree(process_tree: Any, process: subprocess.Popen[str]) -> None:
    """Kill the whole job, confirm no member runs, then reap the root; raise if the tree outlives the bound."""
    process_tree.kill_tree(process)
    deadline = time.monotonic() + _STOP_SECONDS
    while not process_tree._tree_stopped(process):  # noqa: SLF001 - the module's own confirmation, not a reimplementation
        if time.monotonic() > deadline:
            raise RuntimeError("the probe's process tree did not stop; resources may still be in use")
        time.sleep(0.05)
    try:
        process.communicate(timeout=10)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        pass  # pipes already drained or closed; the tree is confirmed stopped


def run_contained(kind: str, config_path: Path, out_dir: Path = DEFAULT_OUT, *, python: str = sys.executable) -> dict[str, Any]:
    """Run one probe in its own contained process tree. However the child ends, the whole tree is killed and
    confirmed stopped before this returns, so no abandoned body, client or grandchild keeps touching a resource."""
    from tools import process_tree

    config = load_config(config_path)
    bound = config.timeout_seconds + 2 * config.grace_seconds + _CHILD_MARGIN_SECONDS
    argv = [python, "-m", "tools.plan12_memory.probes", "--kind", kind, "--config", str(config_path), "--out", str(out_dir),
            "--in-process"]
    process = process_tree.popen(argv, cwd=REPO_ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    out, err, timed_out = "", "", False
    try:
        out, err = process.communicate(timeout=bound)
    except subprocess.TimeoutExpired:
        timed_out = True
    except BaseException as interrupted:  # KeyboardInterrupt included: stop the tree, then let it propagate
        try:
            _stop_tree(process_tree, process)
        except Exception as stop_error:
            interrupted.add_note(f"stopping the probe tree also failed: {stop_error}")
        raise
    _stop_tree(process_tree, process)  # orphans that redirected their pipes elsewhere die with the job too
    record = next((line.split(" -> ", 1)[1].strip() for line in out.splitlines() if " -> " in line), None)
    if timed_out or record is None:
        result = ProbeResult(kind=kind, run_label=config.run_label, config_sha256=config.sha256, outcome="INCONCLUSIVE",
                             disposition="open", started_utc=_utc())
        result.limitations.append(f"contained child {'exceeded its bound' if timed_out else 'wrote no record'}; tree killed")
        result.observations["child"] = {"returncode": process.returncode, "stderr_tail": err[-400:]}
        result.ended_utc = _utc()
        return {"record": write_attempt(result, out_dir).as_posix(), "returncode": process.returncode, "tree_stopped": True}
    return {"record": record, "returncode": process.returncode, "tree_stopped": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--kind", required=True, choices=(*KINDS, SELFTEST))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--in-process", action="store_true", help="the contained child's mode; run_contained passes it")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except (OSError, ConfigError) as error:
        print(f"config refused: {error}", file=sys.stderr)
        return 2
    if not args.in_process:
        outcome = run_contained(args.kind, args.config, args.out)
        print(f"{args.kind}: contained run -> {outcome['record']}")
        return 0
    before = source_identity()
    result, context = run_probe(args.kind, config)
    bind_source(result, before, source_identity())
    path = write_attempt(result, args.out, context.ram_only)
    print(f"{result.kind}: {result.outcome} ({result.disposition}) -> {path.as_posix()}")
    return 0 if result.outcome in {"PASS", "FAIL", "UNRUN", "UNAVAILABLE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
