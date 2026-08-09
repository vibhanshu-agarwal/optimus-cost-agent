"""Reader-confirmed delivery: verified global scan, visibility filter, tokens, CAS."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from evidence_handoff.ledger.models import (
    CursorStatus,
    DeliveryPage,
    DeliveryToken,
    ImmutableEntryEnvelope,
    IntegrityWitness,
)


class DeliveryError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"DeliveryError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


def visible_to_agent(agent_id: str, recipient_agent_ids: Iterable[str]) -> bool:
    """Exact stable agent membership — no wildcard, role, or context expansion."""
    return str(agent_id) in {str(item) for item in recipient_agent_ids}


def _page_digest(
    *,
    watermark: int,
    visible_entry_ids: tuple[str, ...],
    resulting_witness: IntegrityWitness,
) -> str:
    payload = {
        "watermark": watermark,
        "visible_entry_ids": list(visible_entry_ids),
        "ledger_instance_id": resulting_witness.ledger_instance_id,
        "last_committed": resulting_witness.last_committed,
        "last_content_sha256": resulting_witness.last_content_sha256,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class DeliveryService:
    def __init__(
        self,
        *,
        store: Any,
        now: Callable[[], datetime] | None = None,
        token_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        self._store = store
        self._now = now or (lambda: datetime.now(tz=UTC))
        self._token_ttl = token_ttl

    def unread_count(
        self,
        *,
        principal_id: str,
        agent_id: str,
        ledger_instance_id: str,
        cursor: int,
    ) -> int:
        del principal_id  # unread is agent/instance scoped after confirmed cursor
        return int(
            self._store.count_visible_unread(
                agent_id=agent_id,
                ledger_instance_id=ledger_instance_id,
                after_sequence=int(cursor),
            )
        )

    def read_entries(
        self,
        *,
        principal_id: str,
        agent_id: str,
        ledger_instance_id: str,
        cursor: int,
        supported_schemas: frozenset[str],
    ) -> DeliveryPage:
        status = self._store.current_status()
        if str(status.ledger_instance_id) != str(ledger_instance_id):
            raise DeliveryError("ledger_instance_mismatch")

        cursor_row = self._store.get_cursor(
            principal_id=principal_id,
            agent_id=agent_id,
            ledger_instance_id=ledger_instance_id,
        )
        confirmed = int(getattr(cursor_row, "confirmed_sequence", cursor) or 0)
        # Client-supplied cursor must not exceed confirmed or head.
        if int(cursor) > confirmed:
            # Allow explicit re-read at confirmed cursor; reject jumping ahead of store.
            if int(cursor) > int(status.last_committed):
                raise DeliveryError("cursor_ahead_of_head")
        if confirmed > int(status.last_committed):
            raise DeliveryError("cursor_ahead_of_head")

        previous_witness = IntegrityWitness(
            ledger_instance_id=str(ledger_instance_id),
            last_committed=confirmed,
            last_content_sha256=getattr(cursor_row, "chain_head_sha256", None),
            verified=True,
        )
        watermark = int(status.last_committed)
        resulting_witness = self._store.head_witness()
        start = confirmed + 1

        if start > watermark:
            visible: tuple[ImmutableEntryEnvelope, ...] = ()
        else:
            verified = self._store.verify_unfiltered_range(
                reader_cursor=start,
                watermark=watermark,
                anchor=previous_witness,
            )
            visible_list: list[ImmutableEntryEnvelope] = []
            for entry in verified.entries:
                if not visible_to_agent(agent_id, entry.recipient_agent_ids):
                    continue
                if str(entry.schema_id) not in supported_schemas:
                    raise DeliveryError("unsupported_entry_schema")
                visible_list.append(entry)
            visible = tuple(visible_list)

        visible_ids = tuple(entry.entry_id for entry in visible)
        digest = _page_digest(
            watermark=watermark,
            visible_entry_ids=visible_ids,
            resulting_witness=resulting_witness,
        )
        token = DeliveryToken(
            token_id=str(uuid.uuid4()),
            principal_id=principal_id,
            agent_id=agent_id,
            ledger_instance_id=str(ledger_instance_id),
            previous_cursor=confirmed,
            previous_witness=previous_witness,
            watermark=watermark,
            resulting_witness=resulting_witness,
            visible_entry_ids=visible_ids,
            page_digest=digest,
            expires_at=self._now() + self._token_ttl,
        )
        issued = self._store.issue_delivery_token(token=token)
        unread = len(visible)
        count_fn = getattr(self._store, "count_visible_unread", None)
        if callable(count_fn):
            counted = count_fn(
                agent_id=agent_id,
                ledger_instance_id=ledger_instance_id,
                after_sequence=confirmed,
            )
            if isinstance(counted, int):
                unread = counted
        return DeliveryPage(
            entries=visible,
            watermark=watermark,
            page_digest=digest,
            delivery_token=issued if isinstance(issued, DeliveryToken) else token,
            unread_count=unread,
        )

    def confirm_delivery(self, *, token_id: str, principal_id: str) -> CursorStatus:
        token = self._store.consume_delivery_token(
            token_id=token_id,
            principal_id=principal_id,
            now=self._now(),
        )
        return self._store.confirm_cursor_cas(token=token, now=self._now())


__all__ = ["DeliveryError", "DeliveryService", "visible_to_agent"]
