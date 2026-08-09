"""RED tests for reader-confirmed delivery, tokens, and cursors (Task 8).

Covers frozen recipient visibility, verified unfiltered reads before filter,
short-lived single-use tokens, CAS confirmation, and non-disclosure of hidden
entries. IntegrityWitness is the witness type (no parallel invent).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from evidence_handoff.ledger.models import IntegrityWitness


def _enrollment(
    *,
    principal_id: str,
    agent_id: str,
    caller_role: str = "reviewer",
    instance_id: str = "ledger-inst-1",
):
    from evidence_handoff_runtime.auth import Enrollment

    return Enrollment(
        principal_id=principal_id,
        agent_id=agent_id,
        caller_role=caller_role,
        scopes=frozenset({"ledger.write", "ledger.read"}),
        instance_id=instance_id,
    )


def test_delivery_models_reuse_integrity_witness() -> None:
    from evidence_handoff.ledger.models import CursorStatus, DeliveryPage, DeliveryToken

    witness = IntegrityWitness(
        ledger_instance_id="ledger-inst-1",
        last_committed=3,
        last_content_sha256="a" * 64,
        verified=True,
    )
    token = DeliveryToken(
        token_id="tok-1",
        principal_id="principal-reader",
        agent_id="implementer-1",
        ledger_instance_id="ledger-inst-1",
        previous_cursor=0,
        previous_witness=witness,
        watermark=3,
        resulting_witness=witness,
        visible_entry_ids=("entry-2",),
        page_digest="b" * 64,
        expires_at=datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC),
    )
    assert isinstance(token.previous_witness, IntegrityWitness)
    assert isinstance(token.resulting_witness, IntegrityWitness)
    page = DeliveryPage(
        entries=(),
        watermark=3,
        page_digest="b" * 64,
        delivery_token=token,
        unread_count=0,
    )
    assert page.delivery_token.token_id == "tok-1"
    status = CursorStatus(
        principal_id="principal-reader",
        agent_id="implementer-1",
        confirmed_sequence=3,
        last_advanced_at=datetime(2026, 8, 9, 12, 0, 1, tzinfo=UTC),
        unread_count=0,
        witness=witness,
    )
    assert isinstance(status.witness, IntegrityWitness)


@pytest.mark.parametrize(
    ("recipients", "code"),
    [
        ([], "recipients_required"),
        (["implementer-1", "implementer-1"], "duplicate_recipients"),
        (["unknown-agent"], "unknown_recipient"),
        (["retired-agent"], "retired_recipient"),
        (["*"], "wildcard_recipient"),
        (["role:reviewer"], "role_alias_recipient"),
        (["context:ctx-1"], "context_alias_recipient"),
    ],
)
def test_recipient_validation_rejects_forbidden_shapes(
    recipients: list[str], code: str
) -> None:
    from evidence_handoff_runtime.policy import PolicyError, validate_recipients

    with pytest.raises(PolicyError) as raised:
        validate_recipients(
            recipients,
            known_agent_ids=frozenset({"reviewer-1", "implementer-1", "retired-agent"}),
            retired_agent_ids=frozenset({"retired-agent"}),
        )
    assert raised.value.code == code


def test_retired_agent_ids_checked_like_known_agent_ids() -> None:
    """Task 8 minimal retirement: explicit set parallel to known_agent_ids (no Task 9 API)."""
    from evidence_handoff_runtime.policy import PolicyError, validate_recipients

    validate_recipients(
        ["implementer-1"],
        known_agent_ids=frozenset({"implementer-1", "retired-agent"}),
        retired_agent_ids=frozenset({"retired-agent"}),
    )
    with pytest.raises(PolicyError) as raised:
        validate_recipients(
            ["retired-agent"],
            known_agent_ids=frozenset({"implementer-1", "retired-agent"}),
            retired_agent_ids=frozenset({"retired-agent"}),
        )
    assert raised.value.code == "retired_recipient"


def test_visibility_is_exact_agent_membership_no_broadcast() -> None:
    from evidence_handoff_runtime.delivery import visible_to_agent

    assert visible_to_agent("implementer-1", ("implementer-1", "reviewer-1")) is True
    assert visible_to_agent("reviewer-1", ("implementer-1",)) is False
    assert visible_to_agent("implementer-1", ("*",)) is False
    assert visible_to_agent("implementer-1", ("role:implementer",)) is False


def _fake_entry(
    *,
    sequence: int,
    entry_id: str,
    recipients: tuple[str, ...],
    schema_id: str = "review-ruling.v1",
):
    env = MagicMock()
    env.sequence = sequence
    env.entry_id = entry_id
    env.recipient_agent_ids = recipients
    env.schema_id = schema_id
    env.content_sha256 = f"{sequence:064x}"[:64]
    env.ledger_instance_id = "ledger-inst-1"
    env.to_mapping.return_value = {
        "sequence": sequence,
        "entry_id": entry_id,
        "recipient_agent_ids": list(recipients),
        "schema_id": schema_id,
        "content_sha256": env.content_sha256,
    }
    return env


def test_read_entries_filters_after_unfiltered_verify_and_returns_token() -> None:
    from evidence_handoff.ledger.models import DeliveryPage
    from evidence_handoff_runtime.delivery import DeliveryService

    store = MagicMock()
    witness = IntegrityWitness(
        ledger_instance_id="ledger-inst-1",
        last_committed=3,
        last_content_sha256="c" * 64,
        verified=True,
    )
    store.current_status.return_value = MagicMock(
        ledger_instance_id="ledger-inst-1",
        last_committed=3,
        last_content_sha256="c" * 64,
    )
    store.get_cursor.return_value = MagicMock(
        confirmed_sequence=0,
        chain_head_sha256=None,
    )
    store.verify_unfiltered_range.return_value = MagicMock(
        entries=(
            _fake_entry(sequence=1, entry_id="e1", recipients=("reviewer-1",)),
            _fake_entry(sequence=2, entry_id="e2", recipients=("implementer-1",)),
            _fake_entry(sequence=3, entry_id="e3", recipients=("reviewer-1", "implementer-1")),
        ),
        start=1,
        watermark=3,
    )
    store.head_witness.return_value = witness
    store.issue_delivery_token.side_effect = lambda **kwargs: kwargs.get("token") or MagicMock(
        token_id="tok-issued",
        **{k: v for k, v in kwargs.items() if k != "token"},
    )

    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    page = service.read_entries(
        principal_id="principal-impl",
        agent_id="implementer-1",
        ledger_instance_id="ledger-inst-1",
        cursor=0,
        supported_schemas=frozenset({"review-ruling.v1"}),
    )
    assert isinstance(page, DeliveryPage)
    assert [e.entry_id for e in page.entries] == ["e2", "e3"]
    assert page.watermark == 3
    assert page.delivery_token is not None
    store.verify_unfiltered_range.assert_called_once()
    # Visible gaps are normal; hidden seq=1 must not appear.
    assert all(e.sequence != 1 for e in page.entries)


def test_read_entries_no_visible_watermark_still_issues_token() -> None:
    from evidence_handoff_runtime.delivery import DeliveryService

    store = MagicMock()
    store.current_status.return_value = MagicMock(
        ledger_instance_id="ledger-inst-1",
        last_committed=2,
        last_content_sha256="d" * 64,
    )
    store.get_cursor.return_value = MagicMock(confirmed_sequence=0, chain_head_sha256=None)
    store.verify_unfiltered_range.return_value = MagicMock(
        entries=(
            _fake_entry(sequence=1, entry_id="e1", recipients=("reviewer-1",)),
            _fake_entry(sequence=2, entry_id="e2", recipients=("reviewer-1",)),
        ),
        start=1,
        watermark=2,
    )
    store.head_witness.return_value = IntegrityWitness(
        ledger_instance_id="ledger-inst-1",
        last_committed=2,
        last_content_sha256="d" * 64,
        verified=True,
    )
    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    page = service.read_entries(
        principal_id="principal-impl",
        agent_id="implementer-1",
        ledger_instance_id="ledger-inst-1",
        cursor=0,
        supported_schemas=frozenset({"review-ruling.v1"}),
    )
    assert page.entries == ()
    assert page.watermark == 2
    assert page.delivery_token is not None
    assert page.unread_count == 0


def test_unread_count_counts_only_visible_after_cursor() -> None:
    from evidence_handoff_runtime.delivery import DeliveryService

    store = MagicMock()
    store.count_visible_unread.return_value = 2
    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    assert (
        service.unread_count(
            principal_id="p",
            agent_id="implementer-1",
            ledger_instance_id="ledger-inst-1",
            cursor=1,
        )
        == 2
    )
    store.count_visible_unread.assert_called_once_with(
        agent_id="implementer-1",
        ledger_instance_id="ledger-inst-1",
        after_sequence=1,
    )


def test_confirm_delivery_cas_advances_past_non_visible() -> None:
    from evidence_handoff.ledger.models import CursorStatus, DeliveryToken
    from evidence_handoff_runtime.delivery import DeliveryService

    witness = IntegrityWitness(
        ledger_instance_id="ledger-inst-1",
        last_committed=3,
        last_content_sha256="e" * 64,
        verified=True,
    )
    token = DeliveryToken(
        token_id="tok-confirm",
        principal_id="principal-impl",
        agent_id="implementer-1",
        ledger_instance_id="ledger-inst-1",
        previous_cursor=0,
        previous_witness=IntegrityWitness(
            ledger_instance_id="ledger-inst-1",
            last_committed=0,
            last_content_sha256=None,
            verified=True,
        ),
        watermark=3,
        resulting_witness=witness,
        visible_entry_ids=("e2",),
        page_digest="f" * 64,
        expires_at=datetime(2026, 8, 9, 12, 5, 0, tzinfo=UTC),
    )
    store = MagicMock()
    store.consume_delivery_token.return_value = token
    store.confirm_cursor_cas.return_value = CursorStatus(
        principal_id="principal-impl",
        agent_id="implementer-1",
        confirmed_sequence=3,
        last_advanced_at=datetime(2026, 8, 9, 12, 0, 1, tzinfo=UTC),
        unread_count=0,
        witness=witness,
    )
    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    status = service.confirm_delivery(token_id="tok-confirm", principal_id="principal-impl")
    assert status.confirmed_sequence == 3
    store.confirm_cursor_cas.assert_called_once()


def test_lost_confirmation_allows_redelivery() -> None:
    from evidence_handoff_runtime.delivery import DeliveryService

    store = MagicMock()
    store.current_status.return_value = MagicMock(
        ledger_instance_id="ledger-inst-1",
        last_committed=1,
        last_content_sha256="1" * 64,
    )
    store.get_cursor.return_value = MagicMock(confirmed_sequence=0, chain_head_sha256=None)
    entry = _fake_entry(sequence=1, entry_id="e1", recipients=("implementer-1",))
    store.verify_unfiltered_range.return_value = MagicMock(
        entries=(entry,), start=1, watermark=1
    )
    store.head_witness.return_value = IntegrityWitness(
        ledger_instance_id="ledger-inst-1",
        last_committed=1,
        last_content_sha256="1" * 64,
        verified=True,
    )
    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    first = service.read_entries(
        principal_id="principal-impl",
        agent_id="implementer-1",
        ledger_instance_id="ledger-inst-1",
        cursor=0,
        supported_schemas=frozenset({"review-ruling.v1"}),
    )
    second = service.read_entries(
        principal_id="principal-impl",
        agent_id="implementer-1",
        ledger_instance_id="ledger-inst-1",
        cursor=0,
        supported_schemas=frozenset({"review-ruling.v1"}),
    )
    assert [e.entry_id for e in first.entries] == ["e1"]
    assert [e.entry_id for e in second.entries] == ["e1"]


@pytest.mark.parametrize(
    "failure",
    ["token_expired", "token_replayed", "token_principal_mismatch", "token_invalid"],
)
def test_confirm_rejects_bad_tokens_without_cursor_change(failure: str) -> None:
    from evidence_handoff_runtime.delivery import DeliveryError, DeliveryService

    store = MagicMock()
    store.consume_delivery_token.side_effect = DeliveryError(failure)
    store.get_cursor.return_value = MagicMock(confirmed_sequence=4, chain_head_sha256="h" * 64)
    before = store.get_cursor.return_value.confirmed_sequence
    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    with pytest.raises(DeliveryError) as raised:
        service.confirm_delivery(token_id="bad", principal_id="principal-impl")
    assert raised.value.code == failure
    store.confirm_cursor_cas.assert_not_called()
    assert store.get_cursor.return_value.confirmed_sequence == before


def test_confirm_cas_conflict_leaves_cursor() -> None:
    from evidence_handoff.ledger.models import DeliveryToken
    from evidence_handoff_runtime.delivery import DeliveryError, DeliveryService

    token = DeliveryToken(
        token_id="tok-cas",
        principal_id="principal-impl",
        agent_id="implementer-1",
        ledger_instance_id="ledger-inst-1",
        previous_cursor=1,
        previous_witness=IntegrityWitness(
            ledger_instance_id="ledger-inst-1",
            last_committed=1,
            last_content_sha256="1" * 64,
            verified=True,
        ),
        watermark=2,
        resulting_witness=IntegrityWitness(
            ledger_instance_id="ledger-inst-1",
            last_committed=2,
            last_content_sha256="2" * 64,
            verified=True,
        ),
        visible_entry_ids=("e2",),
        page_digest="p" * 64,
        expires_at=datetime(2026, 8, 9, 12, 5, 0, tzinfo=UTC),
    )
    store = MagicMock()
    store.consume_delivery_token.return_value = token
    store.confirm_cursor_cas.side_effect = DeliveryError("cursor_cas_conflict")
    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    with pytest.raises(DeliveryError) as raised:
        service.confirm_delivery(token_id="tok-cas", principal_id="principal-impl")
    assert raised.value.code == "cursor_cas_conflict"


def test_unsupported_visible_schema_fails_whole_query_no_token() -> None:
    from evidence_handoff_runtime.delivery import DeliveryError, DeliveryService

    store = MagicMock()
    store.current_status.return_value = MagicMock(
        ledger_instance_id="ledger-inst-1",
        last_committed=1,
        last_content_sha256="1" * 64,
    )
    store.get_cursor.return_value = MagicMock(confirmed_sequence=0, chain_head_sha256=None)
    store.verify_unfiltered_range.return_value = MagicMock(
        entries=(
            _fake_entry(
                sequence=1,
                entry_id="e1",
                recipients=("implementer-1",),
                schema_id="handoff.v1",
            ),
        ),
        start=1,
        watermark=1,
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
    assert store.get_cursor.return_value.confirmed_sequence == 0


def test_global_integrity_failure_returns_no_page_token_or_cursor_change() -> None:
    from evidence_handoff_runtime.delivery import DeliveryError, DeliveryService
    from evidence_handoff_runtime.integrity import IntegrityCause, LedgerIntegrityError

    store = MagicMock()
    store.current_status.return_value = MagicMock(
        ledger_instance_id="ledger-inst-1",
        last_committed=2,
        last_content_sha256="x" * 64,
    )
    store.get_cursor.return_value = MagicMock(confirmed_sequence=0, chain_head_sha256=None)
    store.verify_unfiltered_range.side_effect = LedgerIntegrityError(
        cause=IntegrityCause.CHAIN_BREAK,
        ledger_instance_id="ledger-inst-1",
        safe_boundary_sequence=0,
    )
    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    with pytest.raises((DeliveryError, LedgerIntegrityError)):
        service.read_entries(
            principal_id="principal-impl",
            agent_id="implementer-1",
            ledger_instance_id="ledger-inst-1",
            cursor=0,
            supported_schemas=frozenset({"review-ruling.v1"}),
        )
    store.issue_delivery_token.assert_not_called()
    assert store.get_cursor.return_value.confirmed_sequence == 0


def test_rollback_witness_ahead_of_head_rejects_read() -> None:
    from evidence_handoff_runtime.delivery import DeliveryError, DeliveryService

    store = MagicMock()
    store.current_status.return_value = MagicMock(
        ledger_instance_id="ledger-inst-1",
        last_committed=2,
        last_content_sha256="2" * 64,
    )
    # Cursor claims a chain head ahead of / diverging from current head.
    store.get_cursor.return_value = MagicMock(
        confirmed_sequence=5,
        chain_head_sha256="f" * 64,
    )
    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    with pytest.raises(DeliveryError) as raised:
        service.read_entries(
            principal_id="principal-impl",
            agent_id="implementer-1",
            ledger_instance_id="ledger-inst-1",
            cursor=5,
            supported_schemas=frozenset({"review-ruling.v1"}),
        )
    assert raised.value.code in {"rollback_divergence", "cursor_ahead_of_head"}
    store.issue_delivery_token.assert_not_called()


def test_hidden_entries_not_disclosed_in_page_or_unread() -> None:
    """Side-channel probe: reader must not learn existence/count/position of hidden entries."""
    from evidence_handoff_runtime.delivery import DeliveryService

    store = MagicMock()
    store.current_status.return_value = MagicMock(
        ledger_instance_id="ledger-inst-1",
        last_committed=4,
        last_content_sha256="4" * 64,
    )
    store.get_cursor.return_value = MagicMock(confirmed_sequence=0, chain_head_sha256=None)
    # Global has 4 entries; only seq 2 is visible to implementer-1.
    store.verify_unfiltered_range.return_value = MagicMock(
        entries=(
            _fake_entry(sequence=1, entry_id="hidden-1", recipients=("reviewer-1",)),
            _fake_entry(sequence=2, entry_id="visible-2", recipients=("implementer-1",)),
            _fake_entry(sequence=3, entry_id="hidden-3", recipients=("reviewer-1",)),
            _fake_entry(sequence=4, entry_id="hidden-4", recipients=("codex-1",)),
        ),
        start=1,
        watermark=4,
    )
    store.head_witness.return_value = IntegrityWitness(
        ledger_instance_id="ledger-inst-1",
        last_committed=4,
        last_content_sha256="4" * 64,
        verified=True,
    )
    store.count_visible_unread.return_value = 1
    service = DeliveryService(store=store, now=lambda: datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC))
    page = service.read_entries(
        principal_id="principal-impl",
        agent_id="implementer-1",
        ledger_instance_id="ledger-inst-1",
        cursor=0,
        supported_schemas=frozenset({"review-ruling.v1"}),
    )
    blob = repr(page) + str([e.to_mapping() for e in page.entries])
    assert "hidden-1" not in blob
    assert "hidden-3" not in blob
    assert "hidden-4" not in blob
    assert page.unread_count == 1
    # Must not expose total committed count or hidden positions as a side channel.
    assert not hasattr(page, "total_committed")
    assert not hasattr(page, "hidden_count")
    assert getattr(page, "global_entry_count", None) in {None, 0}
    assert [e.sequence for e in page.entries] == [2]
