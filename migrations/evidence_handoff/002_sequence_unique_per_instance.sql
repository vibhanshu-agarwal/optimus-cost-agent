-- Scope sequence uniqueness per ledger instance.
-- Table-wide UNIQUE(sequence) conflicts with linked recovery: a replacement continues at
-- anchor.sequence + 1 while the quarantined predecessor retains untrusted tail rows at that
-- sequence. PRIMARY KEY (ledger_instance_id, sequence) already enforces per-instance uniqueness.

ALTER TABLE evidence_handoff_entries
    DROP CONSTRAINT IF EXISTS evidence_handoff_entries_sequence_key;
