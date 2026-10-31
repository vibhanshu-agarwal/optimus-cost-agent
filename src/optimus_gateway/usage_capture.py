"""The Gateway's minimal capture stream (Plan 12.8; ADR-032): one intent before and one outcome after each physical
upstream model attempt. It exists only for what the host cannot see: a legacy route's internal retries, a reply lost on
the way back, or a host that died mid-call. It is evidence correlated by the host request header, never a receipt
store or a second debit: the host's settlement stays the only accounting.

Process-wide like the request diagnostics: the launch configures one writer (`configure`), the server opens and closes
each request's context (`begin` / `end`), the routes name the request or attempt ID they minted (`set_request`), and
the upstream client wraps each physical attempt (`physical_attempt`). Unconfigured, every call is a no-op. Capture
never refuses or delays an attempt beyond the outbox's short acknowledgement wait.
"""

from __future__ import annotations

import itertools
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError

from optimus_security import accounting_config
from optimus_security import usage_capture_contract as uc
from optimus_security.durable_outbox import ACK_WAIT_SECONDS, OutboxWriter, Record
from optimus_security.outbox_drain import DrainStop, OutboxDrain

if TYPE_CHECKING:
    from optimus_gateway.models import GatewayServiceConfig
    from optimus_gateway.usage_store import UsageStore

_STATE = threading.local()
_writer: OutboxWriter | None = None
_ack_wait = ACK_WAIT_SECONDS


def configure(writer: OutboxWriter | None, *, ack_wait: float = ACK_WAIT_SECONDS) -> None:
    global _writer, _ack_wait
    _writer, _ack_wait = writer, ack_wait


def begin(host_request_id: str | None) -> None:
    """Open this thread's request context with the host request it serves (None when the header was absent or malformed)."""
    _STATE.host_request_id = host_request_id if host_request_id and uc.CAPTURE_REQUEST_ID.fullmatch(host_request_id) else None
    _STATE.gateway_request_id = None
    _STATE.ordinals = {}
    _STATE.pending = None


def end() -> None:
    _STATE.host_request_id = _STATE.gateway_request_id = _STATE.pending = None
    _STATE.ordinals = {}


def set_request(gateway_request_id: str) -> None:
    """The Gateway request (legacy) or attempt (enforced, decisions) ID the next physical attempts belong to."""
    _STATE.gateway_request_id = gateway_request_id


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _http_status(exc: BaseException) -> int | None:
    """The provider's HTTP status, raw or from the bounded failure fact the legacy client attaches; else None."""
    if isinstance(exc, HTTPError):
        return exc.code
    failure = getattr(exc, "failure", None)
    status = failure.get("status") if isinstance(failure, dict) and failure.get("kind") == "http" else None
    return status if type(status) is int else None


def prepare_attempt() -> None:
    """Record the next physical attempt's intent now, before the dispatch-time budget check, so the capture's wait never
    consumes the margin that check approves. Whether the intent was durable in time travels with its outcome."""
    writer = _writer
    gateway_request_id = getattr(_STATE, "gateway_request_id", None)
    if writer is None or gateway_request_id is None:
        _STATE.pending = None
        return
    ordinals: dict[str, Any] = getattr(_STATE, "ordinals", None) or {}
    _STATE.ordinals = ordinals
    number = next(ordinals.setdefault(gateway_request_id, itertools.count(1)))
    confirmed = writer.submit(
        {"kind": uc.GATEWAY_ATTEMPT_INTENT, "at": _now(), "gateway_request_id": gateway_request_id,
         "host_request_id": getattr(_STATE, "host_request_id", None), "attempt": number, "route": None}
    ).wait(_ack_wait)
    _STATE.pending = (gateway_request_id, number, confirmed)


def abandon_attempt() -> None:
    """The prepared attempt was refused at dispatch: it is closed as not sent."""
    pending = getattr(_STATE, "pending", None)
    _STATE.pending = None
    if pending is not None and _writer is not None:
        _outcome(_writer, pending, "not_sent", None)


def _outcome(writer: OutboxWriter, pending: tuple[str, int, bool], outcome: str, status: int | None) -> None:
    gateway_request_id, number, confirmed = pending
    writer.submit(
        {"kind": uc.GATEWAY_ATTEMPT_OUTCOME, "at": _now(), "gateway_request_id": gateway_request_id, "attempt": number,
         "outcome": outcome, "http_status": status, "cost_usd": None, "billing_units": None, "intent_confirmed": confirmed}
    )


