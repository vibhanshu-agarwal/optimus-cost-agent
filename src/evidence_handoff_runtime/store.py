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
from evidence_handoff_runtime.integrity import (
    IntegrityCause,
    IntegrityIncident,
    IntegrityLatch,
    LedgerIntegrityError,
)


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

    def append(
        self,
        sanitized: SanitizedDraft,
        identity: ServerIdentity,
        *,
        idempotency_key: str,
    ) -> AppendResult:
        self._refuse_if_integrity_latched()
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
        self._refuse_if_integrity_latched()
        try:
            return self.read_verified_global_range(start=reader_cursor, watermark=watermark)
        except LedgerStoreError as exc:
            if exc.code == "sequence_gap":
                raise LedgerIntegrityError(
                    cause=IntegrityCause.SEQUENCE_GAP,
                    ledger_instance_id=self._ledger_instance_id,
                    safe_boundary_sequence=max(reader_cursor - 1, 0),
                ) from exc
            if exc.code == "chain_break":
                raise LedgerIntegrityError(
                    cause=IntegrityCause.CHAIN_BREAK,
                    ledger_instance_id=self._ledger_instance_id,
                    safe_boundary_sequence=max(reader_cursor - 1, 0),
                ) from exc
            raise

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

    def _refuse_if_integrity_latched(self) -> None:
        if self._control_root is None:
            return
        incident = IntegrityLatch(control_root=self._control_root).load()
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


__all__ = ["PostgresLedgerStore"]
