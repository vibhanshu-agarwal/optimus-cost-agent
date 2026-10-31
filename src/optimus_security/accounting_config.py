"""The Gateway's accounting configuration (Plan 12.8; ADR-032). Neutral: the launch gate binds its digest for approval,
the parent signs the accounting literal into the Gateway's manifest, and the Gateway composes the same literal itself
and reads the configuration.

The file `<config_root>/accounting/gateway-accounting.json` holds only non-secret facts: the Postgres endpoint,
database, role, connect timeout and the name of the password's entry in the Gateway-owned keyring namespace. No
password, DSN with a password, or other credential is ever accepted in it. Its absence means accounting is off: capture
still accumulates locally and nothing changes for an existing launch approval.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = "gateway-accounting.json"
SECURITY_LITERAL_NAME = "OPTIMUS_ACCOUNTING_CONFIG"
KEYRING_SERVICE = "optimus-gateway-accounting"  # the Gateway's own namespace, apart from approvals and credentials
_MAX_BYTES = 16 * 1024
_KEYS = frozenset({"schema_version", "host", "port", "database", "user", "credential_name", "connect_timeout_seconds"})
_NAME = re.compile(r"[A-Za-z0-9_.@:/-]{1,128}")
_HOST = re.compile(r"[A-Za-z0-9.:-]{1,253}")


class AccountingConfigError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AccountingConfig:
    host: str
    port: int
    database: str
    user: str
    credential_name: str
    connect_timeout_seconds: int


def accounting_root(config_root: Path) -> Path:
    return config_root / "accounting"


def _config_bytes(root: Path) -> bytes | None:
    path = root / CONFIG_NAME
    if path.is_symlink():
        raise AccountingConfigError("not_a_regular_file")
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if len(data) > _MAX_BYTES:
        raise AccountingConfigError("too_large")
    return data


def config_literal(root: Path) -> str | None:
    """The approval literal of the configuration's exact bytes, or None when there is none."""
    data = _config_bytes(root)
    return None if data is None else _literal(data)


def _literal(data: bytes) -> str:
    return "accounting-config:sha256:" + hashlib.sha256(data).hexdigest()


def read(root: Path) -> tuple[str | None, AccountingConfig | None, str | None]:
    """One captured read: the literal and the parsed configuration of the same bytes, so what is verified is what is
    used (Checkpoint B finding 2). Returns (literal, config, refusal code); all None when there is no file."""
    data = _config_bytes(root)
    if data is None:
        return None, None, None
    try:
        return _literal(data), _parse(data), None
    except AccountingConfigError as exc:
        return _literal(data), None, exc.code


def accounting_literal(root: Path, config: str | None) -> str:
    """What the Gateway's manifest binds: its accounting root and the approved configuration literal (or none)."""
    return json.dumps({"config": config, "root": str(root.resolve())}, sort_keys=True, separators=(",", ":"))


def load(root: Path) -> AccountingConfig | None:
    """The validated configuration, or None when there is none. Anything that is not exactly the documented non-secret
    shape is refused, so a password can never be read from it."""
    data = _config_bytes(root)
    return None if data is None else _parse(data)


def _parse(data: bytes) -> AccountingConfig:
    try:
        document = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise AccountingConfigError("malformed") from None
    if not isinstance(document, dict) or set(document) != _KEYS or document["schema_version"] != 1:
        raise AccountingConfigError("schema")
    host, port, database, user, name, timeout = (
        document[k] for k in ("host", "port", "database", "user", "credential_name", "connect_timeout_seconds")
    )
    if not (isinstance(host, str) and _HOST.fullmatch(host)) or not (type(port) is int and 0 < port < 65536):
        raise AccountingConfigError("endpoint")
    if not all(isinstance(v, str) and _NAME.fullmatch(v) for v in (database, user, name)):
        raise AccountingConfigError("names")
    if not (type(timeout) is int and 1 <= timeout <= 60):
        raise AccountingConfigError("timeout")
    return AccountingConfig(host, port, database, user, name, timeout)
