"""PostgreSQL-backed immutable ledger store with transactional sequence assignment."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from evidence_handoff.ledger.canonical import content_sha256_for_envelope
from evidence_handoff.ledger.errors import LedgerStoreError, LedgerValidationError
from evidence_handoff.ledger.models import (
    AppendResult,
    ArtifactRef,
    CursorStatus,
    DeliveryToken,
    EntryKind,
    EntryMessage,
    ImmutableEntryEnvelope,
    IntegrityWitness,
    MessagePart,
    SanitizedDraft,
    ServerIdentity,
    StoreStatus,
    VerifiedRange,
)
from evidence_handoff_runtime.capabilities import (
    ActivationStatus,
    AdministrativeAuditResult,
    ReaderCapability,
    capability_report_is_fresh,
)
from evidence_handoff_runtime.delivery import DeliveryError
from evidence_handoff_runtime.integrity import (
    IntegrityCause,
    IntegrityIncident,
    IntegrityLatch,
    LedgerIntegrityError,
)


def _reject_credential_shaped_identity(identity: ServerIdentity) -> None:
    """Task 6: store must never accept bearer/token material as identity fields."""
    for value in (
        identity.principal_id,
        identity.agent_id,
        identity.caller_role,
        identity.authority,
    ):
        if "Bearer " in value or value.startswith("eh1."):
            raise LedgerValidationError("identity_looks_like_credential")


class PostgresLedgerStore:
    def __init__(
        self,
        *,
        conninfo: str,
        ledger_instance_id: str,
        control_root: Path | None = None,
    ) -> None:
        if not ledger_instance_id:
            raise LedgerStoreError("ledger_instance_id_required")
        self._conninfo = conninfo
        self._ledger_instance_id = ledger_instance_id
        self._control_root = control_root

    @property
    def ledger_instance_id(self) -> str:
        return self._ledger_instance_id

    def attach_integrity_control_root(self, control_root: Path) -> None:
        self._control_root = control_root

    def ensure_instance_metadata(self) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO evidence_handoff_ledger_instance(ledger_instance_id, genesis_sequence, genesis_content_sha256)
                VALUES (%s, 0, NULL)
                ON CONFLICT (ledger_instance_id) DO NOTHING
                """,
                (self._ledger_instance_id,),
            )
            conn.execute(
                """
                INSERT INTO evidence_handoff_counter(ledger_instance_id, last_committed, last_content_sha256)
                VALUES (%s, 0, NULL)
                ON CONFLICT (ledger_instance_id) DO NOTHING
                """,
                (self._ledger_instance_id,),
            )
            conn.commit()

    def instance_row_present(self) -> bool:
        """True when this store's ledger_instance_id already has a durable instance row."""
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM evidence_handoff_ledger_instance
                WHERE ledger_instance_id = %s
                """,
                (self._ledger_instance_id,),
            ).fetchone()
            return row is not None

    def append(
        self,
        sanitized: SanitizedDraft,
        identity: ServerIdentity,
        *,
        idempotency_key: str,
    ) -> AppendResult:
        self._refuse_if_integrity_latched()
        _reject_credential_shaped_identity(identity)
        if not idempotency_key.strip():
            raise LedgerValidationError("idempotency_key_required")
        with psycopg.connect(self._conninfo) as conn:
            try:
                return self._append_in_txn(conn, sanitized, identity, idempotency_key=idempotency_key)
            except Exception:
                conn.rollback()
                raise

    def append_with_forced_failure(
        self,
        sanitized: SanitizedDraft,
        identity: ServerIdentity,
        *,
        idempotency_key: str,
    ) -> AppendResult:
        """Test helper: begin an append then raise before commit to prove rollback."""
        with psycopg.connect(self._conninfo) as conn:
            try:
                self._append_in_txn(
                    conn,
                    sanitized,
                    identity,
                    idempotency_key=idempotency_key,
                    commit=False,
                )
                raise LedgerStoreError("forced_append_failure")
            except Exception:
                conn.rollback()
                raise

    def _append_in_txn(
        self,
        conn: psycopg.Connection,
        sanitized: SanitizedDraft,
        identity: ServerIdentity,
        *,
        idempotency_key: str,
        commit: bool = True,
    ) -> AppendResult:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT last_committed, last_content_sha256
                FROM evidence_handoff_counter
                WHERE ledger_instance_id = %s
                FOR UPDATE
                """,
                (self._ledger_instance_id,),
            )
            counter = cur.fetchone()
            if counter is None:
                raise LedgerStoreError("counter_missing")

            cur.execute(
                """
                SELECT entry_id, sequence, content_sha256, kind, schema_id, context_id, task_id,
                       in_reply_to, recipient_agent_ids, message_json, artifacts_json
                FROM evidence_handoff_entries
                WHERE ledger_instance_id = %s AND principal_id = %s AND idempotency_key = %s
                """,
                (self._ledger_instance_id, identity.principal_id, idempotency_key),
            )
            existing = cur.fetchone()
            if existing is not None:
                existing_fingerprint = {
                    "kind": existing["kind"],
                    "schema_id": existing["schema_id"],
                    "context_id": existing["context_id"],
                    "recipient_agent_ids": list(existing["recipient_agent_ids"]),
                    "message": existing["message_json"],
                    "artifacts": existing["artifacts_json"],
                    "task_id": existing["task_id"],
                    "in_reply_to": existing["in_reply_to"],
                }
                if existing_fingerprint != sanitized.request_fingerprint():
                    raise LedgerValidationError("idempotency_conflict")
                if commit:
                    conn.commit()
                return AppendResult(
                    entry_id=existing["entry_id"],
                    sequence=int(existing["sequence"]),
                    ledger_instance_id=self._ledger_instance_id,
                    content_sha256=existing["content_sha256"],
                    idempotent_replay=True,
                )

            last_committed = int(counter["last_committed"])
            last_digest = counter["last_content_sha256"]
            cur.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS max_sequence, COUNT(*) AS row_count
                FROM evidence_handoff_entries
                WHERE ledger_instance_id = %s
                """,
                (self._ledger_instance_id,),
            )
            head = cur.fetchone()
            assert head is not None
            max_sequence = int(head["max_sequence"])
            row_count = int(head["row_count"])
            if row_count == 0:
                cur.execute(
                    """
                    SELECT genesis_sequence, genesis_content_sha256
                    FROM evidence_handoff_ledger_instance
                    WHERE ledger_instance_id = %s
                    """,
                    (self._ledger_instance_id,),
                )
                genesis = cur.fetchone()
                if genesis is None:
                    raise LedgerStoreError("instance_missing")
                genesis_sequence = int(genesis["genesis_sequence"])
                genesis_digest = genesis["genesis_content_sha256"]
                if last_committed != genesis_sequence or last_digest != genesis_digest:
                    raise LedgerStoreError("counter_head_mismatch")
            else:
                if max_sequence != last_committed:
                    raise LedgerStoreError("counter_head_mismatch")
                cur.execute(
                    """
                    SELECT content_sha256
                    FROM evidence_handoff_entries
                    WHERE ledger_instance_id = %s AND sequence = %s
                    """,
                    (self._ledger_instance_id, last_committed),
                )
                head_row = cur.fetchone()
                if head_row is None or head_row["content_sha256"] != last_digest:
                    raise LedgerStoreError("counter_head_mismatch")

            sequence = last_committed + 1
            entry_id = str(uuid.uuid4())
            created_at = datetime.now(UTC).isoformat()
            envelope_fields: dict[str, Any] = {
                "sequence": sequence,
                "ledger_instance_id": self._ledger_instance_id,
                "entry_id": entry_id,
                "schema_id": sanitized.schema_id,
                "kind": sanitized.kind.value,
                "context_id": sanitized.context_id,
                "task_id": sanitized.task_id,
                "in_reply_to": sanitized.in_reply_to,
                "recipient_agent_ids": list(sanitized.recipient_agent_ids),
                "message": sanitized.message.to_mapping(),
                "artifacts": [item.to_mapping() for item in sanitized.artifacts],
                "principal_id": identity.principal_id,
                "agent_id": identity.agent_id,
                "caller_role": identity.caller_role,
                "authority": identity.authority,
                "attestation": None,
                "created_at": created_at,
                "idempotency_key": idempotency_key,
                "prev_content_sha256": last_digest,
            }
            digest = content_sha256_for_envelope(envelope_fields)
            cur.execute(
                """
                INSERT INTO evidence_handoff_entries (
                    sequence, ledger_instance_id, entry_id, schema_id, kind, context_id, task_id,
                    in_reply_to, recipient_agent_ids, message_json, artifacts_json, principal_id,
                    agent_id, caller_role, authority, attestation, created_at, idempotency_key,
                    prev_content_sha256, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s::jsonb, %s::jsonb, %s,
                    %s, %s, %s, NULL, %s::timestamptz, %s,
                    %s, %s
                )
                """,
                (
                    sequence,
                    self._ledger_instance_id,
                    entry_id,
                    sanitized.schema_id,
                    sanitized.kind.value,
                    sanitized.context_id,
                    sanitized.task_id,
                    sanitized.in_reply_to,
                    list(sanitized.recipient_agent_ids),
                    json.dumps(sanitized.message.to_mapping(), separators=(",", ":"), sort_keys=True),
                    json.dumps(
                        [item.to_mapping() for item in sanitized.artifacts],
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    identity.principal_id,
                    identity.agent_id,
                    identity.caller_role,
                    identity.authority,
                    created_at,
                    idempotency_key,
                    last_digest,
                    digest,
                ),
            )
            cur.execute(
                """
                UPDATE evidence_handoff_counter
                SET last_committed = %s, last_content_sha256 = %s
                WHERE ledger_instance_id = %s
                """,
                (sequence, digest, self._ledger_instance_id),
            )
            if commit:
                conn.commit()
            return AppendResult(
                entry_id=entry_id,
                sequence=sequence,
                ledger_instance_id=self._ledger_instance_id,
                content_sha256=digest,
                idempotent_replay=False,
            )

    def current_status(self) -> StoreStatus:
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT last_committed, last_content_sha256
                FROM evidence_handoff_counter
                WHERE ledger_instance_id = %s
                """,
                (self._ledger_instance_id,),
            ).fetchone()
            if row is None:
                raise LedgerStoreError("counter_missing")
            return StoreStatus(
                ledger_instance_id=self._ledger_instance_id,
                last_committed=int(row["last_committed"]),
                last_content_sha256=row["last_content_sha256"],
            )

    def get_entry_by_sequence(self, sequence: int) -> dict[str, Any]:
        """Return content-free identity fields for a committed sequence."""
        if sequence < 1:
            raise LedgerValidationError("invalid_sequence")
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT entry_id, sequence, ledger_instance_id, content_sha256
                FROM evidence_handoff_entries
                WHERE ledger_instance_id = %s AND sequence = %s
                """,
                (self._ledger_instance_id, int(sequence)),
            ).fetchone()
        if row is None:
            raise LedgerStoreError("entry_not_found")
        return {
            "entry_id": str(row["entry_id"]),
            "sequence": int(row["sequence"]),
            "ledger_instance_id": str(row["ledger_instance_id"]),
            "content_sha256": str(row["content_sha256"]),
        }

    def read_verified_global_range(self, *, start: int, watermark: int) -> VerifiedRange:
        if start < 1 or watermark < start:
            raise LedgerValidationError("invalid_range")
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM evidence_handoff_entries
                WHERE ledger_instance_id = %s AND sequence >= %s AND sequence <= %s
                ORDER BY sequence ASC
                """,
                (self._ledger_instance_id, start, watermark),
            ).fetchall()
            expected = list(range(start, watermark + 1))
            actual = [int(row["sequence"]) for row in rows]
            if actual != expected:
                raise LedgerStoreError("sequence_gap")
            entries = tuple(self._row_to_envelope(row) for row in rows)
            self._verify_chain(entries)
            return VerifiedRange(entries=entries, start=start, watermark=watermark)

    def verify_full(
        self,
        external_witnesses: tuple[dict[str, Any], ...] = (),
    ) -> IntegrityWitness:
        self._refuse_if_integrity_latched()
        status = self.current_status()
        for witness in external_witnesses:
            witness_instance = str(witness.get("ledger_instance_id", ""))
            if witness_instance and witness_instance != self._ledger_instance_id:
                raise LedgerIntegrityError(
                    cause=IntegrityCause.LEDGER_INSTANCE_MISMATCH,
                    ledger_instance_id=self._ledger_instance_id,
                    safe_boundary_sequence=0,
                )
            witness_committed = int(witness.get("last_committed", 0))
            if witness_committed > status.last_committed:
                raise LedgerIntegrityError(
                    cause=IntegrityCause.ROLLBACK_DIVERGENCE,
                    ledger_instance_id=self._ledger_instance_id,
                    safe_boundary_sequence=status.last_committed,
                )
        if status.last_committed == 0:
            return IntegrityWitness(
                ledger_instance_id=self._ledger_instance_id,
                last_committed=0,
                last_content_sha256=None,
                verified=True,
            )
        self._audit_through_head(status)
        return IntegrityWitness(
            ledger_instance_id=self._ledger_instance_id,
            last_committed=status.last_committed,
            last_content_sha256=status.last_content_sha256,
            verified=True,
        )

    def verify_unfiltered_range(
        self,
        *,
        reader_cursor: int,
        watermark: int,
        anchor: object,
    ) -> VerifiedRange:
        """Verify contiguous global positions from start through watermark.

        ``reader_cursor`` is the first sequence to include (confirmed_cursor + 1).
        Chain continuity is anchored by ``anchor``'s digest (cursor chain head).
        """
        self._refuse_if_integrity_latched()
        start = int(reader_cursor)
        end = int(watermark)
        if start < 1 or end < start:
            raise LedgerValidationError("invalid_range")
        expected_prev = getattr(anchor, "last_content_sha256", None)
        if expected_prev is None and isinstance(anchor, dict):
            expected_prev = anchor.get("last_content_sha256")
        try:
            with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM evidence_handoff_entries
                    WHERE ledger_instance_id = %s AND sequence >= %s AND sequence <= %s
                    ORDER BY sequence ASC
                    """,
                    (self._ledger_instance_id, start, end),
                ).fetchall()
                expected = list(range(start, end + 1))
                actual = [int(row["sequence"]) for row in rows]
                if actual != expected:
                    raise LedgerStoreError("sequence_gap")
                entries = tuple(self._row_to_envelope(row) for row in rows)
                self._verify_chain_from(entries, expected_prev=expected_prev)
                return VerifiedRange(entries=entries, start=start, watermark=end)
        except LedgerStoreError as exc:
            if exc.code == "sequence_gap":
                raise LedgerIntegrityError(
                    cause=IntegrityCause.SEQUENCE_GAP,
                    ledger_instance_id=self._ledger_instance_id,
                    safe_boundary_sequence=max(start - 1, 0),
                ) from exc
            if exc.code == "chain_break":
                raise LedgerIntegrityError(
                    cause=IntegrityCause.CHAIN_BREAK,
                    ledger_instance_id=self._ledger_instance_id,
                    safe_boundary_sequence=max(start - 1, 0),
                ) from exc
            raise

    def head_witness(self) -> IntegrityWitness:
        status = self.current_status()
        return IntegrityWitness(
            ledger_instance_id=self._ledger_instance_id,
            last_committed=status.last_committed,
            last_content_sha256=status.last_content_sha256,
            verified=True,
        )

    def get_cursor(
        self,
        *,
        principal_id: str,
        agent_id: str,
        ledger_instance_id: str,
    ) -> Any:
        if ledger_instance_id != self._ledger_instance_id:
            raise LedgerStoreError("ledger_instance_mismatch")
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT confirmed_sequence, chain_head_sha256
                FROM evidence_handoff_delivery_cursors
                WHERE principal_id = %s AND agent_id = %s AND ledger_instance_id = %s
                """,
                (principal_id, agent_id, ledger_instance_id),
            ).fetchone()
        if row is None:
            return type(
                "CursorRow",
                (),
                {"confirmed_sequence": 0, "chain_head_sha256": None},
            )()
        return type(
            "CursorRow",
            (),
            {
                "confirmed_sequence": int(row["confirmed_sequence"]),
                "chain_head_sha256": row["chain_head_sha256"],
            },
        )()

    def count_visible_unread(
        self,
        *,
        agent_id: str,
        ledger_instance_id: str,
        after_sequence: int,
    ) -> int:
        if ledger_instance_id != self._ledger_instance_id:
            raise LedgerStoreError("ledger_instance_mismatch")
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM evidence_handoff_entries
                WHERE ledger_instance_id = %s
                  AND sequence > %s
                  AND %s = ANY (recipient_agent_ids)
                """,
                (ledger_instance_id, int(after_sequence), str(agent_id)),
            ).fetchone()
        return int(row["n"] if row is not None else 0)

    def issue_delivery_token(self, *, token: DeliveryToken) -> DeliveryToken:
        if token.ledger_instance_id != self._ledger_instance_id:
            raise DeliveryError("token_instance_mismatch")
        payload = {
            "token_id": token.token_id,
            "principal_id": token.principal_id,
            "agent_id": token.agent_id,
            "ledger_instance_id": token.ledger_instance_id,
            "previous_cursor": token.previous_cursor,
            "previous_witness": {
                "ledger_instance_id": token.previous_witness.ledger_instance_id,
                "last_committed": token.previous_witness.last_committed,
                "last_content_sha256": token.previous_witness.last_content_sha256,
                "verified": token.previous_witness.verified,
            },
            "watermark": token.watermark,
            "resulting_witness": {
                "ledger_instance_id": token.resulting_witness.ledger_instance_id,
                "last_committed": token.resulting_witness.last_committed,
                "last_content_sha256": token.resulting_witness.last_content_sha256,
                "verified": token.resulting_witness.verified,
            },
            "visible_entry_ids": list(token.visible_entry_ids),
            "page_digest": token.page_digest,
            "expires_at": token.expires_at.isoformat(),
        }
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO evidence_handoff_delivery_tokens(
                    token_id, principal_id, ledger_instance_id, payload_json, expires_at, consumed_at
                ) VALUES (%s, %s, %s, %s::jsonb, %s, NULL)
                """,
                (
                    token.token_id,
                    token.principal_id,
                    token.ledger_instance_id,
                    json.dumps(payload, sort_keys=True),
                    token.expires_at,
                ),
            )
            conn.commit()
        return token

    def consume_delivery_token(
        self,
        *,
        token_id: str,
        principal_id: str,
        now: datetime,
    ) -> DeliveryToken:
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT token_id, principal_id, ledger_instance_id, payload_json, expires_at, consumed_at
                FROM evidence_handoff_delivery_tokens
                WHERE token_id = %s
                FOR UPDATE
                """,
                (token_id,),
            ).fetchone()
            if row is None:
                raise DeliveryError("token_invalid")
            if str(row["principal_id"]) != str(principal_id):
                raise DeliveryError("token_principal_mismatch")
            if row["consumed_at"] is not None:
                raise DeliveryError("token_replayed")
            expires_at = row["expires_at"]
            if getattr(expires_at, "tzinfo", None) is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if now >= expires_at:
                raise DeliveryError("token_expired")
            if str(row["ledger_instance_id"]) != self._ledger_instance_id:
                raise DeliveryError("token_instance_mismatch")
            conn.execute(
                """
                UPDATE evidence_handoff_delivery_tokens
                SET consumed_at = %s
                WHERE token_id = %s AND consumed_at IS NULL
                """,
                (now, token_id),
            )
            conn.commit()
            payload = row["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
        return self._token_from_payload(payload)

    def confirm_cursor_cas(self, *, token: DeliveryToken, now: datetime) -> CursorStatus:
        if token.ledger_instance_id != self._ledger_instance_id:
            raise DeliveryError("token_instance_mismatch")
        chain_head = token.resulting_witness.last_content_sha256
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            existing = conn.execute(
                """
                SELECT confirmed_sequence, chain_head_sha256
                FROM evidence_handoff_delivery_cursors
                WHERE principal_id = %s AND agent_id = %s AND ledger_instance_id = %s
                FOR UPDATE
                """,
                (token.principal_id, token.agent_id, token.ledger_instance_id),
            ).fetchone()
            current = int(existing["confirmed_sequence"]) if existing is not None else 0
            if current != int(token.previous_cursor):
                raise DeliveryError("cursor_cas_conflict")
            conn.execute(
                """
                INSERT INTO evidence_handoff_delivery_cursors(
                    principal_id, agent_id, ledger_instance_id, confirmed_sequence,
                    chain_head_sha256, last_advanced_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (principal_id, agent_id, ledger_instance_id) DO UPDATE
                SET confirmed_sequence = EXCLUDED.confirmed_sequence,
                    chain_head_sha256 = EXCLUDED.chain_head_sha256,
                    last_advanced_at = EXCLUDED.last_advanced_at
                """,
                (
                    token.principal_id,
                    token.agent_id,
                    token.ledger_instance_id,
                    int(token.watermark),
                    chain_head,
                    now,
                ),
            )
            conn.commit()
        unread = self.count_visible_unread(
            agent_id=token.agent_id,
            ledger_instance_id=token.ledger_instance_id,
            after_sequence=int(token.watermark),
        )
        return CursorStatus(
            principal_id=token.principal_id,
            agent_id=token.agent_id,
            confirmed_sequence=int(token.watermark),
            last_advanced_at=now,
            unread_count=unread,
            witness=token.resulting_witness,
        )

    def _token_from_payload(self, payload: dict[str, Any]) -> DeliveryToken:
        prev = payload["previous_witness"]
        resulting = payload["resulting_witness"]
        expires_raw = payload["expires_at"]
        if isinstance(expires_raw, str):
            expires_at = datetime.fromisoformat(expires_raw)
        else:
            expires_at = expires_raw
        if getattr(expires_at, "tzinfo", None) is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return DeliveryToken(
            token_id=str(payload["token_id"]),
            principal_id=str(payload["principal_id"]),
            agent_id=str(payload["agent_id"]),
            ledger_instance_id=str(payload["ledger_instance_id"]),
            previous_cursor=int(payload["previous_cursor"]),
            previous_witness=IntegrityWitness(
                ledger_instance_id=str(prev["ledger_instance_id"]),
                last_committed=int(prev["last_committed"]),
                last_content_sha256=prev.get("last_content_sha256"),
                verified=bool(prev.get("verified", True)),
            ),
            watermark=int(payload["watermark"]),
            resulting_witness=IntegrityWitness(
                ledger_instance_id=str(resulting["ledger_instance_id"]),
                last_committed=int(resulting["last_committed"]),
                last_content_sha256=resulting.get("last_content_sha256"),
                verified=bool(resulting.get("verified", True)),
            ),
            visible_entry_ids=tuple(str(item) for item in payload.get("visible_entry_ids") or ()),
            page_digest=str(payload["page_digest"]),
            expires_at=expires_at,
        )

    def _verify_chain_from(
        self,
        entries: tuple[ImmutableEntryEnvelope, ...],
        *,
        expected_prev: str | None,
    ) -> None:
        prev_digest = expected_prev
        for entry in entries:
            if entry.prev_content_sha256 != prev_digest:
                raise LedgerStoreError("chain_break")
            fields = entry.to_mapping()
            if content_sha256_for_envelope(fields) != entry.content_sha256:
                raise LedgerStoreError("chain_break")
            prev_digest = entry.content_sha256

    def find_last_verified_anchor(self, instance_id: str) -> Any:
        from evidence_handoff_runtime.recovery import RecoveryAnchor

        if instance_id != self._ledger_instance_id:
            raise LedgerIntegrityError(
                cause=IntegrityCause.LEDGER_INSTANCE_MISMATCH,
                ledger_instance_id=self._ledger_instance_id,
                safe_boundary_sequence=0,
            )
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM evidence_handoff_entries
                WHERE ledger_instance_id = %s
                ORDER BY sequence ASC
                """,
                (self._ledger_instance_id,),
            ).fetchall()
        prev_digest: str | None = None
        last_seq = 0
        last_digest: str | None = None
        for row in rows:
            entry = self._row_to_envelope(row)
            expected = 1 if last_seq == 0 else last_seq + 1
            if entry.sequence != expected:
                break
            if entry.prev_content_sha256 != prev_digest:
                break
            if content_sha256_for_envelope(entry.to_mapping()) != entry.content_sha256:
                break
            last_seq = entry.sequence
            last_digest = entry.content_sha256
            prev_digest = entry.content_sha256
        if last_seq == 0 or last_digest is None:
            raise LedgerStoreError("no_verified_anchor")
        return RecoveryAnchor(
            ledger_instance_id=self._ledger_instance_id,
            sequence=last_seq,
            content_sha256=last_digest,
            verified=True,
        )

    def create_linked_replacement(self, *, incident: IntegrityIncident, anchor: Any) -> dict[str, Any]:
        replacement_id = str(uuid.uuid4())
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO evidence_handoff_ledger_instance(
                    ledger_instance_id, genesis_sequence, genesis_content_sha256
                ) VALUES (%s, %s, %s)
                """,
                (replacement_id, int(anchor.sequence), str(anchor.content_sha256)),
            )
            conn.execute(
                """
                INSERT INTO evidence_handoff_counter(
                    ledger_instance_id, last_committed, last_content_sha256
                ) VALUES (%s, %s, %s)
                """,
                (replacement_id, int(anchor.sequence), str(anchor.content_sha256)),
            )
            conn.execute(
                """
                INSERT INTO evidence_handoff_control_state(key, value_json)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = NOW()
                """,
                (
                    f"recovery:{replacement_id}",
                    json.dumps(
                        {
                            "incident_id": incident.incident_id,
                            "predecessor_instance_id": self._ledger_instance_id,
                            "recovery_anchor_sequence": int(anchor.sequence),
                            "recovery_anchor_digest": str(anchor.content_sha256),
                        },
                        sort_keys=True,
                    ),
                ),
            )
            conn.commit()
        return {
            "ledger_instance_id": replacement_id,
            "predecessor_instance_id": self._ledger_instance_id,
            "recovery_anchor_sequence": int(anchor.sequence),
            "recovery_anchor_digest": str(anchor.content_sha256),
            "incident_id": incident.incident_id,
        }

    def mirror_integrity_incident(self, incident: IntegrityIncident) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO evidence_handoff_control_state(key, value_json)
                VALUES ('integrity_latch', %s::jsonb)
                ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = NOW()
                """,
                (json.dumps(incident.to_public_mapping(), sort_keys=True),),
            )
            conn.commit()

    def _load_mirrored_integrity_incident(self) -> IntegrityIncident | None:
        """Load the durable latch from evidence_handoff_control_state (always available)."""
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT value_json
                FROM evidence_handoff_control_state
                WHERE key = %s
                """,
                ("integrity_latch",),
            ).fetchone()
        if row is None or row.get("value_json") is None:
            return None
        payload = row["value_json"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return None
        if not isinstance(payload, dict):
            return None
        try:
            return IntegrityIncident(
                incident_id=str(payload["incident_id"]),
                cause=IntegrityCause(str(payload["cause"])),
                ledger_instance_id=str(payload["ledger_instance_id"]),
                safe_boundary_sequence=int(payload["safe_boundary_sequence"]),
                detected_at=str(payload["detected_at"]),
                disposition=str(payload["disposition"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _load_integrity_incident(self) -> IntegrityIncident | None:
        """DB mirror is primary; control_root file is an optional secondary source."""
        mirrored = self._load_mirrored_integrity_incident()
        if mirrored is not None:
            return mirrored
        if self._control_root is None:
            return None
        return IntegrityLatch(control_root=self._control_root).load()

    def _refuse_if_integrity_latched(self) -> None:
        incident = self._load_integrity_incident()
        if incident is None:
            return
        # Latch binds to the failed instance; a linked replacement must still accept writes.
        if incident.ledger_instance_id != self._ledger_instance_id:
            return
        raise LedgerIntegrityError(
            cause=incident.cause,
            ledger_instance_id=incident.ledger_instance_id,
            safe_boundary_sequence=incident.safe_boundary_sequence,
            incident_id=incident.incident_id,
            detected_at=incident.detected_at,
            disposition=incident.disposition,
        )

    def _audit_through_head(self, status: StoreStatus) -> None:
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM evidence_handoff_entries
                WHERE ledger_instance_id = %s
                ORDER BY sequence ASC
                """,
                (self._ledger_instance_id,),
            ).fetchall()
            by_sequence: dict[int, list[dict[str, Any]]] = {}
            for row in rows:
                by_sequence.setdefault(int(row["sequence"]), []).append(row)

            for sequence in sorted(by_sequence):
                if len(by_sequence[sequence]) > 1:
                    raise LedgerIntegrityError(
                        cause=IntegrityCause.SEQUENCE_DUPLICATE,
                        ledger_instance_id=self._ledger_instance_id,
                        safe_boundary_sequence=max(sequence - 1, 0),
                    )

            prev_digest: str | None = None
            verified_through = 0
            for sequence in range(1, status.last_committed + 1):
                matches = by_sequence.get(sequence, [])
                if not matches:
                    foreign = conn.execute(
                        """
                        SELECT ledger_instance_id
                        FROM evidence_handoff_entries
                        WHERE sequence = %s
                        LIMIT 1
                        """,
                        (sequence,),
                    ).fetchone()
                    if (
                        foreign is not None
                        and foreign["ledger_instance_id"] != self._ledger_instance_id
                    ):
                        raise LedgerIntegrityError(
                            cause=IntegrityCause.LEDGER_INSTANCE_MISMATCH,
                            ledger_instance_id=self._ledger_instance_id,
                            safe_boundary_sequence=0,
                        )
                    raise LedgerIntegrityError(
                        cause=IntegrityCause.SEQUENCE_GAP,
                        ledger_instance_id=self._ledger_instance_id,
                        safe_boundary_sequence=max(sequence - 1, 0),
                    )
                entry = self._row_to_envelope(matches[0])
                if entry.ledger_instance_id != self._ledger_instance_id:
                    raise LedgerIntegrityError(
                        cause=IntegrityCause.LEDGER_INSTANCE_MISMATCH,
                        ledger_instance_id=self._ledger_instance_id,
                        safe_boundary_sequence=0,
                    )
                if entry.prev_content_sha256 != prev_digest:
                    raise LedgerIntegrityError(
                        cause=IntegrityCause.CHAIN_BREAK,
                        ledger_instance_id=self._ledger_instance_id,
                        safe_boundary_sequence=verified_through,
                    )
                if content_sha256_for_envelope(entry.to_mapping()) != entry.content_sha256:
                    raise LedgerIntegrityError(
                        cause=IntegrityCause.CHAIN_BREAK,
                        ledger_instance_id=self._ledger_instance_id,
                        safe_boundary_sequence=verified_through,
                    )
                prev_digest = entry.content_sha256
                verified_through = sequence

            if status.last_content_sha256 != prev_digest:
                raise LedgerIntegrityError(
                    cause=IntegrityCause.COUNTER_HEAD_MISMATCH,
                    ledger_instance_id=self._ledger_instance_id,
                    safe_boundary_sequence=max(status.last_committed - 1, 0),
                )

    def _verify_chain(self, entries: tuple[ImmutableEntryEnvelope, ...]) -> None:
        prev_digest: str | None = None
        for entry in entries:
            if entry.prev_content_sha256 != prev_digest:
                raise LedgerStoreError("chain_break")
            fields = entry.to_mapping()
            if content_sha256_for_envelope(fields) != entry.content_sha256:
                raise LedgerStoreError("chain_break")
            prev_digest = entry.content_sha256

    def _row_to_envelope(self, row: dict[str, Any]) -> ImmutableEntryEnvelope:
        message_json = row["message_json"]
        artifacts_json = row["artifacts_json"]
        parts = tuple(
            MessagePart(kind=part["kind"], text=part.get("text"), data=part.get("data"))
            for part in message_json["parts"]
        )
        artifacts = tuple(
            ArtifactRef(
                name=item["name"],
                content_sha256=item["content_sha256"],
                uri=item.get("uri"),
                media_type=item.get("media_type"),
            )
            for item in artifacts_json
        )
        created_at = row["created_at"]
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        return ImmutableEntryEnvelope(
            sequence=int(row["sequence"]),
            ledger_instance_id=row["ledger_instance_id"],
            entry_id=row["entry_id"],
            schema_id=row["schema_id"],
            kind=EntryKind(row["kind"]),
            context_id=row["context_id"],
            task_id=row["task_id"],
            in_reply_to=row["in_reply_to"],
            recipient_agent_ids=tuple(row["recipient_agent_ids"]),
            message=EntryMessage(parts=parts),
            artifacts=artifacts,
            principal_id=row["principal_id"],
            agent_id=row["agent_id"],
            caller_role=row["caller_role"],
            authority=row["authority"],
            attestation=None,
            created_at=str(created_at),
            idempotency_key=row["idempotency_key"],
            prev_content_sha256=row["prev_content_sha256"],
            content_sha256=row["content_sha256"],
        )

    def upsert_reader_capability(self, capability: ReaderCapability) -> None:
        schemas = sorted(str(item) for item in capability.supported_schemas)
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO evidence_handoff_reader_capabilities(
                    principal_id, agent_id, ledger_instance_id, supported_schemas,
                    reported_at, retired
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (principal_id, ledger_instance_id) DO UPDATE
                SET agent_id = EXCLUDED.agent_id,
                    supported_schemas = EXCLUDED.supported_schemas,
                    reported_at = EXCLUDED.reported_at,
                    retired = EXCLUDED.retired
                """,
                (
                    capability.principal_id,
                    capability.agent_id,
                    self._ledger_instance_id,
                    schemas,
                    capability.reported_at,
                    bool(capability.retired),
                ),
            )
            conn.commit()

    def get_reader_capability(self, principal_id: str) -> ReaderCapability:
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT principal_id, agent_id, supported_schemas, reported_at, retired
                FROM evidence_handoff_reader_capabilities
                WHERE principal_id = %s AND ledger_instance_id = %s
                """,
                (principal_id, self._ledger_instance_id),
            ).fetchone()
        if row is None:
            raise LedgerStoreError("capability_not_found")
        return self._row_to_reader_capability(row)

    def list_reader_capabilities(self) -> tuple[ReaderCapability, ...]:
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT principal_id, agent_id, supported_schemas, reported_at, retired
                FROM evidence_handoff_reader_capabilities
                WHERE ledger_instance_id = %s
                ORDER BY principal_id ASC
                """,
                (self._ledger_instance_id,),
            ).fetchall()
        return tuple(self._row_to_reader_capability(row) for row in rows)

    def retired_agent_ids(self) -> frozenset[str]:
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT agent_id
                FROM evidence_handoff_reader_capabilities
                WHERE ledger_instance_id = %s AND retired = TRUE
                """,
                (self._ledger_instance_id,),
            ).fetchall()
        return frozenset(str(row["agent_id"]) for row in rows)

    def is_writer_active(self, schema_id: str) -> bool:
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT writer_active
                FROM evidence_handoff_capabilities
                WHERE schema_id = %s
                """,
                (schema_id,),
            ).fetchone()
        return bool(row and row["writer_active"])

    def set_writer_active(self, schema_id: str, *, active: bool) -> ActivationStatus:
        now = datetime.now(tz=UTC)
        with psycopg.connect(self._conninfo) as conn:
            updated = conn.execute(
                """
                UPDATE evidence_handoff_capabilities
                SET writer_active = %s
                WHERE schema_id = %s
                """,
                (bool(active), schema_id),
            )
            if updated.rowcount == 0:
                conn.execute(
                    """
                    INSERT INTO evidence_handoff_capabilities(
                        schema_id, kind, writer_active, reader_active
                    ) VALUES (%s, %s, %s, TRUE)
                    """,
                    (schema_id, schema_id.split(".")[0], bool(active)),
                )
            conn.commit()
        return ActivationStatus(schema_id=schema_id, writer_active=bool(active), activated_at=now)

    def retire_principal(
        self, principal_id: str, *, agent_id: str | None = None
    ) -> AdministrativeAuditResult:
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT agent_id
                FROM evidence_handoff_reader_capabilities
                WHERE principal_id = %s AND ledger_instance_id = %s
                FOR UPDATE
                """,
                (principal_id, self._ledger_instance_id),
            ).fetchone()
            if row is None:
                if not agent_id:
                    raise LedgerStoreError("capability_not_found")
                conn.execute(
                    """
                    INSERT INTO evidence_handoff_reader_capabilities(
                        principal_id, agent_id, ledger_instance_id, supported_schemas,
                        reported_at, retired
                    ) VALUES (%s, %s, %s, %s, %s, TRUE)
                    """,
                    (
                        principal_id,
                        agent_id,
                        self._ledger_instance_id,
                        [],
                        datetime.now(tz=UTC),
                    ),
                )
                resolved_agent = str(agent_id)
            else:
                resolved_agent = str(row["agent_id"])
                conn.execute(
                    """
                    UPDATE evidence_handoff_reader_capabilities
                    SET retired = TRUE
                    WHERE principal_id = %s AND ledger_instance_id = %s
                    """,
                    (principal_id, self._ledger_instance_id),
                )
            agent_id = resolved_agent
            audit_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO evidence_handoff_audit(event_type, payload_json)
                VALUES (%s, %s::jsonb)
                """,
                (
                    "administrative_retire_principal",
                    json.dumps(
                        {
                            "principal_id": principal_id,
                            "agent_id": agent_id,
                            "audit_event_id": audit_id,
                            "retired": True,
                        },
                        sort_keys=True,
                    ),
                ),
            )
            conn.commit()
        return AdministrativeAuditResult(
            principal_id=principal_id,
            agent_id=agent_id,
            retired=True,
            audit_event_id=audit_id,
        )

    def touch_authenticated_request(
        self,
        *,
        principal_id: str,
        agent_id: str,
        now: datetime,
        warning_incident_id: str | None = None,
    ) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO evidence_handoff_reader_capabilities(
                    principal_id, agent_id, ledger_instance_id, supported_schemas,
                    reported_at, retired, last_authenticated_request_at,
                    warning_delivered_incident_id
                ) VALUES (%s, %s, %s, %s, %s, FALSE, %s, %s)
                ON CONFLICT (principal_id, ledger_instance_id) DO UPDATE
                SET last_authenticated_request_at = EXCLUDED.last_authenticated_request_at,
                    warning_delivered_incident_id = COALESCE(
                        EXCLUDED.warning_delivered_incident_id,
                        evidence_handoff_reader_capabilities.warning_delivered_incident_id
                    )
                """,
                (
                    principal_id,
                    agent_id,
                    self._ledger_instance_id,
                    [],
                    now,
                    now,
                    warning_incident_id,
                ),
            )
            conn.commit()

    def global_integrity_fact(self) -> dict[str, Any]:
        incident = self._load_integrity_incident()
        if incident is None:
            return {
                "latched": False,
                "incident_id": None,
                "cause": None,
                "safe_boundary_sequence": None,
            }
        cause = getattr(incident.cause, "value", incident.cause)
        return {
            "latched": True,
            "incident_id": incident.incident_id,
            "cause": str(cause),
            "safe_boundary_sequence": incident.safe_boundary_sequence,
        }

    def list_delivery_facts(
        self,
        *,
        now: datetime | None = None,
        stale_after: Any | None = None,
    ) -> tuple[dict[str, Any], ...]:
        from datetime import timedelta as _timedelta

        from evidence_handoff_runtime.capabilities import CAPABILITY_STALE_AFTER

        integrity = self.global_integrity_fact()
        incident_id = integrity.get("incident_id")
        clock = now or datetime.now(tz=UTC)
        freshness_window = (
            stale_after if isinstance(stale_after, _timedelta) else CAPABILITY_STALE_AFTER
        )
        with psycopg.connect(self._conninfo, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT
                    rc.principal_id,
                    rc.agent_id,
                    rc.supported_schemas,
                    rc.reported_at,
                    rc.retired,
                    rc.last_authenticated_request_at,
                    rc.warning_delivered_incident_id,
                    dc.confirmed_sequence,
                    dc.last_advanced_at
                FROM evidence_handoff_reader_capabilities rc
                LEFT JOIN evidence_handoff_delivery_cursors dc
                  ON dc.principal_id = rc.principal_id
                 AND dc.agent_id = rc.agent_id
                 AND dc.ledger_instance_id = rc.ledger_instance_id
                WHERE rc.ledger_instance_id = %s
                ORDER BY rc.principal_id ASC
                """,
                (self._ledger_instance_id,),
            ).fetchall()
        facts: list[dict[str, Any]] = []
        for row in rows:
            confirmed = int(row["confirmed_sequence"] or 0)
            unread = self.count_visible_unread(
                agent_id=str(row["agent_id"]),
                ledger_instance_id=self._ledger_instance_id,
                after_sequence=confirmed,
            )
            warning = "not_yet_requested"
            delivered_id = row.get("warning_delivered_incident_id")
            if incident_id and delivered_id and str(delivered_id) == str(incident_id):
                warning = "delivered"
            schemas = row.get("supported_schemas") or ()
            facts.append(
                {
                    "agent_id": str(row["agent_id"]),
                    "principal_id": str(row["principal_id"]),
                    "principal_status": "retired" if row["retired"] else "active",
                    "confirmed_sequence": confirmed,
                    "last_confirmed_at": row.get("last_advanced_at"),
                    "visible_unread_count": unread,
                    "last_authenticated_request_at": row.get("last_authenticated_request_at"),
                    "last_acknowledgement_sequence": None,
                    "last_acknowledgement_at": None,
                    "capability_reported_at": row.get("reported_at"),
                    "capability_fresh": capability_report_is_fresh(
                        row.get("reported_at"),
                        now=clock,
                        stale_after=freshness_window,
                        has_schemas=bool(schemas),
                    ),
                    "activation_blocked": False,
                    "warning_delivery": warning,
                }
            )
        return tuple(facts)

    def rebuild_delivery_projection(self) -> dict[str, Any]:
        facts = self.list_delivery_facts()
        return {
            "rebuilt_rows": len(facts),
            "source": "canonical_entries",
            "authoritative_for_entry_content": False,
        }

    def _row_to_reader_capability(self, row: dict[str, Any]) -> ReaderCapability:
        schemas = row["supported_schemas"] or ()
        reported = row["reported_at"]
        if getattr(reported, "tzinfo", None) is None:
            reported = reported.replace(tzinfo=UTC)
        return ReaderCapability(
            agent_id=str(row["agent_id"]),
            principal_id=str(row["principal_id"]),
            supported_schemas=frozenset(str(item) for item in schemas),
            reported_at=reported,
            retired=bool(row["retired"]),
        )


__all__ = ["PostgresLedgerStore"]
