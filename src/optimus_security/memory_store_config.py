"""The memory store's configuration (Plan 12.11 Task 1; ADR-042). Neutral: `optimus-trust memory-setup --store` writes it,
the launch gate binds its digest for approval, the parent signs the literal into the Gateway's manifest, and the Gateway
composes the same literal itself and reads it.

It is the context index's pattern (ADR-037) for a second, separate resource: accepted memory cannot be rebuilt from the
workspace, so it does not share the index's instance, credential or eviction behaviour.

`<config_root>/memory-store/memory-store.json` holds non-secret facts only: the dedicated Redis resource, the ACL file's digest
and the keyring entry's name. Its absence means the feature is off and nothing changes for an existing launch approval.
`users.acl` beside it holds the password's hash, never the password, which lives only in the Gateway's keyring namespace.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = "memory-store.json"
ACL_NAME = "users.acl"
SECURITY_LITERAL_NAME = "_memory_store_config"  # not an environment variable, like the index's literal
KEYRING_SERVICE = "optimus-gateway-memory-store"  # the Gateway's own namespace, apart from the index, approvals and credentials
# Streams carry the authoritative events; hashes, sets and sorted sets the rebuildable projection; WATCH/MULTI the fence;
# WAITAOF the same-connection fsync. BGREWRITEAOF and BGSAVE complete a purge. No scripting, no CONFIG, no FLUSH.
ACL_COMMANDS = ("ping", "info", "dbsize", "get", "set", "del", "exists", "incrby", "pexpire", "pttl", "scan",
                "hset", "hsetnx", "hget", "hmget", "hgetall", "hdel", "hlen", "sadd", "srem", "smembers", "sismember", "scard",
                "zadd", "zrem", "zrange", "zrangebyscore", "zcard",
                "xadd", "xrange", "xrevrange", "xlen", "xdel",
                "multi", "exec", "discard", "watch", "unwatch", "waitaof", "client|id", "bgrewriteaof", "bgsave", "lastsave")
KEY_PATTERN = "omem:*"
_MAX_BYTES = 16 * 1024
_KEYS = frozenset({"schema_version", "resource", "image", "container", "volume", "host", "port", "user", "credential_name",
                   "maxmemory_mb", "admission_ceiling_mb", "acl_sha256"})
_NAME = re.compile(r"[A-Za-z0-9_.@:/-]{1,128}")
_RESOURCE = re.compile(r"[a-z0-9-]{8,64}")
_IMAGE = re.compile(r"[a-z0-9./_-]+@sha256:[0-9a-f]{64}")
_DOCKER_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{1,62}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_LOOPBACK = frozenset({"127.0.0.1", "localhost"})


class MemoryStoreConfigError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MemoryStoreConfig:
    resource: str
    image: str
    container: str
    volume: str
    host: str
    port: int
    user: str
    credential_name: str
    maxmemory_mb: int
    admission_ceiling_mb: int  # new saves stop here; the rest of maxmemory is reserved for withdrawal, purge and control
    acl_sha256: str


def memory_store_root(config_root: Path) -> Path:
    return config_root / "memory-store"


def _config_bytes(root: Path) -> bytes | None:
    path = root / CONFIG_NAME
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise MemoryStoreConfigError("not_a_regular_file")
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if len(data) > _MAX_BYTES:
        raise MemoryStoreConfigError("too_large")
    return data


def _literal(data: bytes) -> str:
    return "memory-store-config:sha256:" + hashlib.sha256(data).hexdigest()


def config_literal(root: Path) -> str | None:
    """The approval literal of the configuration's exact bytes, or None when there is no configuration. The ACL file's digest
    is inside those bytes, so replacing it needs a new approval."""
    data = _config_bytes(root)
    return None if data is None else _literal(data)


def read(root: Path) -> tuple[str | None, MemoryStoreConfig | None, str | None]:
    """One captured read, so what is verified is what is used: (literal, config, refusal code); all None without a file."""
    data = _config_bytes(root)
    if data is None:
        return None, None, None
    try:
        return _literal(data), _parse(data), None
    except MemoryStoreConfigError as exc:
        return _literal(data), None, exc.code


def memory_store_literal(root: Path, config: str | None) -> str:
    """What the Gateway's manifest binds: the root and the approved configuration literal."""
    return json.dumps({"config": config, "root": str(root.resolve())}, sort_keys=True, separators=(",", ":"))


def _parse(data: bytes) -> MemoryStoreConfig:
    try:
        document = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise MemoryStoreConfigError("malformed") from None
    if not isinstance(document, dict) or set(document) != _KEYS or document["schema_version"] != 1:
        raise MemoryStoreConfigError("schema")
    if not all(isinstance(document[key], str) for key in ("resource", "image", "container", "volume", "host", "user", "credential_name", "acl_sha256")):
        raise MemoryStoreConfigError("schema")
    if not _RESOURCE.fullmatch(document["resource"]) or not _IMAGE.fullmatch(document["image"]):
        raise MemoryStoreConfigError("resource")
    if not _DOCKER_NAME.fullmatch(document["container"]) or not _DOCKER_NAME.fullmatch(document["volume"]):
        raise MemoryStoreConfigError("resource")
    port = document["port"]
    if document["host"] not in _LOOPBACK or type(port) is not int or not 0 < port < 65536:
        raise MemoryStoreConfigError("endpoint")
    if not _NAME.fullmatch(document["user"]) or not _NAME.fullmatch(document["credential_name"]):
        raise MemoryStoreConfigError("names")
    maxmemory, ceiling = document["maxmemory_mb"], document["admission_ceiling_mb"]
    if type(maxmemory) is not int or not 64 <= maxmemory <= 1 << 20:
        raise MemoryStoreConfigError("memory")
    if type(ceiling) is not int or not 1 <= ceiling < maxmemory:  # a reserve must remain for deletion and control
        raise MemoryStoreConfigError("memory")
    if not _DIGEST.fullmatch(document["acl_sha256"]):
        raise MemoryStoreConfigError("digest")
    return MemoryStoreConfig(
        document["resource"], document["image"], document["container"], document["volume"], document["host"], port, document["user"],
        document["credential_name"], maxmemory, ceiling, document["acl_sha256"],
    )


def acl_text(user: str, password_sha256: str) -> str:
    """The restricted ACL file: only the hash, least privilege, the default user off."""
    commands = " ".join(f"+{command}" for command in ACL_COMMANDS)
    return f"user default off\nuser {user} on #{password_sha256} ~{KEY_PATTERN} resetchannels -@all {commands}\n"
