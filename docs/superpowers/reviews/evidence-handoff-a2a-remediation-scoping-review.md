# Review Chronology — A2A Remediation Scoping (preserved record)

Preserved from gitignored `.superpowers/sdd/a2a-remediation-scoping-review.md` on 2026-08-12.
Audited commit `e5f7e339`. Author: Codex (reviewer). Reviewer: n/a — this is the review record.

**Latest disposition: Revision 3 APPROVED, 2026-08-12.** Earlier rounds in this file open
with CHANGES REQUIRED; those are historical and must not be read as the current ruling.

The region between the PRESERVED-BODY markers below is byte-identical to the source and
must not be edited. Any later material (for example a custody manifest) goes **outside** it.

<!-- PRESERVED-BODY-START -->
# Review — A2A Ledger Remediation Scoping Proposal

**Reviewer:** Codex  
**Date:** 2026-08-12  
**Artifact reviewed:** `.superpowers/sdd/a2a-remediation-scoping-proposal-DRAFT.md`  
**Source audit:** `.superpowers/sdd/a2a-audit-independent-findings.md`  
**Decision:** **CHANGES REQUIRED — do not approve the slice cut yet**

The five-slice direction is substantially better than one remediation plan, and the proposal has
the right endpoints: composition first as an integration substrate, evidence last, and the stale
pool correction outside implementation. The current draft nevertheless has a dependency cycle,
one finding that is only one-third housed despite the 17/17 label count, and a triage table that
downgrades several trust-blocking defects below the independent audit's ruling.

The five proposed feature IDs are unused outside the draft. The finding labels also appear exactly
once. That mechanical coverage check passes; semantic coverage does not yet pass because Medium 16
contains three independent obligations and the proposal assigns only one.

## Blocking review findings

### 1. [P0] Slice A is enabling for installed integration evidence, but its current Done condition depends on B and D

The claim that nothing else can be proven before A
(`a2a-remediation-scoping-proposal-DRAFT.md:22-28`) is too absolute. B, C, and D can and should prove
their component invariants with focused unit/integration tests while A is being built. What they
cannot prove without A is **clean-installed production composition**. That distinction matters
because the current wording needlessly serializes the program.

More seriously, A promises a migrated, authenticated, **ready** ledger
(`a2a-remediation-scoping-proposal-DRAFT.md:56-75`) while:

- B owns construction of the production `IntegrityMonitor` and full genesis/recovery-anchor
  readiness (`:77-90`); and
- D owns the least-privileged application credential (`:105-114`), even though creating that role is
  itself a lifecycle/provisioning action and the frozen design forbids a ready service running on
  the administrator credential.

As written, A can close only by doing part of B and D, or by declaring an admin-credentialed service
with incomplete integrity readiness “ready.” Neither is acceptable.

**Required correction:** define A as the **installed composition substrate**, not the trust gate.
Its acceptance must say explicitly that the feature remains default-off and untrusted until B–D
close. B/C/D may proceed in parallel once A's production interfaces are stable; each receives two
evidence levels:

1. focused component/integration proof, which does not depend on A; and
2. final clean-wheel composition proof, which does depend on A and must be rerun as each slice
   lands.

Do not use “nothing else can be proven.” Use “nothing else can receive clean-installed production
acceptance.” E remains the only cumulative trust/evidence closure.

### 2. [P0] High 9 is mis-homed; least-privileged role provisioning belongs in A

The lifecycle composition is responsible for creating/granting the application DB role and passing
only that credential to the service. A cannot own “provisions from nothing” while D separately owns
the database identity that provisioning must create. This is the same seam that caused the original
composition failure.

**Required correction:** move **High 9** from D to A. A should cover C1, C3, H7, H9, and M15. Its
installed walkthrough must prove the lifecycle/admin credential never enters the service process.

H8 and M14 can remain together as service-process launch/secret-boundary work. If the draft keeps
them in D, rename D from “Privilege” to a runtime/service security boundary; after H9 moves, the
current name is inaccurate.

