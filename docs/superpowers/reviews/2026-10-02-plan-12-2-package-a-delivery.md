# Plan 12.2 Package A local delivery record

Recorded 2026-10-02 (Asia/Calcutta), Codex architect/reviewer; Claude implementer.
This is evidence/status at the named source pin, not a second live work pool. The sole backlog
owns current status. Claude reviews this docs draft before its authorized docs commit/push/PR.

| Local commit | Delivery |
|---|---|
| `116d3c6ad24805eb78401a25929ed2063d7854b7` | Ignore only gitignored reviewer checkpoints in docs-index test |
| `13410c8d6335789a6665b67e73f483d796d8db5b` | Real directive producer controls, cancellation/effects at commit |
| `780faed6c69ba12c6d7a87bdac5ff68bdccf73a0` | Floor warning/meter/notices and numeric model-history order |
| `38a465fda38c73712162ab2b144c1d8da3cceeeb` | Deterministic lock-failure controls, no lock production change |

Base is merged docs `1f7b6a2dafc62d90696aee8ed2a15ff9ad66fce4` (PR #214), after ADR merge
`83fafb9606fb81992508554aa302d3b62c603236` (PR #213). Package A intake/env followed that merge;
the old docs-first/start/local-commit holds were satisfied/superseded, not erased from frozen plans.
Branch `agent/claude/plan12-context-engine-package-a` was clean at the reviewed head above.

## Result and limits

Task 2 records real WRITE/TEST effects and suppresses not-yet-started approved operations on cancel.
A completed WRITE plus cancelled TEST is PARTIAL; an already-started operation is not promised
to be interrupted or rolled back. Task 3 preserves the inclusive 524288-byte canonical floor and
80% arithmetic, makes warning/meter/separated notices visible, and fixes model-facing numeric
turn/declared-field ordering without changing canonical storage bytes.

All applicable hooks passed on each of the four code/test commits, with no skip. Passing hook
output suppresses pytest counts. Focused/offline evidence and Fable/independent Codex reviews
support the recorded delivery. Marked live/keyring/Redis/Gateway/Zed tiers are not promoted to PASS.
The later docs commit follows [ADR-016](../../decisions/ADR-016-checkpoint-review-cadence.md): skip only the full-suite hook
after focused docs checks, disclose it, and leave required CI to run its configured suite.

Terminal full-hook coverage at `38a465f`: aggregate 87.5846994535519%, launch approvals exactly
86.79245283018868%. Two unchanged modules below Task 2: server 90.57377049180327% ->
90.1639344262295% (574-575); client_sdk 78.38709677419355% -> 77.74193548387096% (326/338).
The numeric non-regression result is **NOT MET with operator-accepted residual**, solely for
these four statements at that head, per [ADR-017](../../decisions/ADR-017-package-a-coverage-exception.md). Task 3 offline
technical acceptance is recorded; neither production defects nor general safety-policy waiver
is inferred. All 135 modules were independently compared unrounded against matching source.

This PR includes a **runtime-hardening repair** under Plan 12's accepted ADR-013 first-step scope.
The sandbox still has the previously reported producer/effect gap until a separately authorized
synchronization. No sandbox code/settings/services were changed or re-certified by this package.
Archived Plan 11.25 and its [correction note](2026-10-01-plan-11-25-effect-instrumentation-correction.md)
retain historical bytes; this record supplies the later branch implementation evidence.

## Evidence custody

Raw evidence remains external under `optimus-handoff\sandbox-review-kit\evidence\plan12-pkg-a-20261001\`.
Task 2 commit isolation/coverage: `task2\commits\`; Task 3 terminal: `task3\commit\`;
lock controls/terminal: `task3\lockfix\`. Earlier failed attempts/collection checks remain failed.
No coverage datasets were combined or rerun until favorable.

| Artifact | SHA-256 |
|---|---|
| Lock-test commit log | `42C5C0DCD1814BC9683E7580A28EB2DD15D3E0F04672AD9DA79F412EE4D77C79` |
| Lock-test hook log | `D0CD32046A0554377D4923E4A9AFF6F31A4CD927F21115751F0DE2F9B3DE4AF8` |
| Terminal coverage | `3D15F4C5DB066DF91BC1CC944331A4B4F6CCE2C8D55342A3954FC5C55035696F` |
| Transcript S3 | `9B89272060555D1542B14F25C37807F21C5763222D0A93CF2C1ECC791D642A66` |

Reviewer acceptance/direct-authority proof is in the Codex workspace
`outputs\task3-acceptance\`; raw output custody is external, not a repository dependency.
Open observations and next gates are recorded only in the sole backlog under their existing owners.
