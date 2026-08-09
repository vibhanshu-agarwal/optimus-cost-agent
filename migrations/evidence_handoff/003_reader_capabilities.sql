-- Per-principal reader capabilities and delivery-cursor advance timestamps (Task 9).
-- Schema-level evidence_handoff_capabilities remains writer/reader activation flags only.

CREATE TABLE IF NOT EXISTS evidence_handoff_reader_capabilities (
    principal_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    ledger_instance_id TEXT NOT NULL REFERENCES evidence_handoff_ledger_instance (ledger_instance_id),
    supported_schemas TEXT[] NOT NULL,
    reported_at TIMESTAMPTZ NOT NULL,
    retired BOOLEAN NOT NULL DEFAULT FALSE,
    last_authenticated_request_at TIMESTAMPTZ NULL,
    warning_delivered_incident_id TEXT NULL,
    PRIMARY KEY (principal_id, ledger_instance_id),
    CHECK (evidence_handoff_text_array_is_unique(supported_schemas))
);

ALTER TABLE evidence_handoff_delivery_cursors
    ADD COLUMN IF NOT EXISTS last_advanced_at TIMESTAMPTZ NULL;