### 3. [P0] Medium 16 is two-thirds homeless

The proposal assigns only the typed-status portion of M16 to B
(`a2a-remediation-scoping-proposal-DRAFT.md:79-85`). It does not assign:

- production construction and use of `AuditRecorder` across transport, authentication, session,
  delivery, and integrity paths; or
- the missing pre-parse rate and concurrency bounds.

This is why label-level 17/17 coverage is insufficient. E even calls for DB/audit extracts, but no
preceding slice owns production audit generation.

**Required correction:** split M16 explicitly in the coverage matrix without pretending it is one
atomic change:

- **M16c typed integrity state** → B;
- **M16a production audit recording** → a pre-E runtime boundary slice; and
- **M16b rate/concurrency controls** → that same runtime/transport boundary slice.

The cleanest five-slice repair is to move H9 to A and redefine D as **Runtime service security and
observability**, covering H8, M14, M16a, and M16b. If production audit wiring makes D too broad,
create a sixth slice; silently dropping two requirements is not an option.

### 4. [P1] H12 cannot wait until the last slice even though cumulative evidence must

E correctly belongs last for capstone regeneration, but the DoD/gate defect must not remain active
while A–D are planned and closed. Otherwise the remediation repeats the exact process failure under
review.

**Required correction:** split H12 temporally:

- before Slice A planning, establish one program-level gate inventory and checkbox rule that every
  slice must inherit; and
- in E, run/reconcile the cumulative clean-install, CI, live-tier, and documentation-freshness
  evidence and close the final DoD.

The early gate contract is process infrastructure, not evidence sign-off. E remains last.

### 5. [P1] C does not need a hard dependency on all of B

H4 has an integrity interaction, but its primary defect is recipient authorization/hidden
commitment disclosure. H5 and H6 are independent of the integrity implementation. Making all of C
depend on B (`a2a-remediation-scoping-proposal-DRAFT.md:92-103`) needlessly serializes redaction and
snapshot work.

**Required correction:** allow B and C to proceed in parallel after stable composition interfaces.
C must include one combined post-B regression proving direct reads and snapshot/token paths also
respect the latch, but that integration checkpoint is not a reason to block all C implementation on
B completion.

## Grouping rulings requested by the drafter

### Critical 3 inside A — approved

C3 is a start-sequence defect: the exposed lifecycle path creates the durable instance fact that
then forbids first minting. It cannot be repaired or proven independently of the composition order.
Keeping it in A is correct.

### High 13 inside B — approved, and it is trust-blocking

H13 is not merely adjacent recovery work. B's defining contract is full verification from the
declared ordinary genesis **or recovery anchor**. A verifier that rejects its own valid linked
replacement is an integrity/readiness defect, so H13 belongs in B. Do not downgrade it because
recovery is less frequent than ordinary reads.

### Medium 15 inside A — approved

Cross-process status and malformed instance-file handling are lifecycle/bootstrap behavior. The
metadata-corruption branch must produce a fail-closed/reconciliation result that B can classify, but
A should own the read/reconcile/overwrite decision. Keeping the whole finding in A avoids a second
owner for the same control file.

### High 4/5/6 inside C — approved

They share the policy/store request seam and a real service/store integration harness. The grouping
is coherent. The dependency wording, not the grouping, needs revision.

### High 8 / Medium 14 inside D — approved with rename

Both govern whether the service process may launch when authentication/secret preconditions are
not safely established. They fit a runtime service boundary. Add the non-integrity parts of M16 or
create a sixth slice, as ruled above.

### Medium 17 outside implementation slices — approved

The pool correction is a separate, small documentation mutation and should precede Slice A. It must
not edit any frozen/digest-pinned artifact. Correcting the row also needs to reconcile the existing
design-refresh, credential-lifecycle, at-rest-integrity, and peer-liveness ownership statements—not
just the three Git facts.

