from __future__ import annotations


class DuplicateGatewayRequestError(ValueError):
    """A second, divergent record was submitted for an already-recorded ``gateway_request_id``.

    An identical replay of an already-recorded record is idempotent and never raises this
    error, under any run; only a same-ID record with a different provider, provider request id,
    units, or cost (by value) is rejected (``optimus.usage.ledger.append_settled``). Shared by :class:`~optimus.usage.ledger.ProviderUsageLedger` and
    :class:`~optimus.evidence.ledger.EvidenceLedger` so both immutable ledgers reject a
    divergent duplicate before a second entry is ever appended.
    """

    def __init__(self, gateway_request_id: str) -> None:
        self.gateway_request_id = gateway_request_id
        super().__init__(f"divergent gateway_request_id: {gateway_request_id}")
