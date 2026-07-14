from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from optimus.evidence.ledger import EvidenceLedger
from optimus.gateway.models import GatewayUsage
from optimus.telemetry.events import TelemetryEvent
from optimus.usage.ledger import ProviderUsageLedger
from optimus.usage.models import ProviderUsage


class UsageReconciliationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None
    matched_gateway_request_ids: frozenset[str]
    missing_provider_usage_ids: frozenset[str]
    missing_evidence_ids: frozenset[str]
    evidence_cost_usd: Decimal
    provider_cost_usd: Decimal
    cost_delta_usd: Decimal

    @property
    def reconciled(self) -> bool:
        return (
            not self.missing_provider_usage_ids
            and not self.missing_evidence_ids
            and self.cost_delta_usd == Decimal("0")
        )


class UsageAccountingService:
    """
    Provides services for tracking and auditing usage of gateways and related
    provider services.

    This class is responsible for recording usage metrics and auditing
    specific events, such as pricing fallback occurrences. It utilizes
    `ProviderUsageLedger` for maintaining records of usage and ensures
    telemetry details are captured for further analysis.

    :ivar provider_ledger: Ledger used for recording and maintaining
        provider usage data.
    :type provider_ledger: ProviderUsageLedger
    """
    def __init__(self, *, provider_ledger: ProviderUsageLedger | None = None) -> None:
        self.provider_ledger = provider_ledger or ProviderUsageLedger()

    def record_gateway_usage(
        self,
        gateway_usage: GatewayUsage,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
    ) -> ProviderUsageLedger:
        usage = ProviderUsage.from_gateway_usage(
            gateway_usage,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
        )
        self.provider_ledger = self.provider_ledger.record(usage)
        return self.provider_ledger

    def record_pricing_fallback_audit(
        self,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        provider: str,
        service: str,
        native_unit: str,
        price_snapshot_id: str,
        reason: str,
    ) -> TelemetryEvent:
        return TelemetryEvent.pricing_fallback(
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            provider=provider,
            service=service,
            native_unit=native_unit,
            price_snapshot_id=price_snapshot_id,
            reason=reason,
        )


def reconcile_evidence_provider_usage(
    evidence_ledger: EvidenceLedger,
    provider_ledger: ProviderUsageLedger,
    *,
    run_id: str | None = None,
) -> UsageReconciliationReport:
    evidence_ids = evidence_ledger.gateway_request_ids(run_id=run_id)
    provider_ids = provider_ledger.gateway_request_ids(run_id=run_id)
    matched = evidence_ids & provider_ids
    evidence_cost = evidence_ledger.total_cost_usd(run_id=run_id)
    provider_cost = provider_ledger.total_cost_usd(run_id=run_id)
    return UsageReconciliationReport(
        run_id=run_id,
        matched_gateway_request_ids=matched,
        missing_provider_usage_ids=evidence_ids - provider_ids,
        missing_evidence_ids=provider_ids - evidence_ids,
        evidence_cost_usd=evidence_cost,
        provider_cost_usd=provider_cost,
        cost_delta_usd=evidence_cost - provider_cost,
    )
