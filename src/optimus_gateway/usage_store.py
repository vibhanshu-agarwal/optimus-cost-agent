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
from collections.abc import Mapping
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


# A lost connection, an expired lock wait or a cancelled statement: retryable, never acknowledged.
_UNAVAILABLE = (psycopg.OperationalError, psycopg.errors.LockNotAvailable, psycopg.errors.QueryCanceled)


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

    def __init__(self, conninfo: str, *, connect_timeout: int = 5, lock_timeout_ms: int = 5000, statement_timeout_ms: int = 30000) -> None:
        self._conninfo = conninfo
        self._connect_timeout = connect_timeout
        self.lock_timeout_ms = lock_timeout_ms  # agent-selected
        self.statement_timeout_ms = statement_timeout_ms  # agent-selected
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
                self._bound(conn)
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
        except _UNAVAILABLE:
            raise StoreError("unavailable") from None
        self.ledger_instance = instance
        return instance

    def ingest(self, batch: uc.CaptureBatch) -> IngestResult:
        """Commit one batch atomically and acknowledge exactly what was committed."""
        instance = self.ledger_instance or self.migrate()
        try:
            with self._connect() as conn:
                self._bound(conn)
                result = self._ingest(conn, instance, batch)
                conn.commit()
                return result
        except _UNAVAILABLE:
            raise StoreError("unavailable") from None

    def _bound(self, conn: psycopg.Connection[Any]) -> None:
        """Bound this transaction's lock waits and statements; expiry rolls it back and is retryable, never acknowledged."""
        conn.execute(f"SET LOCAL lock_timeout = '{int(self.lock_timeout_ms)}ms'")
        conn.execute(f"SET LOCAL statement_timeout = '{int(self.statement_timeout_ms)}ms'")

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
            conflicts = self._project_receipt(conn, stream, record)
            self._certify(conn, payload["epoch_id"])  # a late or conflicting receipt downgrades a certified epoch
            return conflicts
        if kind == uc.INTEGRITY_FAILURE:
            if payload["epoch_id"]:
                self._certify(conn, payload["epoch_id"])  # also after the close: a certified epoch is downgraded
            return 0
        if kind in {uc.GATEWAY_ATTEMPT_INTENT, uc.GATEWAY_ATTEMPT_OUTCOME}:
            host_request_id = payload.get("host_request_id") if kind == uc.GATEWAY_ATTEMPT_INTENT else self._host_request_of(conn, payload)
            self._recertify_for(conn, [host_request_id] if host_request_id else [])
            return 0
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

    def _host_request_of(self, conn: psycopg.Connection[Any], outcome: Mapping[str, Any]) -> str | None:
        row = conn.execute(
            "SELECT payload->>'host_request_id' FROM optimus_usage.capture_event WHERE writer = 'gateway' AND kind = %s "
            "AND payload->>'gateway_request_id' = %s AND (payload->>'attempt')::int = %s LIMIT 1",
            (uc.GATEWAY_ATTEMPT_INTENT, outcome["gateway_request_id"], outcome["attempt"]),
        ).fetchone()
        return row[0] if row else None

    def _project_receipt(self, conn: psycopg.Connection[Any], stream: str, record: Record) -> int:
        """One identity namespace: an attempt ID is either one canonical receipt or one alias of one, never both, and a
        Gateway request settles at most one canonical receipt. Projections of the same attempt or request from any stream
        are serialized by transaction-scoped advisory locks on both keys, taken in a fixed order."""
        p = record.payload
        keys = sorted({f"attempt:{p['attempt_id']}"} | ({f"request:{p['gateway_request_id']}"} if p["gateway_request_id"] else set()))
        for key in keys:
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 1))", (key,))
        aliased = conn.execute(
            "SELECT a.canonical_attempt_id, r.gateway_request_id, r.settled_digest FROM optimus_usage.receipt_alias a "
            "JOIN optimus_usage.attempt_receipt r ON r.attempt_id = a.canonical_attempt_id WHERE a.attempt_id = %s",
            (p["attempt_id"],),
        ).fetchone()
        if aliased is not None:
            if (aliased[1], aliased[2]) == (p["gateway_request_id"], p["settled_digest"]):
                return 0  # the alias replayed: nothing new
            return self._conflict(conn, stream, record, aliased[0], "attempt_facts_differ")
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
                "INSERT INTO optimus_usage.receipt_alias (attempt_id, canonical_attempt_id, stream_id, sequence) VALUES (%s, %s, %s, %s)",
                (p["attempt_id"], owner[0], stream, record.sequence),
            )  # no alias exists for it (checked above under the locks), so no mapping is silently ignored
            return 0
        return self._conflict(conn, stream, record, owner[0], "gateway_request_settled_differently")

    def _conflict(self, conn: psycopg.Connection[Any], stream: str, record: Record, existing: str, reason: str) -> int:
        conn.execute(
            "INSERT INTO optimus_usage.receipt_conflict (stream_id, sequence, attempt_id, existing_attempt_id, reason) VALUES (%s, %s, %s, %s, %s)",
            (stream, record.sequence, record.payload["attempt_id"], existing, reason),
        )
        owner = conn.execute("SELECT epoch_id FROM optimus_usage.attempt_receipt WHERE attempt_id = %s", (existing,)).fetchone()
        if owner is not None and owner[0]:
            self._certify(conn, owner[0])  # the original's epoch is downgraded too, whichever stream it came from
        return 1

    def _project_close(self, conn: psycopg.Connection[Any], stream: str, record: Record) -> None:
        p = record.payload
        conn.execute(
            "INSERT INTO optimus_usage.coverage_epoch (epoch_id, stream_id, turn_id, close_sequence, state) VALUES (%s, %s, %s, %s, 'open') "
            "ON CONFLICT (epoch_id) DO UPDATE SET close_sequence = EXCLUDED.close_sequence, updated_at = NOW()",
            (p["epoch_id"], stream, p["turn_id"], record.sequence),
        )
        self._certify(conn, p["epoch_id"])

    def _certify(self, conn: psycopg.Connection[Any], epoch_id: str) -> None:
        """Recompute one epoch's coverage from persisted evidence alone (Checkpoint B finding 1); never from the host's flag
        by itself. Complete requires: a begin and a written close with `host_complete` and no pending invocation; every
        invocation that opened, ended; the close's identity parts bound by its digest; no stream gap inside the epoch; every
        persisted intent answered by a persisted receipt or alias; the settled identities equal to the persisted receipts,
        none of them in conflict and no late receipt; and, for every intent, Gateway physical attempts each with an outcome,
        a confirmed intent and no uncertain outcome. Anything missing keeps it incomplete with its reasons; evidence that
        arrives later re-certifies it. Serialized per epoch from before the first evidence read (a transaction-scoped
        lock; READ COMMITTED reads after it see every certification committed before it), so a stale evaluation never
        overwrites a newer downgrade."""
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 2))", (f"epoch:{epoch_id}",))
        row = conn.execute(
            "SELECT stream_id, begin_sequence, close_sequence FROM optimus_usage.coverage_epoch WHERE epoch_id = %s", (epoch_id,)
        ).fetchone()
        if row is None or row[2] is None:
            return  # not closed: it stays open
        stream, begin, close_seq = row
        reasons: list[str] = []
        close = self._event(conn, stream, close_seq)
        if begin is None:
            reasons.append("begin_missing")
        if not close["host_complete"]:
            reasons.append("host_incomplete")
        if close["pending_invocations"]:
            reasons.append("pending_invocations")
        opened = self._count(conn, stream, uc.INVOCATION_OPEN, epoch_id)
        if opened != self._count(conn, stream, uc.INVOCATION_END, epoch_id):
            reasons.append("invocation_not_ended")
        if self._count(conn, stream, uc.INTEGRITY_FAILURE, epoch_id):
            reasons.append("integrity_failure")
        settled, unknown, parts = self._identities(conn, stream, epoch_id, close_seq, close["identity_parts"])
        if parts != close["identity_parts"] or _identities_digest(epoch_id, settled, unknown) != close["identities_digest"]:
            reasons.append("identity_parts_incomplete")
        if begin is not None and conn.execute(
            "SELECT 1 FROM optimus_usage.capture_event WHERE stream_id = %s AND kind = %s AND sequence > %s AND sequence < %s LIMIT 1",
            (stream, GAP_KIND, begin, close_seq),
        ).fetchone():
            reasons.append("stream_gap")
        receipts = self._values(conn, stream, uc.ATTEMPT_RECEIPT, epoch_id, "attempt_id", late=False)
        if self._values(conn, stream, uc.ATTEMPT_RECEIPT, epoch_id, "attempt_id", late=True):
            reasons.append("late_receipt")
        if sorted(receipts) != sorted(settled):
            reasons.append("settled_identities_differ")
        persisted = {
            r[0]
            for r in conn.execute(
                "SELECT attempt_id FROM optimus_usage.attempt_receipt WHERE attempt_id = ANY(%s) "
                "UNION SELECT attempt_id FROM optimus_usage.receipt_alias WHERE attempt_id = ANY(%s)",
                (receipts, receipts),
            ).fetchall()
        }
        if set(receipts) - persisted:
            reasons.append("receipt_not_persisted")
        if receipts and conn.execute(
            "SELECT 1 FROM optimus_usage.receipt_conflict WHERE attempt_id = ANY(%s) OR existing_attempt_id = ANY(%s) LIMIT 1",
            (receipts, receipts),
        ).fetchone():
            reasons.append("receipt_conflict")
        intents = self._values(conn, stream, uc.ATTEMPT_INTENT, epoch_id, "host_request_id")
        if any(not any(r == h or r.startswith(h + ":") for r in receipts) for h in intents):
            reasons.append("intent_without_receipt")
        if any(not any(r == h or r.startswith(h + ":") for h in intents) for r in receipts):
            reasons.append("receipt_without_intent")
        answered = {
            gateway_request_id: outcome
            for gateway_request_id, outcome in conn.execute(
                "SELECT payload->>'gateway_request_id', payload->>'outcome' FROM optimus_usage.capture_event WHERE stream_id = %s "
                "AND kind = %s AND payload->>'epoch_id' = %s AND NOT (payload->>'late')::boolean",
                (stream, uc.ATTEMPT_RECEIPT, epoch_id),
            ).fetchall()
            if gateway_request_id
        }
        reasons += self._physical(conn, intents, answered)
        conn.execute(
            "UPDATE optimus_usage.coverage_epoch SET state = %s, reasons = %s, updated_at = NOW() WHERE epoch_id = %s",
            ("incomplete" if reasons else "complete", sorted(set(reasons)), epoch_id),
        )

    def _physical(self, conn: psycopg.Connection[Any], intents: list[str], answered: Mapping[str, str]) -> list[str]:
        """Gateway physical evidence for the epoch's host requests, joined to its receipts by Gateway request ID (`answered`:
        Gateway request ID -> the receipt's outcome). Each Gateway request's attempts must be numbered 1..n in one stream
        with no gap among their records, each with an outcome, a confirmed intent and nothing uncertain. A request that was
        sent needs a receipt; the receipt settles only the request's last attempt (a completed receipt needs a completed
        last attempt), so an earlier sent attempt with no recorded cost (a legacy retry after a 503) stays unresolved.
        Every receipt's Gateway request needs physical evidence."""
        reasons: list[str] = []
        seen: set[str] = set()
        for host_request_id in intents:
            requests: dict[str, list[tuple[str, int, int]]] = {}
            for gateway_request_id, number, stream, sequence in conn.execute(
                "SELECT payload->>'gateway_request_id', (payload->>'attempt')::int, stream_id, sequence FROM optimus_usage.capture_event "
                "WHERE writer = 'gateway' AND kind = %s AND payload->>'host_request_id' = %s ORDER BY 1, 2",
                (uc.GATEWAY_ATTEMPT_INTENT, host_request_id),
            ).fetchall():
                requests.setdefault(gateway_request_id, []).append((stream, number, sequence))
            if not requests:
                reasons.append("physical_evidence_missing")
            for gateway_request_id, attempts in requests.items():
                seen.add(gateway_request_id)
                streams = {stream for stream, _, _ in attempts}
                if [number for _, number, _ in attempts] != list(range(1, len(attempts) + 1)) or len(streams) != 1:
                    reasons.append("physical_attempt_missing")
                    continue
                (stream,) = streams
                outcomes: list[Mapping[str, Any]] = []
                last_sequence = attempts[-1][2]
                for _, number, _ in attempts:
                    outcome = conn.execute(
                        "SELECT payload, sequence FROM optimus_usage.capture_event WHERE stream_id = %s AND kind = %s "
                        "AND payload->>'gateway_request_id' = %s AND (payload->>'attempt')::int = %s LIMIT 1",
                        (stream, uc.GATEWAY_ATTEMPT_OUTCOME, gateway_request_id, number),
                    ).fetchone()
                    if outcome is None:
                        reasons.append("physical_outcome_missing")
                        continue
                    outcomes.append(outcome[0])
                    last_sequence = max(last_sequence, outcome[1])
                    if outcome[0].get("intent_confirmed") is not True:  # absent (an older writer) is never confirmed
                        reasons.append("physical_intent_unconfirmed")
                    if outcome[0]["outcome"] == "uncertain":
                        reasons.append("physical_attempt_uncertain")
                if conn.execute(
                    "SELECT 1 FROM optimus_usage.capture_event WHERE stream_id = %s AND kind = %s AND sequence > %s AND sequence < %s LIMIT 1",
                    (stream, GAP_KIND, attempts[0][2], last_sequence),
                ).fetchone():
                    reasons.append("physical_stream_gap")
                if len(outcomes) != len(attempts):
                    continue
                sent = [o for o in outcomes if o["outcome"] != "not_sent"]
                if gateway_request_id not in answered:
                    if sent:
                        reasons.append("physical_receipt_unmatched")
                    continue
                if answered[gateway_request_id] == "completed" and outcomes[-1]["outcome"] in {"failed", "not_sent"}:
                    reasons.append("physical_attempt_missing")
                if any(o["cost_usd"] is None for o in sent if o is not outcomes[-1]):
                    reasons.append("physical_cost_unresolved")
        if set(answered) - seen:
            reasons.append("receipt_without_physical")
        return reasons

    def _recertify_for(self, conn: psycopg.Connection[Any], host_request_ids: list[str]) -> None:
        """Re-certify closed epochs whose intents these Gateway records answer."""
        if not host_request_ids:
            return
        for (epoch_id,) in conn.execute(
            "SELECT DISTINCT payload->>'epoch_id' FROM optimus_usage.capture_event WHERE writer = 'host' AND kind = %s "
            "AND payload->>'host_request_id' = ANY(%s)",
            (uc.ATTEMPT_INTENT, host_request_ids),
        ).fetchall():
            self._certify(conn, epoch_id)

    def _event(self, conn: psycopg.Connection[Any], stream: str, sequence: int) -> dict[str, Any]:
        row = conn.execute(
            "SELECT payload FROM optimus_usage.capture_event WHERE stream_id = %s AND sequence = %s", (stream, sequence)
        ).fetchone()
        return dict(row[0]) if row else {}

    def _count(self, conn: psycopg.Connection[Any], stream: str, kind: str, epoch_id: str) -> int:
        row = conn.execute(
            "SELECT count(*) FROM optimus_usage.capture_event WHERE stream_id = %s AND kind = %s AND payload->>'epoch_id' = %s",
            (stream, kind, epoch_id),
        ).fetchone()
        return int(row[0]) if row else 0

    def _values(self, conn: psycopg.Connection[Any], stream: str, kind: str, epoch_id: str, field: str, *, late: bool | None = None) -> list[str]:
        if late is None:
            rows = conn.execute(
                "SELECT payload->>%s FROM optimus_usage.capture_event WHERE stream_id = %s AND kind = %s AND payload->>'epoch_id' = %s",
                (field, stream, kind, epoch_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT payload->>%s FROM optimus_usage.capture_event WHERE stream_id = %s AND kind = %s AND payload->>'epoch_id' = %s "
                "AND (payload->>'late')::boolean = %s",
                (field, stream, kind, epoch_id, late),
            ).fetchall()
        return [r[0] for r in rows]

    def _identities(self, conn: psycopg.Connection[Any], stream: str, epoch_id: str, close_seq: int, expected: int) -> tuple[list[str], list[str], int]:
        """The last full set of identity parts before the close (a re-close after a refused close repeats them)."""
        rows = conn.execute(
            "SELECT payload FROM optimus_usage.capture_event WHERE stream_id = %s AND kind = %s AND payload->>'epoch_id' = %s "
            "AND sequence < %s ORDER BY sequence DESC LIMIT %s",
            (stream, uc.EPOCH_IDENTITIES, epoch_id, close_seq, expected),
        ).fetchall()
        settled: list[str] = []
        unknown: list[str] = []
        for (part,) in sorted(rows, key=lambda r: r[0]["part"]):
            settled += part["settled_attempt_ids"]
            unknown += part["unknown_attempt_ids"]
        return settled, unknown, len(rows)


def _identities_digest(epoch_id: str, settled: list[str], unknown: list[str]) -> str:
    """The host's `capture_events.digest((epoch_id, settled, unknown))`, recomputed here without importing the host."""
    body = json.dumps(["capture-facts-v1", [epoch_id, settled, unknown]], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "hex:" + hashlib.sha256(body.encode("ascii")).hexdigest()


__all__ = ["GENESIS", "IngestResult", "StoreError", "UsageStore", "verify_migrations"]
