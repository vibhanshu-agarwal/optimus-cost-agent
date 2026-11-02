-- Plan 12.9: the cost-savings report's reads (ADR-034). Migration 001 is unchanged; changing this file requires a new
-- migration file.

-- Immutable price snapshots (the Gateway's registry and its dated reference prices), keyed by their content-derived ID:
-- the same content captured again is the same row, first capture kept.
CREATE TABLE optimus_usage.price_snapshot (
    snapshot_id TEXT PRIMARY KEY CHECK (snapshot_id ~ '^hex:[0-9a-f]{64}$'),
    kind TEXT NOT NULL CHECK (kind IN ('gateway.registry.snapshot', 'gateway.reference.snapshot')),
    body JSONB NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    stream_id TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    FOREIGN KEY (stream_id, sequence) REFERENCES optimus_usage.capture_event (stream_id, sequence)
);

CREATE TRIGGER price_snapshot_immutable BEFORE UPDATE OR DELETE ON optimus_usage.price_snapshot
    FOR EACH ROW EXECUTE FUNCTION optimus_usage.refuse_change();
CREATE TRIGGER price_snapshot_no_truncate BEFORE TRUNCATE ON optimus_usage.price_snapshot
    FOR EACH STATEMENT EXECUTE FUNCTION optimus_usage.refuse_change();

-- Report joins: one session's receipts, turn contexts and epoch begins; each receipt's event; conflict evidence by
-- either attempt.
CREATE INDEX capture_event_session ON optimus_usage.capture_event ((payload->>'session_id'), kind)
    WHERE kind IN ('attempt.receipt', 'turn.report_context', 'epoch.begin');
CREATE INDEX attempt_receipt_event ON optimus_usage.attempt_receipt (stream_id, sequence);
CREATE INDEX receipt_conflict_attempt ON optimus_usage.receipt_conflict (attempt_id);
CREATE INDEX receipt_conflict_existing ON optimus_usage.receipt_conflict (existing_attempt_id);
