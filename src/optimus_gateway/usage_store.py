"""The Gateway-owned Postgres ledger for durable usage capture (Plan 12.8; memory design v4 section 7; ADR-032).

Only the Gateway holds the database credential. One transaction per batch: a per-stream advisory lock and the
committed cursor; an idempotent replay of records already committed (each must carry its stored digest); the ordering
check (`durable_outbox.follows`) for each new record; the immutable event; the receipt projection (the original
receipt, an alias for an identical replay of a settled Gateway request, or conflict evidence that is never a charge);
the coverage projection; the cursor advance. Only a committed batch is acknowledged, naming this ledger instance, the
stream, the sequence and the digest. Facts are immutable in the database itself (migration 001's triggers).

A stream this ledger has never seen whose sender believes an earlier prefix was committed (by a replaced ledger, or
before its acknowledged segments were compacted) starts here with an explicit gap: the prefix is recorded as
unavailable to this ledger, never certified. Migrations are digest-pinned like the evidence ledger's, in their own
schema; this module never opens the evidence-handoff store or its database.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import make_conninfo

from optimus_security import usage_capture_contract as uc
from optimus_security.accounting_config import AccountingConfig
from optimus_security.durable_outbox import GAP_KIND, GENESIS, Record, follows

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_ROOT = REPO_ROOT / "migrations" / "optimus_usage"
# Digests are pinned to LF-normalized SQL bytes; changing a migration requires a new file.
_PINNED: tuple[tuple[str, str], ...] = (
    ("001_durable_capture.sql", "90b54892de149c8e6b73bfbdd5ea6f59cd0523c22e0b7c8f79c446e557cded77"),  # pragma: allowlist secret - SQL migration integrity hash, not a credential
)


class StoreError(Exception):
    """``code``: unavailable (retryable), migration_file_missing, migration_digest_mismatch, cursor_mismatch,
    order or duplicate_event. Never carries record content."""

    def __init__(self, code: str, *, committed: tuple[int, str] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.committed = committed


@dataclass(frozen=True)
class IngestResult:
    ack: uc.CaptureAck
    inserted: int
    replayed: int


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def verify_migrations() -> None:
    for filename, pinned in _PINNED:
        path = MIGRATIONS_ROOT / filename
        if not path.is_file():
            raise StoreError("migration_file_missing")
        if _digest(path) != pinned:
            raise StoreError("migration_digest_mismatch")


class UsageStore:
    """One ledger instance in one database. Each operation opens its own connection (as the evidence store does)."""

    def __init__(self, conninfo: str, *, connect_timeout: int = 5) -> None:
        self._conninfo = conninfo
        self._connect_timeout = connect_timeout
        self.ledger_instance: str | None = None

    @classmethod
    def from_config(cls, config: AccountingConfig, password: str) -> UsageStore:
        """A store for the approved configuration, with the password the Gateway resolved from its own keyring namespace.
        The password is only ever in this process's connection string, never logged or persisted."""
        conninfo = make_conninfo(host=config.host, port=config.port, dbname=config.database, user=config.user, password=password)
        return cls(conninfo, connect_timeout=config.connect_timeout_seconds)

    def _connect(self) -> psycopg.Connection[Any]:
        try:
            return psycopg.connect(self._conninfo, connect_timeout=self._connect_timeout)
        except psycopg.OperationalError:
            raise StoreError("unavailable") from None

    def migrate(self) -> str:
        """Apply the pinned migrations (refusing changed bytes) and return this database's ledger instance ID."""
        verify_migrations()
        try:
            with self._connect() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS optimus_usage_schema_migrations ("
                    "filename TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
                )
                for filename, pinned in _PINNED:
                    row = conn.execute("SELECT sha256 FROM optimus_usage_schema_migrations WHERE filename = %s", (filename,)).fetchone()
                    if row is not None:
                        if row[0] != pinned:
                            raise StoreError("migration_digest_mismatch")
                        continue
                    conn.execute((MIGRATIONS_ROOT / filename).read_text(encoding="utf-8"))  # type: ignore[arg-type]
                    conn.execute("INSERT INTO optimus_usage_schema_migrations(filename, sha256) VALUES (%s, %s)", (filename, pinned))
                row = conn.execute("SELECT ledger_instance_id FROM optimus_usage.ledger_instance ORDER BY created_at LIMIT 1").fetchone()
                if row is None:
                    instance = uuid.uuid4().hex
                    conn.execute("INSERT INTO optimus_usage.ledger_instance(ledger_instance_id) VALUES (%s)", (instance,))
                else:
                    instance = row[0]
                conn.commit()
        except psycopg.OperationalError:
            raise StoreError("unavailable") from None
        self.ledger_instance = instance
        return instance

    def ingest(self, batch: uc.CaptureBatch) -> IngestResult:
        """Commit one batch atomically and acknowledge exactly what was committed."""
        instance = self.ledger_instance or self.migrate()
        try:
            with self._connect() as conn:
                result = self._ingest(conn, instance, batch)
                conn.commit()
                return result
        except psycopg.OperationalError:
            raise StoreError("unavailable") from None

    def _ingest(self, conn: psycopg.Connection[Any], instance: str, batch: uc.CaptureBatch) -> IngestResult:
        stream = batch.stream_id
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (stream,))
        row = conn.execute(
            "SELECT writer, sequence, record_digest FROM optimus_usage.drain_cursor WHERE ledger_instance_id = %s AND stream_id = %s",
            (instance, stream),
        ).fetchone()
        if row is not None and row[0] != batch.writer:
            raise StoreError("order")  # a stream never changes owner
        base = (row[1], row[2]) if row is not None else None
        replayed = 0
        records = list(batch.records)
        if base is None or batch.after_sequence > base[0]:
            # The sender's committed prefix is ahead of this ledger (a new or replaced ledger, or one restored from an
            # older backup): the missing span is recorded as unavailable here, never certified.
            if batch.after_sequence > (0 if base is None else base[0]):
                self._project_gap(conn, stream, 1 if base is None else base[0] + 1, batch.after_sequence, batch.ledger_instance)
            base = (batch.after_sequence, batch.after_digest)
        else:
            while records and records[0].sequence <= base[0]:
                stored = conn.execute(
                    "SELECT record_digest FROM optimus_usage.capture_event WHERE stream_id = %s AND sequence = %s",
                    (stream, records[0].sequence),
                ).fetchone()
                if stored is None or stored[0] != records[0].digest:
                    raise StoreError("cursor_mismatch", committed=base)
                records.pop(0)
                replayed += 1
            if records and (batch.after_sequence, batch.after_digest) != base and records[0].sequence != base[0] + 1:
                raise StoreError("cursor_mismatch", committed=base)
        conflicts = 0
        for record in records:
            if follows(record, base[0], base[1]):
                raise StoreError("cursor_mismatch" if record.sequence > base[0] + 1 and record.payload.get("kind") != GAP_KIND else "order", committed=base)
            inserted = conn.execute(
                "INSERT INTO optimus_usage.capture_event (stream_id, sequence, event_id, writer, kind, prev_digest, record_digest, payload) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (event_id) DO NOTHING RETURNING sequence",
                (stream, record.sequence, record.event_id, batch.writer, record.payload["kind"], record.prev, record.digest, json.dumps(record.payload)),
            ).fetchone()
            if inserted is None:
                raise StoreError("duplicate_event", committed=base)
            conflicts += self._project(conn, stream, record)
            base = (record.sequence, record.digest)
        if base[0] == 0:
            raise StoreError("order")  # nothing committed and nothing to acknowledge
        if records or row is None:
            conn.execute(
                "INSERT INTO optimus_usage.drain_cursor (ledger_instance_id, stream_id, writer, sequence, record_digest) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (ledger_instance_id, stream_id) DO UPDATE "
                "SET sequence = EXCLUDED.sequence, record_digest = EXCLUDED.record_digest, updated_at = NOW()",
                (instance, stream, batch.writer, base[0], base[1]),
            )
        return IngestResult(uc.CaptureAck(instance, stream, base[0], base[1], conflicts), len(records), replayed)

    def _project_gap(self, conn: psycopg.Connection[Any], stream: str, first: int, last: int, prior_ledger: str | None) -> None:
        conn.execute(
            "INSERT INTO optimus_usage.coverage_epoch (epoch_id, stream_id, state, reasons) VALUES (%s, %s, 'incomplete', %s) "
            "ON CONFLICT (epoch_id) DO NOTHING",
            (f"unavailable:{stream}:{first}-{last}", stream, [f"stream_span_unavailable:{first}-{last}", f"prior_ledger:{prior_ledger or 'unknown'}"]),
        )

    def _project(self, conn: psycopg.Connection[Any], stream: str, record: Record) -> int:
        """Project one new event; returns 1 for a conflicting receipt (recorded as evidence), else 0."""
        payload = record.payload
        kind = payload["kind"]
        if kind == uc.ATTEMPT_RECEIPT:
            return self._project_receipt(conn, stream, record)
        if kind == uc.EPOCH_BEGIN:
            conn.execute(
                "INSERT INTO optimus_usage.coverage_epoch (epoch_id, stream_id, turn_id, begin_sequence, state) "
                "VALUES (%s, %s, %s, %s, 'open') ON CONFLICT (epoch_id) DO UPDATE SET begin_sequence = EXCLUDED.begin_sequence, updated_at = NOW()",
                (payload["epoch_id"], stream, payload["turn_id"], record.sequence),
            )
        elif kind == uc.EPOCH_CLOSE:
            self._project_close(conn, stream, record)
        elif kind == GAP_KIND:
            conn.execute(
                "UPDATE optimus_usage.coverage_epoch SET state = 'incomplete', reasons = array_append(reasons, %s), updated_at = NOW() "
                "WHERE stream_id = %s AND state = 'open'",
                (f"stream_gap:{payload['unconfirmed_from']}-{payload['unconfirmed_to']}", stream),
            )
        return 0

    def _project_receipt(self, conn: psycopg.Connection[Any], stream: str, record: Record) -> int:
        p = record.payload
        values = (p["attempt_id"], p["gateway_request_id"], p["epoch_id"], p["turn_id"], p["stage"], p["purpose"], p["outcome"],
                  p["reported_cost_usd"], p["facts_digest"], p["settled_digest"], p["late"], stream, record.sequence)
        inserted = conn.execute(
            "INSERT INTO optimus_usage.attempt_receipt (attempt_id, gateway_request_id, epoch_id, turn_id, stage, purpose, outcome, "
            "reported_cost_usd, facts_digest, settled_digest, late, stream_id, sequence) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING attempt_id",
            values,
        ).fetchone()
        if inserted is not None:
            return 0
        same_attempt = conn.execute(
            "SELECT facts_digest FROM optimus_usage.attempt_receipt WHERE attempt_id = %s", (p["attempt_id"],)
        ).fetchone()
        if same_attempt is not None:
            if same_attempt[0] == p["facts_digest"]:
                return 0  # an identical replay of the attempt: nothing new
            return self._conflict(conn, stream, record, p["attempt_id"], "attempt_facts_differ")
        owner = conn.execute(
            "SELECT attempt_id, settled_digest FROM optimus_usage.attempt_receipt WHERE gateway_request_id = %s", (p["gateway_request_id"],)
        ).fetchone()
        if owner is None:  # the insert conflicted on neither its attempt nor its Gateway request
            raise StoreError("order")
        if owner[1] == p["settled_digest"]:
            conn.execute(
                "INSERT INTO optimus_usage.receipt_alias (attempt_id, canonical_attempt_id, stream_id, sequence) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (attempt_id) DO NOTHING",
                (p["attempt_id"], owner[0], stream, record.sequence),
            )
            return 0
        return self._conflict(conn, stream, record, owner[0], "gateway_request_settled_differently")

    def _conflict(self, conn: psycopg.Connection[Any], stream: str, record: Record, existing: str, reason: str) -> int:
        conn.execute(
            "INSERT INTO optimus_usage.receipt_conflict (stream_id, sequence, attempt_id, existing_attempt_id, reason) VALUES (%s, %s, %s, %s, %s)",
            (stream, record.sequence, record.payload["attempt_id"], existing, reason),
        )
        return 1

    def _project_close(self, conn: psycopg.Connection[Any], stream: str, record: Record) -> None:
        p = record.payload
        reasons: list[str] = []
        epoch = conn.execute(
            "SELECT begin_sequence, state FROM optimus_usage.coverage_epoch WHERE epoch_id = %s", (p["epoch_id"],)
        ).fetchone()
        if epoch is None or epoch[0] is None:
            reasons.append("begin_missing")
        if not p["host_complete"]:
            reasons.append("host_incomplete")
        parts = conn.execute(
            "SELECT payload FROM optimus_usage.capture_event WHERE stream_id = %s AND kind = %s AND payload->>'epoch_id' = %s "
            "AND sequence < %s ORDER BY sequence DESC LIMIT %s",
            (stream, uc.EPOCH_IDENTITIES, p["epoch_id"], record.sequence, p["identity_parts"]),
        ).fetchall()
        settled: list[str] = []
        unknown: list[str] = []
        for (part,) in sorted(parts, key=lambda row: row[0]["part"]):
            settled += part["settled_attempt_ids"]
            unknown += part["unknown_attempt_ids"]
        if len(parts) != p["identity_parts"] or _identities_digest(p["epoch_id"], settled, unknown) != p["identities_digest"]:
            reasons.append("identity_parts_incomplete")
        if epoch is not None and epoch[0] is not None:
            gap = conn.execute(
                "SELECT 1 FROM optimus_usage.capture_event WHERE stream_id = %s AND kind = %s AND sequence > %s AND sequence < %s LIMIT 1",
                (stream, GAP_KIND, epoch[0], record.sequence),
            ).fetchone()
            if gap is not None:
                reasons.append("stream_gap")
            if epoch[1] == "incomplete":
                reasons.append("incomplete_before_close")
        conn.execute(
            "INSERT INTO optimus_usage.coverage_epoch (epoch_id, stream_id, turn_id, close_sequence, state, reasons) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (epoch_id) DO UPDATE SET close_sequence = EXCLUDED.close_sequence, "
            "state = EXCLUDED.state, reasons = optimus_usage.coverage_epoch.reasons || EXCLUDED.reasons, updated_at = NOW()",
            (p["epoch_id"], stream, p["turn_id"], record.sequence, "incomplete" if reasons else "complete", reasons),
        )


def _identities_digest(epoch_id: str, settled: list[str], unknown: list[str]) -> str:
    """The host's `capture_events.digest((epoch_id, settled, unknown))`, recomputed here without importing the host."""
    body = json.dumps(["capture-facts-v1", [epoch_id, settled, unknown]], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "hex:" + hashlib.sha256(body.encode("ascii")).hexdigest()


__all__ = ["GENESIS", "IngestResult", "StoreError", "UsageStore", "verify_migrations"]
