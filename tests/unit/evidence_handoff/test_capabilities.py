"""RED tests for reader capabilities, activation, retirement, and delivery views (Task 9).

Census note: migrations/evidence_handoff/001_ledger_v1.sql has schema-level
evidence_handoff_capabilities (schema_id, writer_active, reader_active) only —
no per-principal ReaderCapability columns. Per-reader storage is Task 9 work
(likely a new migration), not reuse of that table's shape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_schema_level_capabilities_table_lacks_per_reader_columns() -> None:
    """Documented census: 001 cannot host ReaderCapability rows as-is."""
    sql = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "evidence_handoff"
        / "001_ledger_v1.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS evidence_handoff_capabilities" in sql
    assert "writer_active" in sql
    assert "reader_active" in sql
    # Per-reader fields must not already be on the schema-level table.
    block = sql.split("CREATE TABLE IF NOT EXISTS evidence_handoff_capabilities")[1].split(
        "CREATE TABLE"
    )[0]
    assert "principal_id" not in block
    assert "reported_at" not in block
    assert "retired" not in block


def test_reader_capability_model_fields() -> None:
    from evidence_handoff_runtime.capabilities import ReaderCapability

    reported = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    cap = ReaderCapability(
        agent_id="implementer-1",
        principal_id="principal-implementer",
        supported_schemas=frozenset({"review-ruling.v1"}),
        reported_at=reported,
        retired=False,
    )
    assert cap.agent_id == "implementer-1"
    assert cap.principal_id == "principal-implementer"
    assert cap.supported_schemas == frozenset({"review-ruling.v1"})
    assert cap.reported_at == reported
    assert cap.retired is False


def test_record_and_load_reader_capability() -> None:
    from evidence_handoff_runtime.capabilities import CapabilityCoordinator, ReaderCapability

    store = MagicMock()
    reported = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    cap = ReaderCapability(
        agent_id="implementer-1",
        principal_id="principal-implementer",
        supported_schemas=frozenset({"review-ruling.v1", "handoff.v1"}),
        reported_at=reported,
        retired=False,
    )
    store.get_reader_capability.return_value = cap
    coordinator = CapabilityCoordinator(store=store, now=lambda: reported)
    coordinator.record_capability(cap)
    store.upsert_reader_capability.assert_called_once_with(cap)
    loaded = coordinator.get_capability(principal_id="principal-implementer")
    assert loaded.supported_schemas == frozenset({"review-ruling.v1", "handoff.v1"})
    assert loaded.retired is False


def test_preflight_blocks_missing_and_stale_non_retired_readers() -> None:
    from evidence_handoff_runtime.capabilities import CapabilityCoordinator, ReaderCapability

    now = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    store = MagicMock()
    store.list_reader_capabilities.return_value = (
        ReaderCapability(
            agent_id="fresh-1",
            principal_id="principal-fresh",
            supported_schemas=frozenset({"review-ruling.v1", "handoff.v1"}),
            reported_at=now - timedelta(minutes=1),
            retired=False,
        ),
        ReaderCapability(
            agent_id="stale-1",
            principal_id="principal-stale",
            supported_schemas=frozenset({"review-ruling.v1"}),  # missing handoff.v1
            reported_at=now - timedelta(days=30),
            retired=False,
        ),
        ReaderCapability(
            agent_id="missing-1",
            principal_id="principal-missing",
            supported_schemas=frozenset({"review-ruling.v1"}),
            reported_at=now - timedelta(minutes=2),
            retired=False,
        ),
        ReaderCapability(
            agent_id="retired-1",
            principal_id="principal-retired",
            supported_schemas=frozenset({"review-ruling.v1"}),
            reported_at=now - timedelta(days=90),
            retired=True,  # must not block
        ),
    )
    coordinator = CapabilityCoordinator(
        store=store,
        now=lambda: now,
        stale_after=timedelta(hours=24),
    )
    blockers = coordinator.preflight_activation("handoff.v1")
    assert "principal-stale" in blockers.stale_or_incompatible_principal_ids
    assert "principal-missing" in blockers.stale_or_incompatible_principal_ids
    assert "principal-fresh" not in blockers.stale_or_incompatible_principal_ids
    assert "principal-retired" not in blockers.stale_or_incompatible_principal_ids
    assert blockers.blocking is True


def _caller(*, principal_id: str, scopes: frozenset[str], agent_id: str = "reviewer-1"):
    """Minimal authenticated caller shape for capability admin actions."""
    principal = MagicMock()
    principal.principal_id = principal_id
    principal.agent_id = agent_id
    principal.scopes = scopes
    return principal


def test_activate_writer_refuses_while_blockers_remain_reader_first() -> None:
    from evidence_handoff_runtime.capabilities import (
        ActivationError,
        CapabilityCoordinator,
        ReaderCapability,
    )

    now = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    store = MagicMock()
    store.list_reader_capabilities.return_value = (
        ReaderCapability(
            agent_id="impl-1",
            principal_id="principal-impl",
            supported_schemas=frozenset({"review-ruling.v1"}),
            reported_at=now,
            retired=False,
        ),
    )
    store.is_writer_active.return_value = False
    coordinator = CapabilityCoordinator(store=store, now=lambda: now)
    admin = _caller(
        principal_id="principal-reviewer",
        scopes=frozenset({"ledger.write", "ledger.read", "ledger.admin"}),
    )
    with pytest.raises(ActivationError) as raised:
        coordinator.activate_writer("handoff.v1", caller=admin)
    assert raised.value.code in {"activation_blocked", "readers_not_ready"}
    store.set_writer_active.assert_not_called()


def test_activate_writer_succeeds_after_all_active_readers_report_support() -> None:
    from evidence_handoff_runtime.capabilities import ActivationStatus, CapabilityCoordinator, ReaderCapability

    now = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    store = MagicMock()
    store.list_reader_capabilities.return_value = (
        ReaderCapability(
            agent_id="impl-1",
            principal_id="principal-impl",
            supported_schemas=frozenset({"review-ruling.v1", "handoff.v1"}),
            reported_at=now,
            retired=False,
        ),
        ReaderCapability(
            agent_id="codex-1",
            principal_id="principal-codex",
            supported_schemas=frozenset({"review-ruling.v1", "handoff.v1"}),
            reported_at=now,
            retired=False,
        ),
    )
    store.is_writer_active.return_value = False
    store.set_writer_active.return_value = ActivationStatus(
        schema_id="handoff.v1",
        writer_active=True,
        activated_at=now,
    )
    coordinator = CapabilityCoordinator(store=store, now=lambda: now)
    admin = _caller(
        principal_id="principal-reviewer",
        scopes=frozenset({"ledger.write", "ledger.read", "ledger.admin"}),
    )
    status = coordinator.activate_writer("handoff.v1", caller=admin)
    assert isinstance(status, ActivationStatus)
    assert status.writer_active is True
    store.set_writer_active.assert_called_once_with("handoff.v1", active=True)


def test_non_admin_cannot_retire_principal_or_activate_writer() -> None:
    """Admin-shaped actions require ledger.admin — matched-pair rejection like review-ruling."""
    from evidence_handoff_runtime.capabilities import ActivationError, CapabilityCoordinator

    now = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    store = MagicMock()
    coordinator = CapabilityCoordinator(store=store, now=lambda: now)
    non_admin = _caller(
        principal_id="principal-implementer",
        agent_id="implementer-1",
        scopes=frozenset({"ledger.write", "ledger.read"}),  # no ledger.admin
    )
    with pytest.raises(ActivationError) as retire_raised:
        coordinator.retire_principal("principal-codex", caller=non_admin)
    assert retire_raised.value.code in {
        "admin_required",
        "scope_not_permitted",
        "role_not_permitted",
    }
    store.retire_principal.assert_not_called()

    with pytest.raises(ActivationError) as activate_raised:
        coordinator.activate_writer("handoff.v1", caller=non_admin)
    assert activate_raised.value.code in {
        "admin_required",
        "scope_not_permitted",
        "role_not_permitted",
    }
    store.set_writer_active.assert_not_called()


def test_retire_principal_is_authoritative_for_retired_agent_ids_path() -> None:
    """Task 8 retired_agent_ids must be populated from ReaderCapability.retired — one registry."""
    from evidence_handoff_runtime.capabilities import (
        AdministrativeAuditResult,
        CapabilityCoordinator,
        ReaderCapability,
    )
    from evidence_handoff_runtime.policy import PolicyError, validate_recipients

    now = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    store = MagicMock()
    store.get_reader_capability.return_value = ReaderCapability(
        agent_id="retired-agent",
        principal_id="principal-retired",
        supported_schemas=frozenset({"review-ruling.v1"}),
        reported_at=now,
        retired=False,
    )
    store.retired_agent_ids.return_value = frozenset({"retired-agent"})
    store.retire_principal.return_value = AdministrativeAuditResult(
        principal_id="principal-retired",
        agent_id="retired-agent",
        retired=True,
        audit_event_id="audit-1",
    )
    coordinator = CapabilityCoordinator(store=store, now=lambda: now)
    admin = _caller(
        principal_id="principal-reviewer",
        scopes=frozenset({"ledger.write", "ledger.read", "ledger.admin"}),
    )
    result = coordinator.retire_principal("principal-retired", caller=admin)
    assert result.retired is True
    store.retire_principal.assert_called_once_with("principal-retired")
    # Same rejection path Task 8 already uses — no parallel registry.
    retired = store.retired_agent_ids()
    with pytest.raises(PolicyError) as raised:
        validate_recipients(
            ["retired-agent"],
            known_agent_ids=frozenset({"retired-agent", "implementer-1"}),
            retired_agent_ids=retired,
        )
    assert raised.value.code == "retired_recipient"

def test_unsupported_visible_schema_still_fails_whole_query_no_token() -> None:
    """Per-query unsupported schema remains fail-closed (Task 8 contract, Task 9 surface)."""
    from evidence_handoff_runtime.delivery import DeliveryError, DeliveryService

    store = MagicMock()
    store.current_status.return_value = MagicMock(
        ledger_instance_id="ledger-inst-1",
        last_committed=1,
        last_content_sha256="1" * 64,
    )
    store.get_cursor.return_value = MagicMock(confirmed_sequence=0, chain_head_sha256=None)
    entry = MagicMock()
    entry.sequence = 1
    entry.entry_id = "e1"
    entry.recipient_agent_ids = ("implementer-1",)
    entry.schema_id = "handoff.v1"
    store.verify_unfiltered_range.return_value = MagicMock(
        entries=(entry,), start=1, watermark=1
    )
    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    with pytest.raises(DeliveryError) as raised:
        service.read_entries(
            principal_id="principal-impl",
            agent_id="implementer-1",
            ledger_instance_id="ledger-inst-1",
            cursor=0,
            supported_schemas=frozenset({"review-ruling.v1"}),
        )
    assert raised.value.code == "unsupported_entry_schema"
    store.issue_delivery_token.assert_not_called()


def test_delivery_view_capability_fresh_uses_staleness_not_emptiness() -> None:
    """Regression: a year-old report with schemas must be capability_fresh=False."""
    from evidence_handoff_runtime.capabilities import capability_report_is_fresh
    from evidence_handoff_runtime.observability import build_delivery_views

    now = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
    stale_reported = now - timedelta(days=365)
    assert (
        capability_report_is_fresh(
            stale_reported,
            now=now,
            stale_after=timedelta(hours=24),
            has_schemas=True,
        )
        is False
    )
    assert (
        capability_report_is_fresh(
            now - timedelta(minutes=1),
            now=now,
            stale_after=timedelta(hours=24),
            has_schemas=True,
        )
        is True
    )
    assert (
        capability_report_is_fresh(
            now - timedelta(minutes=1),
            now=now,
            stale_after=timedelta(hours=24),
            has_schemas=False,
        )
        is False
    )

    store = MagicMock()
    store.list_delivery_facts.return_value = (
        {
            "agent_id": "implementer-1",
            "principal_id": "principal-implementer",
            "principal_status": "active",
            "confirmed_sequence": 0,
            "last_confirmed_at": None,
            "visible_unread_count": 0,
            "last_authenticated_request_at": None,
            "last_acknowledgement_sequence": None,
            "last_acknowledgement_at": None,
            "capability_reported_at": stale_reported,
            "capability_fresh": capability_report_is_fresh(
                stale_reported,
                now=now,
                stale_after=timedelta(hours=24),
                has_schemas=True,
            ),
            "activation_blocked": False,
            "warning_delivery": "not_yet_requested",
        },
    )
    store.global_integrity_fact.return_value = {
        "latched": False,
        "incident_id": None,
        "cause": None,
        "safe_boundary_sequence": None,
    }
    views = build_delivery_views(store=store)
    assert views[0].capability_fresh is False


def test_delivery_view_is_facts_only_never_guesses_liveness() -> None:
    from evidence_handoff_runtime.observability import DeliveryView, build_delivery_views

    store = MagicMock()
    store.list_delivery_facts.return_value = (
        {
            "agent_id": "implementer-1",
            "principal_id": "principal-implementer",
            "principal_status": "active",
            "confirmed_sequence": 2,
            "last_confirmed_at": datetime(2026, 8, 9, 11, 0, 0, tzinfo=UTC),
            "visible_unread_count": 1,
            "last_authenticated_request_at": datetime(2026, 8, 9, 11, 30, 0, tzinfo=UTC),
            "last_acknowledgement_sequence": None,
            "last_acknowledgement_at": None,
            "capability_reported_at": datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC),
            "capability_fresh": True,
            "activation_blocked": False,
            "warning_delivery": "not_yet_requested",
        },
    )
    store.global_integrity_fact.return_value = {
        "latched": False,
        "incident_id": None,
        "cause": None,
        "safe_boundary_sequence": None,
    }
    views = build_delivery_views(store=store)
    assert len(views) == 1
    view = views[0]
    assert isinstance(view, DeliveryView)
    mapping = view.to_mapping()
    for forbidden in ("online", "dead", "healthy", "liveness", "is_alive", "process_status"):
        assert forbidden not in mapping
        assert forbidden not in {k.lower() for k in mapping}
    assert mapping["warning_delivery"] == "not_yet_requested"
    assert mapping["agent_id"] == "implementer-1"
    assert mapping["visible_unread_count"] == 1


def test_delivery_view_distinguishes_warning_delivered_vs_not_yet_requested() -> None:
    from evidence_handoff_runtime.observability import build_delivery_views

    store = MagicMock()
    store.list_delivery_facts.return_value = (
        {
            "agent_id": "a1",
            "principal_id": "p1",
            "principal_status": "active",
            "confirmed_sequence": 0,
            "last_confirmed_at": None,
            "visible_unread_count": 0,
            "last_authenticated_request_at": datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC),
            "last_acknowledgement_sequence": None,
            "last_acknowledgement_at": None,
            "capability_reported_at": datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC),
            "capability_fresh": True,
            "activation_blocked": False,
            "warning_delivery": "delivered",
        },
        {
            "agent_id": "a2",
            "principal_id": "p2",
            "principal_status": "active",
            "confirmed_sequence": 0,
            "last_confirmed_at": None,
            "visible_unread_count": 0,
            "last_authenticated_request_at": None,
            "last_acknowledgement_sequence": None,
            "last_acknowledgement_at": None,
            "capability_reported_at": None,
            "capability_fresh": False,
            "activation_blocked": True,
            "warning_delivery": "not_yet_requested",
        },
    )
    store.global_integrity_fact.return_value = {
        "latched": True,
        "incident_id": "inc-1",
        "cause": "chain_break",
        "safe_boundary_sequence": 3,
    }
    views = build_delivery_views(store=store)
    by_agent = {v.agent_id: v for v in views}
    assert by_agent["a1"].warning_delivery == "delivered"
    assert by_agent["a2"].warning_delivery == "not_yet_requested"
    assert views[0].integrity["latched"] is True
    assert views[0].integrity["incident_id"] == "inc-1"


def test_delivery_projection_rebuildable_and_non_authoritative() -> None:
    from evidence_handoff_runtime.observability import rebuild_delivery_projection

    store = MagicMock()
    store.rebuild_delivery_projection.return_value = {
        "rebuilt_rows": 2,
        "source": "canonical_entries",
        "authoritative_for_entry_content": False,
    }
    result = rebuild_delivery_projection(store=store)
    assert result["authoritative_for_entry_content"] is False
    assert result["source"] == "canonical_entries"
    store.rebuild_delivery_projection.assert_called_once()
    # Projection discard + rebuild must not call any entry-body rewriter.
    assert not hasattr(store, "rewrite_entry_body") or not store.rewrite_entry_body.called
