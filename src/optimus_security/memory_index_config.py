"""The context index's configuration (Plan 12.10 Task 2; ADR-037). Neutral: `optimus-trust memory-setup` writes it, the launch
gate binds its digest for approval, the parent signs the literal into the Gateway's manifest, and the Gateway composes the
same literal itself and reads it.

`<config_root>/memory-index/memory-index.json` holds non-secret facts only: the dedicated Redis resource, the ACL file's digest,
the keyring entry's name and the embedding artifact's identity. Its absence means the feature is off and nothing changes for
an existing launch approval. `users.acl` beside it holds the password's hash, never the password, which lives only in the
Gateway's keyring namespace.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_NAME = "memory-index.json"
ACL_NAME = "users.acl"
ARTIFACTS_NAME = "artifacts"
SECURITY_LITERAL_NAME = "_memory_index_config"  # not an environment variable, like the accounting literal
KEYRING_SERVICE = "optimus-gateway-memory-index"  # the Gateway's own namespace, apart from approvals and credentials
ACL_COMMANDS = ("ping", "info", "module|list", "get", "set", "del", "incrby", "pexpire", "exists", "scan",
                "hset", "hsetnx", "hget", "hmget", "hgetall", "hdel", "sadd", "srem", "smembers",
                "zadd", "zrangebylex", "multi", "exec", "discard", "watch", "unwatch",
                "ft.create", "ft.search", "ft.info", "ft.dropindex")
KEY_PATTERN = "oidx:*"
_MAX_BYTES = 16 * 1024
_KEYS = frozenset({"schema_version", "resource", "image", "container", "volume", "host", "port", "user", "credential_name",
                   "maxmemory_mb", "acl_sha256", "embedding"})
_EMBEDDING_KEYS = frozenset({"model", "source", "revision", "licence", "dimensions", "max_input_tokens", "artifact_sha256"})
_NAME = re.compile(r"[A-Za-z0-9_.@:/-]{1,128}")
_RESOURCE = re.compile(r"[a-z0-9-]{8,64}")
_IMAGE = re.compile(r"[a-z0-9./_-]+@sha256:[0-9a-f]{64}")
_DOCKER_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{1,62}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_LOOPBACK = frozenset({"127.0.0.1", "localhost"})


class MemoryIndexConfigError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    source: str
    revision: str
    licence: str
    dimensions: int
    max_input_tokens: int
    artifact_sha256: str


@dataclass(frozen=True)
class MemoryIndexConfig:
    resource: str
    image: str
    container: str
    volume: str
    host: str
    port: int
    user: str
    credential_name: str
    maxmemory_mb: int
    acl_sha256: str
    embedding: EmbeddingConfig


def memory_index_root(config_root: Path) -> Path:
    return config_root / "memory-index"


def _config_bytes(root: Path) -> bytes | None:
    path = root / CONFIG_NAME
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise MemoryIndexConfigError("not_a_regular_file")
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if len(data) > _MAX_BYTES:
        raise MemoryIndexConfigError("too_large")
    return data


def _literal(data: bytes) -> str:
    return "memory-index-config:sha256:" + hashlib.sha256(data).hexdigest()


def config_literal(root: Path) -> str | None:
    """The approval literal of the configuration's exact bytes, or None when there is no configuration. The ACL file's digest
    and the artifact's are inside those bytes, so replacing either needs a new approval."""
    data = _config_bytes(root)
    return None if data is None else _literal(data)


def read(root: Path) -> tuple[str | None, MemoryIndexConfig | None, str | None]:
    """One captured read, so what is verified is what is used: (literal, config, refusal code); all None without a file."""
    data = _config_bytes(root)
    if data is None:
        return None, None, None
    try:
        return _literal(data), _parse(data), None
    except MemoryIndexConfigError as exc:
        return _literal(data), None, exc.code


def memory_index_literal(root: Path, config: str | None) -> str:
    """What the Gateway's manifest binds: the root and the approved configuration literal."""
    return json.dumps({"config": config, "root": str(root.resolve())}, sort_keys=True, separators=(",", ":"))


def _parse(data: bytes) -> MemoryIndexConfig:
    try:
        document = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise MemoryIndexConfigError("malformed") from None
    if not isinstance(document, dict) or set(document) != _KEYS or document["schema_version"] != 1:
        raise MemoryIndexConfigError("schema")
    if not all(isinstance(document[key], str) for key in ("resource", "image", "container", "volume", "host", "user", "credential_name", "acl_sha256")):
        raise MemoryIndexConfigError("schema")
    if not _RESOURCE.fullmatch(document["resource"]) or not _IMAGE.fullmatch(document["image"]):
        raise MemoryIndexConfigError("resource")
    if not _DOCKER_NAME.fullmatch(document["container"]) or not _DOCKER_NAME.fullmatch(document["volume"]):
        raise MemoryIndexConfigError("resource")
    port = document["port"]
    if document["host"] not in _LOOPBACK or type(port) is not int or not 0 < port < 65536:
        raise MemoryIndexConfigError("endpoint")
    if not _NAME.fullmatch(document["user"]) or not _NAME.fullmatch(document["credential_name"]):
        raise MemoryIndexConfigError("names")
    if type(document["maxmemory_mb"]) is not int or not 64 <= document["maxmemory_mb"] <= 1 << 20:
        raise MemoryIndexConfigError("memory")
    if not _DIGEST.fullmatch(document["acl_sha256"]):
        raise MemoryIndexConfigError("digest")
    return MemoryIndexConfig(
        document["resource"], document["image"], document["container"], document["volume"], document["host"], port, document["user"],
        document["credential_name"], document["maxmemory_mb"], document["acl_sha256"], _embedding(document["embedding"]),
    )


def _embedding(value: Any) -> EmbeddingConfig:
    if not isinstance(value, dict) or set(value) != _EMBEDDING_KEYS:
        raise MemoryIndexConfigError("embedding")
    if not all(isinstance(value[key], str) and _NAME.fullmatch(value[key]) for key in ("model", "source", "revision", "licence")):
        raise MemoryIndexConfigError("embedding")
    if type(value["dimensions"]) is not int or not 1 <= value["dimensions"] <= 4096:
        raise MemoryIndexConfigError("embedding")
    if type(value["max_input_tokens"]) is not int or not 1 <= value["max_input_tokens"] <= 1 << 20:
        raise MemoryIndexConfigError("embedding")
    if not isinstance(value["artifact_sha256"], str) or not _DIGEST.fullmatch(value["artifact_sha256"]):
        raise MemoryIndexConfigError("embedding")
    return EmbeddingConfig(value["model"], value["source"], value["revision"], value["licence"], value["dimensions"],
                           value["max_input_tokens"], value["artifact_sha256"])


def acl_text(user: str, password_sha256: str) -> str:
    """The restricted ACL file: only the hash, least privilege, the default user off."""
    commands = " ".join(f"+{command}" for command in ACL_COMMANDS)
    return f"user default off\nuser {user} on #{password_sha256} ~{KEY_PATTERN} resetchannels -@all {commands}\n"


def artifact_digest(root: Path) -> str:
    """One digest over an artifact directory's relative paths and contents, order independent."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        with path.open("rb") as stream:
            while chunk := stream.read(1 << 20):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()