## Corrected triage ruling

Section 5 is not acceptable as written. In particular, “no known live trigger” is not a basis to
downgrade High findings: concurrent append is normal A2A behavior for H6, and linked replacement is
a required recovery path for H13.

If the operator chooses to ship/trust this slice, use the following triage:

| Class | Findings | Ruling |
|---|---|---|
| **Must fix before any trust** | C1, C2, C3, H4, H5, H6, H7, H8, H9, H13, M14, M15, M16b, M16c | These are production composition, confidentiality/redaction, consistency, integrity, privilege/secret, lifecycle, or required transport controls. |
| **Must exist before an evidence claim** | M16a, H10, H11, H12 | Production audit data must exist before E can cite it; the evidence/verifier/DoD defects then require regeneration, not reinterpretation. |
| **Immediate documentation correction** | M17 | The current-state source is materially false. |

There is no justified “Should fix” bucket for H6 or H13. M14 and M15 also cannot sit in “Accept or
schedule”: A's own walkthrough requires truthful status, malformed instance state must fail closed,
and a service must not run after failing to protect/delete a signing-key bundle.

M16 may be accepted only through an explicit approved design amendment that changes the frozen
security/observability requirements and states the residual risk. A triage table by itself cannot
silently waive the frozen design.

The proposal's alternative—declare the feature explicitly **not shipped**, correct M17, and defer
A–E—is defensible. What is not defensible is calling the feature trusted while deferring any item in
the first two rows above.

## Non-goal review

Section 4 is directionally correct, with four required clarifications.

1. **Wakeup, real-time relay, peer-liveness synthesis, verified process identity,
   non-repudiation, and malicious-same-user resistance remain out of this remediation.** Their
   absence is not a defect in the frozen risk slice.
2. **The other five entry kinds are not frozen-design non-goals.** They are deferred protocol
   completion. Say “out of scope for this remediation and retained under existing roadmap custody,”
   not “do not remediate.”
3. **The malicious-same-user non-goal does not excuse M14.** Restrictive permissions and deletion of
   the signing-key/DB bundle are explicit shipped controls against ordinary exposure and must still
   fail closed.
4. **Do not let E reintroduce the identity overclaim.** A server-signed receipt can bind an
   authenticated principal credential to a server-observed operation; it cannot prove which native
   executable held that credential. Raw native-client transcripts are corroboration. E must use a
   claim-to-evidence table with those exact strengths. “Bind client to request” is too ambiguous.

There is also one external dependency the draft must state: the pool records that stock Cursor tool
discovery currently fails because OAuth discovery is gated and 401 lacks `WWW-Authenticate`
(`evidence-handoff-open-work-pool.md:112`). If E intends to re-certify a normal native Cursor path,
it depends on the relevant interoperability subset of
`EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE`; otherwise E must narrow its claim and must not use a
probe/workaround as proof that stock Cursor integration works.

Finally, list the adjacent open custody that these slices do **not** silently close:

- Docker-versus-wslc and session Option A remain with the A2A design refresh;
- behind-confirmed-cursor/periodic historical verification remains with at-rest integrity unless B
  explicitly absorbs it and the pool owner is updated;
- OAuth/rotation and native-client discovery remain with credential lifecycle; and
- peer-liveness remains independently owned.

B overlaps the design-refresh operation-entry item and may overlap the at-rest full-audit item. The
approved scoping must say whether those rows are partially superseded, fully absorbed, or still
open. One requirement cannot have ambiguous dual custody.

## Required revision checklist

- [ ] Recast A as an installed, default-off integration substrate; reserve cumulative trust closure
  for E.
