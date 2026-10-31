-- Plan 12.8: Optimus-owned durable usage capture (memory design v4 section 7; ADR-032).
-- Append-only facts are immutable in the database itself; only drain cursors and the rebuildable coverage
-- projection change. Changing this file requires a new migration file.

CREATE SCHEMA IF NOT EXISTS optimus_usage;

CREATE TABLE optimus_usage.ledger_instance (
    ledger_instance_id TEXT PRIMARY KEY CHECK (ledger_instance_id ~ '^[0-9a-f]{32}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Every verified outbox record, exactly as framed by its writer.
CREATE TABLE optimus_usage.capture_event (
    stream_id TEXT NOT NULL CHECK (stream_id ~ '^[0-9a-f]{32}$'),
    sequence BIGINT NOT NULL CHECK (sequence >= 1),
    event_id TEXT NOT NULL UNIQUE,
    writer TEXT NOT NULL CHECK (writer IN ('host', 'gateway')),
    kind TEXT NOT NULL,
    prev_digest TEXT NOT NULL,
    record_digest TEXT NOT NULL,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (stream_id, sequence)
);

-- Original receipt facts keyed by attempt identity; one charge per non-null Gateway request.
CREATE TABLE optimus_usage.attempt_receipt (
    attempt_id TEXT PRIMARY KEY,
    gateway_request_id TEXT UNIQUE,
    epoch_id TEXT,
    turn_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    purpose TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reported_cost_usd NUMERIC CHECK (reported_cost_usd IS NULL OR reported_cost_usd >= 0),
    facts_digest TEXT NOT NULL,
    settled_digest TEXT NOT NULL,
    late BOOLEAN NOT NULL,
    stream_id TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    FOREIGN KEY (stream_id, sequence) REFERENCES optimus_usage.capture_event (stream_id, sequence)
);

-- An identical replay of a settled Gateway request under another host attempt alias: linked, never charged.
CREATE TABLE optimus_usage.receipt_alias (
    attempt_id TEXT PRIMARY KEY,
    canonical_attempt_id TEXT NOT NULL REFERENCES optimus_usage.attempt_receipt (attempt_id),
    stream_id TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    FOREIGN KEY (stream_id, sequence) REFERENCES optimus_usage.capture_event (stream_id, sequence)
);

-- A contradictory duplicate: durable integrity evidence; the original stays and nothing is charged twice.
CREATE TABLE optimus_usage.receipt_conflict (
    stream_id TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    attempt_id TEXT NOT NULL,
    existing_attempt_id TEXT NOT NULL REFERENCES optimus_usage.attempt_receipt (attempt_id),
    reason TEXT NOT NULL CHECK (reason IN ('attempt_facts_differ', 'gateway_request_settled_differently')),
    PRIMARY KEY (stream_id, sequence),
    FOREIGN KEY (stream_id, sequence) REFERENCES optimus_usage.capture_event (stream_id, sequence)
);

-- Later, independent evidence linked to an original attempt; it never rewrites the receipt.
CREATE TABLE optimus_usage.reconciliation_evidence (
    evidence_id BIGSERIAL PRIMARY KEY,
    attempt_id TEXT NOT NULL,
    source TEXT NOT NULL,
    stream_id TEXT,
    sequence BIGINT,
    observed JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (stream_id, sequence) REFERENCES optimus_usage.capture_event (stream_id, sequence)
);

-- Rebuildable projection of coverage epochs from capture_event.
CREATE TABLE optimus_usage.coverage_epoch (
    epoch_id TEXT PRIMARY KEY,
    stream_id TEXT NOT NULL,
    turn_id TEXT,
    begin_sequence BIGINT,
    close_sequence BIGINT,
    state TEXT NOT NULL CHECK (state IN ('open', 'complete', 'incomplete')),
    reasons TEXT[] NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- The committed contiguous prefix of each stream, bound to this ledger instance.
CREATE TABLE optimus_usage.drain_cursor (
    ledger_instance_id TEXT NOT NULL REFERENCES optimus_usage.ledger_instance (ledger_instance_id),
    stream_id TEXT NOT NULL,
    writer TEXT NOT NULL CHECK (writer IN ('host', 'gateway')),
    sequence BIGINT NOT NULL CHECK (sequence >= 1),
    record_digest TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ledger_instance_id, stream_id)
);

CREATE FUNCTION optimus_usage.refuse_change() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'optimus_usage.% rows are immutable', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE TRIGGER capture_event_immutable BEFORE UPDATE OR DELETE ON optimus_usage.capture_event
    FOR EACH ROW EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER attempt_receipt_immutable BEFORE UPDATE OR DELETE ON optimus_usage.attempt_receipt
    FOR EACH ROW EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER receipt_alias_immutable BEFORE UPDATE OR DELETE ON optimus_usage.receipt_alias
    FOR EACH ROW EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER receipt_conflict_immutable BEFORE UPDATE OR DELETE ON optimus_usage.receipt_conflict
    FOR EACH ROW EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER reconciliation_evidence_immutable BEFORE UPDATE OR DELETE ON optimus_usage.reconciliation_evidence
    FOR EACH ROW EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER ledger_instance_immutable BEFORE UPDATE OR DELETE ON optimus_usage.ledger_instance
    FOR EACH ROW EXECUTE FUNCTION optimus_usage.refuse_change();

-- Row triggers do not fire on TRUNCATE.
CREATE TRIGGER capture_event_no_truncate BEFORE TRUNCATE ON optimus_usage.capture_event
    FOR EACH STATEMENT EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER attempt_receipt_no_truncate BEFORE TRUNCATE ON optimus_usage.attempt_receipt
    FOR EACH STATEMENT EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER receipt_alias_no_truncate BEFORE TRUNCATE ON optimus_usage.receipt_alias
    FOR EACH STATEMENT EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER receipt_conflict_no_truncate BEFORE TRUNCATE ON optimus_usage.receipt_conflict
    FOR EACH STATEMENT EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER reconciliation_evidence_no_truncate BEFORE TRUNCATE ON optimus_usage.reconciliation_evidence
    FOR EACH STATEMENT EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER ledger_instance_no_truncate BEFORE TRUNCATE ON optimus_usage.ledger_instance
    FOR EACH STATEMENT EXECUTE FUNCTION optimus_usage.refuse_change();
