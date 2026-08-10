"""Lifecycle-owned durable signing-key custody via the OS keyring.

Option A: one DPAPI-backed keyring entry per service installation (control root),
not per ledger_instance_id. Service and RuntimeInputSupplier must not query the
keyring — they consume resolved bytes only.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from pathlib import Path

_ENTRY_NAME = "signing_key"
_KEY_BYTES = 32


class SigningKeyCustodyError(Exception):
    """Value-free durable signing-key custody failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"SigningKeyCustodyError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


def keyring_service_for_control_root(control_root: Path) -> str:
    """Stable OS-keyring service name for one installation (control root)."""
    digest = hashlib.sha256(str(control_root.resolve()).encode("utf-8")).hexdigest()[:32]
    return f"evidence-handoff-signing:{digest}"


def _decode_stored(raw: str) -> bytes:
    try:
        decoded = base64.b64decode(raw.encode("ascii"), validate=True)
    except (ValueError, TypeError) as exc:
        raise SigningKeyCustodyError("signing_key_corrupt") from exc
    if len(decoded) != _KEY_BYTES:
        raise SigningKeyCustodyError("signing_key_corrupt")
    return decoded


def load_signing_key(*, control_root: Path, keyring_backend: object) -> bytes:
    """Load the installation signing key. Never mints."""
    service = keyring_service_for_control_root(control_root)
    try:
        raw = keyring_backend.get_password(service, _ENTRY_NAME)
    except Exception as exc:  # noqa: BLE001 — translate any backend failure
        raise SigningKeyCustodyError("signing_key_unreadable") from exc
    if raw is None:
        raise SigningKeyCustodyError("signing_key_missing")
    if not isinstance(raw, str):
        raise SigningKeyCustodyError("signing_key_corrupt")
    return _decode_stored(raw)


def resolve_signing_key(
    *,
    control_root: Path,
    keyring_backend: object,
    instance_record_present: bool,
    store_instance_present: bool,
) -> bytes:
    """Load the installation key, or mint once when no instance signal exists."""
    try:
        return load_signing_key(control_root=control_root, keyring_backend=keyring_backend)
    except SigningKeyCustodyError as exc:
        if exc.code != "signing_key_missing":
            raise

    if instance_record_present or store_instance_present:
        raise SigningKeyCustodyError("signing_key_mint_forbidden")

    minted = secrets.token_bytes(_KEY_BYTES)
    service = keyring_service_for_control_root(control_root)
    encoded = base64.b64encode(minted).decode("ascii")
    try:
        keyring_backend.set_password(service, _ENTRY_NAME, encoded)
    except Exception as exc:  # noqa: BLE001
        raise SigningKeyCustodyError("signing_key_unwritable") from exc
    return minted


__all__ = [
    "SigningKeyCustodyError",
    "keyring_service_for_control_root",
    "load_signing_key",
    "resolve_signing_key",
]