- [ ] Replace absolute serial sequencing with component proof plus clean-composition acceptance.
- [ ] Move H9 to A and prove the service never receives the admin credential.
- [ ] Fully home M16a/M16b/M16c; rename D or add a sixth slice.
- [ ] Establish the H12 gate contract before A; retain final cumulative execution in E.
- [ ] Allow B/C/D parallel implementation with explicit combined integration checkpoints.
- [ ] Upgrade H6, H13, M14, M15, and the applicable M16 parts per the corrected triage.
- [ ] Clarify that the five other entry kinds are deferred, not permanent design non-goals.
- [ ] Add the Cursor/credential-lifecycle dependency or narrow E's native-client claim.
- [ ] Reconcile overlap with the design-refresh and at-rest-integrity custody rows.
- [ ] Preserve M17 as an immediate, separately approved documentation correction.

## Final ruling

**Revise and return the scoping proposal; do not draft per-slice designs yet.** C3→A and H13→B are
correct. The decisive changes are to break A's hidden dependency cycle, move H9 into lifecycle
composition, fully place M16, move the DoD contract ahead of all implementation, and restore the
audit's trust-blocking severity for H6/H13/M14/M15/M16.

---

## Revision 2 re-review — 2026-08-12

**Artifact state reviewed:** `A2A Ledger Remediation — Scoping Proposal (REVISION 2)`  
**Decision:** **CHANGES REQUIRED — three narrow scoping corrections remain**

Revision 2 substantively resolves all eleven items in the first review. It corrects the original
dependency cycle, moves H9 to lifecycle provisioning, expands the coverage model from 17 labels to
20 obligations, fully places M16, splits H12 temporally, restores the audit's triage, corrects the
scope fence, and records adjacent custody. The first review's broad objections are closed.

The proposal should receive one more scoping revision before per-slice designs. The remaining
issues are not implementation details: they decide the actual slice boundary and whether A can
close without violating B's safety contract.

### R2-1 [P0] Slice A's Done condition still permits traffic before B supplies readiness

Section 3 correctly says A is default-off/untrusted and does not claim integrity readiness
(`a2a-remediation-scoping-proposal-DRAFT.md:83-88`). Its Done condition nevertheless says the
installed walkthrough reaches a “migrated, authenticated, running ledger.” A real running MCP
ledger normally accepts tool traffic. The frozen design requires full anchor-to-head verification
before accepting traffic, and B—not A—owns that verification.

This is the last hidden B dependency. A is not dependency-clean if it closes by starting a service
that serves ledger operations without B; it is also not dependency-clean if “running” quietly
requires B's monitor.

**Required correction:** A must deliver a fail-closed readiness seam whose pre-B/default result is
not-ready. Its clean-wheel walkthrough may prove:

- installation, migrations, metadata, key custody, enrollments/credential issuance;
- creation and exclusive use of the application DB role;
- service-process start/stop and truthful cross-process lifecycle status;
- authentication rejection/identity binding at the perimeter; and
- authenticated ledger tool traffic is refused with a stable not-ready outcome until B installs a
  successful readiness provider/verdict.

Replace “running ledger” with “running service process held non-ready for ledger operations.” A
must also state that its composition path never selects the H8 unauthenticated stub; the separately
callable public-stub defect remains owned by D. With those two sentences, A is genuinely free of B
and D while remaining a usable installed substrate.

### R2-2 [P0] Decide the sixth audit-wiring slice now

Do **not** defer the M16a split to Slice D design. This document exists to prevent oversized plans;
asking the design to decide whether its own cross-cutting scope is too large repeats the ambiguity
the scoping stage is meant to remove.

M16a crosses transport, authentication, sessions, delivery, integrity, and final evidence
extraction. H8/M14/M16b instead form a coherent runtime launch and transport-protection slice. Their
change surfaces, failure modes, and evidence are different.

**Required correction:** mint the already proposed sixth ID now:

- **Slice D — Runtime service security and transport bounds:** H8, M14, M16b.
- **Slice E — Audit wiring and evidence observability:** M16a.
- **Slice F — Evidence and DoD closure:** H10, H11, H12b.