@contextmanager
def physical_attempt() -> Iterator[None]:
    """Record one physical upstream attempt's outcome around its I/O: completed, failed with its HTTP status, or
    uncertain. It answers the intent `prepare_attempt` recorded before the budget check (or records one now)."""
    if getattr(_STATE, "pending", None) is None:
        prepare_attempt()
    pending = getattr(_STATE, "pending", None)
    _STATE.pending = None
    writer = _writer
    if writer is None or pending is None:
        yield
        return
    outcome, status = "uncertain", None
    try:
        yield
        outcome = "completed"
    except BaseException as exc:
        status = _http_status(exc)
        outcome = "failed" if status is not None else "uncertain"
        raise
    finally:
        _outcome(writer, pending, outcome, status)


def handle_usage_capture_request(*, authorization_header: str | None, raw_body: bytes, config: GatewayServiceConfig) -> tuple[int, dict[str, Any]]:
    """`POST /v1/observability/usage-capture`: a strictly validated batch committed by the Gateway-owned ledger. Only a
    committed batch is acknowledged; anything else leaves the sender's outbox untouched. Bodies over the contract's
    limit are refused by the server before they are read."""
    from optimus_gateway.models import authorize_bearer
    from optimus_gateway.usage_store import StoreError

    if not authorize_bearer(authorization_header=authorization_header, shared_secret=config.shared_secret):
        return 401, {"error": "unauthorized"}
    try:
        batch = uc.parse_batch(raw_body)
    except uc.ContractError as exc:
        return 400, {"status": "rejected", "code": f"CAPTURE_{exc.code.upper()}"}
    store = config.usage_store
    if store is None:
        return 503, {"status": "unavailable", "code": "ACCOUNTING_NOT_CONFIGURED", "retryable": True}
    try:
        result = store.ingest(batch)
    except StoreError as exc:
        if exc.code == "unavailable":
            return 503, {"status": "unavailable", "code": "LEDGER_UNAVAILABLE", "retryable": True}
        body: dict[str, Any] = {"status": "rejected", "code": f"CAPTURE_{exc.code.upper()}"}
        if exc.committed is not None:
            body.update(ledger_instance=store.ledger_instance, sequence=exc.committed[0], digest=exc.committed[1])
        return (409 if exc.code == "cursor_mismatch" else 400), body
    return 200, uc.build_ack(result.ack)


@dataclass
class GatewayAccounting:
    """What a launch with an accounting root runs: the capture writer, the ledger when an approved configuration and its
    credential are present, and the drain of the Gateway's own streams into that ledger."""

    writer: OutboxWriter
    store: UsageStore | None = None
    drain: OutboxDrain | None = None

    def stop(self) -> None:
        if self.drain is not None:
            self.drain.stop()
        configure(None)
        self.writer.close()


def start_accounting(root: Path, config: accounting_config.AccountingConfig | None, *, refusal: str | None = None,
                     keyring_backend: Any, log: Callable[[str], None]) -> GatewayAccounting:
    """Open the Gateway's accounting under its verified root with the configuration verified against the manifest (never
    re-read here). The ledger's password is read only from the Gateway-owned keyring namespace; without an approved
    configuration or that credential, capture still accumulates locally."""
    from optimus_gateway.usage_store import UsageStore

    writer = OutboxWriter(root / "outbox" / "gateway")
    configure(writer)
    accounting = GatewayAccounting(writer)
    if refusal is not None:
        log(f"optimus-local-gateway: accounting configuration refused ({refusal}); capture stays local.")
        return accounting
    if config is None:
        return accounting
    try:
        password = keyring_backend.get_password(accounting_config.KEYRING_SERVICE, config.credential_name)
    except Exception:  # noqa: BLE001 - an unavailable keyring leaves accounting off, never the Gateway
        password = None
    if not password:
        log("optimus-local-gateway: the accounting credential is not in the Gateway keyring namespace; capture stays local.")
        return accounting
    accounting.store = UsageStore.from_config(config, password)
    accounting.drain = OutboxDrain(writer, _direct_send(accounting.store), name="gateway-capture-drain")
    accounting.drain.start()
    return accounting


def _direct_send(store: UsageStore) -> Callable[[str, str | None, tuple[int, str], list[Record]], uc.CaptureAck]:
    from optimus_gateway.usage_store import StoreError

    def send(stream_id: str, ledger: str | None, after: tuple[int, str], batch: list[Record]) -> uc.CaptureAck:
        try:
            parsed = uc.parse_batch(uc.build_batch("gateway", stream_id, ledger, after[0], after[1], batch))
            return store.ingest(parsed).ack
        except uc.ContractError as exc:
            raise DrainStop(f"invalid:{exc.code}") from None
        except StoreError as exc:
            raise DrainStop(exc.code, transient=exc.code == "unavailable") from None

    return send
