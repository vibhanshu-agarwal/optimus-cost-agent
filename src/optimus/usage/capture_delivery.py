"""Delivery of the host's outbox streams to the Gateway-owned ledger (Plan 12.8; ADR-032), through the host's existing
Gateway URL and key: the shared `optimus_security.outbox_drain` with an HTTP send. The host never holds the ledger's
credential. Passes run on one owned background thread, never inside settlement and never on a model call's path.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from optimus.gateway.errors import GatewayError, GatewayHttpError
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc
from optimus_security.outbox_drain import DrainReport, DrainStop, OutboxDrain

if TYPE_CHECKING:
    from optimus.gateway.client import GatewayClient
    from optimus.usage.durable_capture import DurableCapture

DeliveryReport = DrainReport


class CaptureDelivery(OutboxDrain):
    def __init__(self, capture: DurableCapture, client: GatewayClient, **kwargs: Any) -> None:
        self._client = client
        super().__init__(capture.writer, self._post, name="capture-delivery", **kwargs)

    def _post(self, stream_id: str, ledger: str | None, after: tuple[int, str], batch: list[ob.Record]) -> uc.CaptureAck:
        body = json.loads(uc.build_batch("host", stream_id, ledger, after[0], after[1], batch))
        try:
            reply = self._client.post_observability_json(path=uc.PATH, payload=body)
        except GatewayHttpError as exc:
            if exc.status_code == 503:
                raise DrainStop("ledger_unavailable", transient=True) from None
            raise DrainStop(f"refused:{exc.status_code}") from None
        except GatewayError:
            raise DrainStop("gateway_unreachable", transient=True) from None
        try:
            return uc.parse_ack(reply, stream_id=stream_id)
        except uc.ContractError:
            raise DrainStop("malformed_ack") from None