The audit-wiring slice can define its event/recorder contract in parallel, but its production
integration acceptance follows the stable B/C/D event surfaces and must precede final evidence
closure. Renumbering the current evidence slice to F keeps dependency order legible. Update the ID
table, slice list, sequencing text, coverage matrix, and “A-E” wording accordingly.

### R2-3 [P1] Section 7's at-rest boundary is directionally right but stated too categorically

**Operation-entry custody ruling: confirmed.** B should absorb the operation-entry guard requirement
currently recorded under `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH`. When B is scheduled, the
pool must remove that sub-item from DESIGN-REFRESH. DESIGN-REFRESH retains the design v2
restatement, Docker-versus-wslc correction, and session Option A item. There should be no dual owner.

**At-rest ruling: correct the wording.** B necessarily performs historical verification in two
forms required by the frozen risk slice:

1. full declared ordinary-genesis-or-recovery-anchor-to-head verification at startup/readiness;
2. an explicit operator-triggered full audit using the same verifier.

`EVIDENCE-HANDOFF-FEAT-AT-REST-INTEGRITY` should retain **post-readiness periodic/scheduled
historical re-verification**, including detection of tampering behind every confirmed cursor. That
is the distinct defense-in-depth gap discovered in the capstone.

Therefore, replace “B does NOT absorb [at-rest] historical verification” with this precise split:

- B owns startup/readiness and explicit on-demand full-chain verification, incident persistence,
  and operation-entry refusal;
- AT-REST-INTEGRITY owns periodic/scheduled re-verification after readiness and does not weaken or
  substitute for B's on-scan/readiness guards.

The current categorical wording is misleading because B's stated anchor-to-head readiness is
itself historical verification, and omitting the explicit operator-triggered audit would leave a
frozen first-slice requirement unremediated. Update the pool row when B is scheduled so the at-rest
owner is narrowed rather than duplicated.

## Revision 2 checklist disposition

| Prior requirement | R2 ruling |
|---|---|
| A installed/default-off substrate, final cumulative closure | Addressed, subject to R2-1 non-ready acceptance wording |
| Component proof vs clean-composition acceptance | Addressed |
| H9 moved to A | Addressed |
| M16a/b/c fully homed | Addressed mechanically; M16a now requires the R2-2 separate slice |
| H12 gate contract before A | Addressed |
| B/C/D parallel work plus integration checkpoints | Addressed; audit wiring gets its own post-B/C/D checkpoint |
| Audit triage restored | Addressed |
| Other five entry kinds labelled deferred | Addressed |
| Cursor/credential-lifecycle dependency | Addressed; cite the credential-lifecycle pool row precisely |
| Adjacent custody reconciled | Partially addressed; adopt the R2-3 on-demand versus periodic boundary |
| M17 immediate correction | Addressed |

The 20-obligation matrix is semantically complete; no audited obligation is missing. After R2-2,
M16a's owner changes from D to the dedicated audit-wiring slice, but the obligation count remains
20.

## Revision 2 final ruling

**Return for one narrow Revision 3; do not draft per-slice designs yet.** The three requested
answers are:

1. **Section 7:** B absorbs operation-entry guards. B also owns startup and operator-triggered
   full-chain audit; AT-REST-INTEGRITY retains periodic/scheduled post-readiness historical
   detection. Correct the current categorical “does not absorb” wording.
2. **Slice D:** decide the sixth slice now. M16a is independently schedulable cross-cutting audit
   work and should not be hidden behind a design-time split trigger.
3. **Slice A:** almost, but not yet dependency-free. Its Done condition must start a service process
   that remains fail-closed/not-ready for ledger operations until B lands, and must explicitly avoid
   D's public stub path.

---

## Revision 3 re-review — 2026-08-12

**Artifact state reviewed:** `A2A Ledger Remediation — Scoping Proposal (REVISION 3)`  
**Decision:** **APPROVED AS THE REMEDIATION SCOPING CONTRACT**

