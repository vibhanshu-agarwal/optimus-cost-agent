-- evidence_handoff ledger schema v1
-- Descriptive, number-free migration for the risk-bearing vertical slice.

CREATE TABLE IF NOT EXISTS evidence_handoff_schema_migrations (
    filename TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION evidence_handoff_text_array_is_unique(arr TEXT[])
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT arr IS NOT NULL
       AND cardinality(arr) = (
           SELECT cardinality(ARRAY(SELECT DISTINCT unnest(arr)))
       );
$$;

CREATE TABLE IF NOT EXISTS evidence_handoff_ledger_instance (
    ledger_instance_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    genesis_sequence BIGINT NOT NULL DEFAULT 0 CHECK (genesis_sequence >= 0),
    genesis_content_sha256 TEXT NULL
);

CREATE TABLE IF NOT EXISTS evidence_handoff_counter (
    ledger_instance_id TEXT PRIMARY KEY REFERENCES evidence_handoff_ledger_instance (ledger_instance_id),
    last_committed BIGINT NOT NULL CHECK (last_committed >= 0),
    last_content_sha256 TEXT NULL
);

CREATE TABLE IF NOT EXISTS evidence_handoff_entries (
    sequence BIGINT NOT NULL UNIQUE CHECK (sequence > 0),
    ledger_instance_id TEXT NOT NULL REFERENCES evidence_handoff_ledger_instance (ledger_instance_id),
    entry_id TEXT NOT NULL UNIQUE,
    schema_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    context_id TEXT NOT NULL,
    task_id TEXT NULL,
    in_reply_to TEXT NULL,
    recipient_agent_ids TEXT[] NOT NULL,
    message_json JSONB NOT NULL,
    artifacts_json JSONB NOT NULL,
    principal_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    caller_role TEXT NOT NULL,
    authority TEXT NOT NULL,
    attestation JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL,
    idempotency_key TEXT NOT NULL,
    prev_content_sha256 TEXT NULL,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY (ledger_instance_id, sequence),
    UNIQUE (ledger_instance_id, principal_id, idempotency_key),
    CHECK (attestation IS NULL),
    CHECK (cardinality(recipient_agent_ids) > 0),
    CHECK (evidence_handoff_text_array_is_unique(recipient_agent_ids))
);

CREATE TABLE IF NOT EXISTS evidence_handoff_control_state (
    key TEXT PRIMARY KEY,
    value_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS evidence_handoff_capabilities (
    schema_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    writer_active BOOLEAN NOT NULL DEFAULT FALSE,
    reader_active BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS evidence_handoff_delivery_cursors (
    principal_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    ledger_instance_id TEXT NOT NULL REFERENCES evidence_handoff_ledger_instance (ledger_instance_id),
    confirmed_sequence BIGINT NOT NULL DEFAULT 0 CHECK (confirmed_sequence >= 0),
    chain_head_sha256 TEXT NULL,
    PRIMARY KEY (principal_id, agent_id, ledger_instance_id)
);

CREATE TABLE IF NOT EXISTS evidence_handoff_delivery_tokens (
    token_id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    ledger_instance_id TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS evidence_handoff_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    payload_json JSONB NOT NULL
);

INSERT INTO evidence_handoff_capabilities (schema_id, kind, writer_active, reader_active)
VALUES
    ('question.v1', 'question', FALSE, FALSE),
    ('answer.v1', 'answer', FALSE, FALSE),
    ('evidence-notice.v1', 'evidence-notice', FALSE, FALSE),
    ('review-ruling.v1', 'review-ruling', TRUE, TRUE),
    ('handoff.v1', 'handoff', FALSE, FALSE),
    ('acknowledgement.v1', 'acknowledgement', FALSE, FALSE)
ON CONFLICT (schema_id) DO NOTHING;
