# Sealed Reviewer Findings — A2A Ledger (preserved record)

Preserved from gitignored `.superpowers/sdd/a2a-audit-SEALED-reviewer-findings.md` on 2026-08-12.
Audited commit `e5f7e339`. Author: Claude (reviewer of the original slice). Reviewer: n/a — sealed baseline.

**Current authority:** historical. This was sealed before the independent audit and opened
only after that audit's findings were complete, to produce the differential. It is **not**
authoritative where it conflicts with the independent audit.

The region between the PRESERVED-BODY markers below is byte-identical to the source and
must not be edited. Any later material (for example a custody manifest) goes **outside** it.

<!-- PRESERVED-BODY-START -->
# SEALED — reviewer's known findings, A2A ledger risk-bearing slice

**DO NOT OPEN until you have written your own independent findings list to
`.superpowers/sdd/a2a-audit-independent-findings.md` and it is complete.**

Reading this first destroys the only thing that makes this audit worth running. Your list exists to
be compared against this one — including the things this list gets wrong, or missed entirely.

Author: Claude, the reviewer of that slice. That is exactly why Claude cannot be its auditor: the
list below is the output of the judgement under examination.

---

## Defects found DURING the slice (all fixed unless noted)

1. **Strict single-value protocol-version match** — the service admitted only `2025-11-25` and
   rejected other versions *before* auth. Widened.
2. **Doubled header rejected** — one client sends `MCP-Protocol-Version` twice; RFC 9110 joins them
   to `"2025-11-25, 2025-11-25"`, failing an exact-match test. Fixed by parsing the comma list.
3. **Session bound to a default, not the negotiated version** — spec-correct clients omit the header
   on `initialize`; the service defaulted the session, then 401'd the client's correctly-versioned
   follow-up.
4. **Integrity latch inert in the shipped configuration — FAIL-OPEN.** `global_integrity_fact()` and
   `_refuse_if_integrity_latched()` both short-circuited on `control_root is None`, which is exactly
   how the service builds its store. A latched, provably tampered ledger kept serving as healthy.
   Fixed by reading the latch from the DB mirror.
5. **Latch skipped when the scan is skipped — FAIL-OPEN, RECORDED, STILL OPEN.** `read_entries` has
   no latch check of its own; it inherits one only from `verify_unfiltered_range`, never called when
   `start > watermark`. A caught-up reader gets a clean empty page **and a delivery token** over a
   broken chain.
6. **Integrity mirror swallowed failures — FAIL-OPEN, found by CI AFTER the DoD passed.**
   `_persist_latch` did `try: mirror(incident) except Exception: pass` and duck-checked the method's
   presence. After fix 4 the DB mirror was the service's only latch source in production.

**Four of six were fail-open security controls**, each because the guard hung off something
incidental — an optional argument, a duck-typed probe, a skipped scan, a swallowed exception —
rather than sitting at the operation it protects.

## Open issues recorded but not fixed

- Read-path integrity verification covers only the **unread** range. A tamper behind all confirmed
  cursors has no detector, and clients cannot force a re-scan (a client-supplied cursor is
  overridden by the stored confirmed cursor).
- **No server-side MCP `clientInfo` capture.** "A native client made this call" is asserted and
  corroborated by DB side effects, never cryptographically proven.
- Option B leaves the session's bound protocol version **decorative** in production.

## Process failures worth auditing as first-class findings

- **The DoD passed while a fail-open was live**, and its "Windows repository/coverage gates" never
  included four **CI-only** checks: `bandit`, `pre-commit optimus-ast-grep`,
  `optimus.guardrails.prompt_injection`, `detect-secrets`. 22 commits had never been pushed, so CI
  had never run against them once; a `bandit` B110 had been latent since those lines were written.
- The reviewer compounded it by reading `$?` **after a pipe** and reporting bandit as passing when
  it exited 1.
- **The service has never been provisioned from scratch by following its own runbook.** Every live
  run was built incrementally across sessions with fixes applied in flight.

## Known-stale documentation (verify, do not trust)

The `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER` row in the product pool is wrong on at least three
independently checkable facts. Ground truth: final tip `658042d`, **25** commits from `8735885`,
and PR #128 was opened **and merged** (`7b5865f`), followed by PR #129 (`74f7104`).

## The expectation gap

The operator expected the delivered feature to serve as an agent-to-agent communication channel.
The slice specified a ledger plus a one-shot three-agent capstone, then deliberate teardown. Whether
that gap is a scoping failure, a communication failure, or neither is a legitimate audit question —
and it is the question that triggered this audit.

<!-- PRESERVED-BODY-END -->