Revision 3 resolves all three remaining Revision 2 rulings. No blocking or non-blocking scoping
finding remains. Approval means the work is correctly partitioned and custodied; it does **not**
authorize implementation, amend a frozen design, or answer the operator's separate question of
whether the feature should be remediated rather than declared not shipped.

### R3-1 — Slice A is now genuinely independent of B and D: approved

Slice A now closes on a **running service process held non-ready for ledger operations**, not a
traffic-serving ledger. Its pre-B readiness verdict is explicitly NOT-READY, authenticated ledger
tools must return a stable not-ready outcome, and A never selects the H8 unauthenticated stub
(`a2a-remediation-scoping-proposal-DRAFT.md:98-117`).

That is the correct composition boundary:

- A proves the installed wheel, migrations, metadata, key-custody order, enrollment/issuance,
  application DB role, real service-process lifecycle, truthful cross-process status, and perimeter
  authentication/identity binding.
- B later supplies the successful integrity-readiness provider/verdict required before ledger
  operations accept traffic.
- D still owns eliminating the separately callable public stub and enforcing runtime
  secret/transport protections.

A therefore neither implements B/D work nor weakens their gates. Its Done condition is
dependency-clean.

### R3-2 — Six slices are the correct cut: approved

The split is now decided at scoping time:

- A — installed composition substrate;
- B — integrity boundary;
- C — data-path authorization and atomicity;
- D — runtime service security and transport bounds;
- E — audit wiring and evidence observability;
- F — evidence and DoD closure.

M16a is independently schedulable, cross-cutting work and correctly owns a dedicated Slice E.
H8/M14/M16b remain a coherent Slice D. E may define its audit contract in parallel, while its
production integration acceptance correctly follows stable B/C/D event surfaces and precedes F.
No seventh split is required at scoping time; individual designs must still remain within their
approved obligations.

The dependency order `Pre-A → A → {B, C, D} → E → F` is approved for clean-installed acceptance.
It does not prevent focused B/C/D component tests or E contract design from proceeding in parallel
where the proposal explicitly permits them.

### R3-3 — Adjacent integrity custody is precise and non-duplicative: approved

Section 7 now draws the correct boundary:

- B absorbs the operation-entry guard requirement from A2A-LEDGER-DESIGN-REFRESH and, when
  scheduled, removes that sub-item from the pool row. DESIGN-REFRESH retains the v2 restatement,
  Docker-versus-wslc correction, and session Option A item.
- B owns startup/readiness declared-anchor-to-head verification, explicit operator-triggered
  on-demand full-chain audit, incident persistence, and operation-entry refusal.
- AT-REST-INTEGRITY retains periodic/scheduled post-readiness historical re-verification, including
  behind-confirmed-cursor tamper detection. It neither substitutes for nor duplicates B's mandatory
  readiness/on-scan guards.

This preserves the frozen risk-slice requirement while keeping the later defense-in-depth detector
under its existing roadmap owner.

### Verification record

- All six proposed feature IDs are unused on `origin/main`:
  `LEDGER-COMPOSITION`, `LEDGER-INTEGRITY-BOUNDARY`, `LEDGER-DATAPATH`,
  `LEDGER-RUNTIME-BOUNDARY`, `LEDGER-AUDIT-WIRING`, and `LEDGER-EVIDENCE-DOD`.
- The obligation matrix contains exactly 20 rows, 20 unique expected obligations, no missing
  obligation, no extra obligation, and no duplicate owner row.
- The slice-letter and dependency references consistently use A–F; F is cumulative closure.
- M17 remains immediate documentation-only work; the scope fence and credential-lifecycle/Cursor
  dependency remain intact.

## Revision 3 final ruling

**Scoping approved.** The next decision belongs to the operator: either declare the feature not
shipped and correct only M17, or authorize the remediation program. If remediation is chosen, the
Pre-A gate contract and immediate M17 correction precede per-slice design/plan work. This approval
does not itself authorize Claude to draft those designs or any agent to implement changes.

<!-- PRESERVED-BODY-END -->
