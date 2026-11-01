"""Delivery of the host's outbox streams to the Gateway-owned ledger (Plan 12.8; ADR-032), through the host's existing
Gateway URL and key: the shared `optimus_security.outbox_drain` with an HTTP send. The host never holds the ledger's
credential. Passes run on one owned background thread, never inside settlement and never on a model call's path.

Plan 12.9 (ADR-034): before its passes, delivery asks the Gateway's usage-report capabilities once it answers. Only a
Gateway listing `FEATURE_REPORT_CONTEXT` enables turn contexts; an older one (its unknown route answers 404, or a
response this contract does not know) keeps them off for the process, so a record it would refuse is never written.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from optimus.gateway.errors import GatewayError, GatewayHttpError
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc
from optimus_security import usage_report_contract as urc
from optimus_security.outbox_drain import DrainReport, DrainStop, OutboxDrain

if TYPE_CHECKING:
    from optimus.gateway.client import GatewayClient
    from optimus.usage.durable_capture import DurableCapture

DeliveryReport = DrainReport


class CaptureDelivery(OutboxDrain):
    def __init__(self, capture: DurableCapture, client: GatewayClient, **kwargs: Any) -> None:
        self._client = client
        self._capture = capture
        self.report_context: bool | None = None  # None until the Gateway has answered the capabilities request
        super().__init__(capture.writer, self._post, name="capture-delivery", **kwargs)

    def drain_once(self) -> DeliveryReport:
        if self.report_context is None:
            self._negotiate()
        return super().drain_once()

    def _negotiate(self) -> None:
        try:
            reply = self._client.post_observability_json(path=urc.PATH, payload=json.loads(urc.build_request(None)))
        except GatewayHttpError as exc:
            if exc.status_code in {0, 503}:
                return  # not answering yet (status 0 is the transport's own failure): ask again next pass
            self.report_context = False  # it answered and does not support the feature (an older Gateway: 404)
            return
        except GatewayError:
            return
        try:
            self.report_context = urc.FEATURE_REPORT_CONTEXT in urc.validate_capabilities(reply)
        except urc.ContractError:
            self.report_context = False
        if self.report_context:
            self._capture.enable_report_context()

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
