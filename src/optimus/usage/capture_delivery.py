"""Delivery of the host's outbox streams to the Gateway-owned ledger (Plan 12.8; ADR-032), through the host's existing
Gateway URL and key: the shared `optimus_security.outbox_drain` with an HTTP send. The host never holds the ledger's
credential. Passes run on one owned background thread, never inside settlement and never on a model call's path.

Plan 12.9 (ADR-034): before its passes, delivery asks the Gateway's usage-report capabilities once it answers. Only a
Gateway listing `FEATURE_REPORT_CONTEXT` enables turn contexts; an older one (its unknown route answers 404, or a
response this contract does not know) keeps them off for the process, so a record it would refuse is never written.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
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
    def __init__(self, capture: DurableCapture, client: GatewayClient, *,
                 capabilities: Callable[[bytes], tuple[int, Any]] | None = None, **kwargs: Any) -> None:
        self._client = client
        self._capture = capture
        # Plan 12.9: a bounded POST to the report route (`savings_report.gateway_post`); None never negotiates.
        self._capabilities = capabilities
        self.report_context: bool | None = None  # None until the Gateway has answered the capabilities request
        super().__init__(capture.writer, self._post, name="capture-delivery", **kwargs)

    def drain_once(self) -> DeliveryReport:
        self.negotiate()
        return super().drain_once()

    def negotiate(self) -> None:
        """Ask for the capabilities until the Gateway has answered. Each pass does; so does a launch once its own Gateway
        is up, because a turn entered before the answer stays unattributed for good."""
        if self.report_context is None and self._capabilities is not None:
            with contextlib.suppress(Exception):  # negotiation never stops this pass's ordinary delivery
                self._negotiate(self._capabilities)

    def _negotiate(self, capabilities: Callable[[bytes], tuple[int, Any]]) -> None:
        from optimus.usage.savings_report import ReportTransportError

        try:
            status, reply = capabilities(urc.build_request(None))
        except ReportTransportError:
            return  # not answering, or not within its bound: ask again next pass
        if status == 503:
            return
        try:
            self.report_context = status == 200 and urc.FEATURE_REPORT_CONTEXT in urc.validate_capabilities(reply)
        except urc.ContractError:
            self.report_context = False  # it answered, and not with these capabilities (an older Gateway: 404)
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
