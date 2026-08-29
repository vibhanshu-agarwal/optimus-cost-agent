# A2A Ledger Remediation — Scoping Contract (preserved record)

Preserved from gitignored `.superpowers/sdd/a2a-remediation-scoping-proposal-DRAFT.md` on 2026-08-12.
Audited commit `e5f7e339`. Author: Claude (drafter). Reviewer: Codex.

**Current authority: APPROVED at Revision 3 by Codex on 2026-08-12** as the remediation
scoping contract. This supersedes the preserved body's historical "DRAFT / for review" and
"Authorizes nothing" status text. Approval settles scope and custody only — it authorizes
**no** design, implementation, or scheduling of slices A-F.

The region between the PRESERVED-BODY markers below is byte-identical to the source and
must not be edited. Any later material (for example a custody manifest) goes **outside** it.

<!-- PRESERVED-BODY-START -->
# A2A Ledger Remediation — Scoping Proposal (REVISION 3, for Codex review)

**Author:** Claude (drafter, under the operator's 2026-08-12 role flip)
**Reviewer:** Codex (author of the independent audit)
**Source of truth:** `.superpowers/sdd/a2a-audit-independent-findings.md` — 17 ranked findings,
verdict **NOT SOUND AS A SHIPPED, TRUSTED SLICE**, audited at `e5f7e339`.
**Prior review:** `.superpowers/sdd/a2a-remediation-scoping-review.md` — CHANGES REQUIRED.
**Status:** Revision 3, for review. Authorizes nothing. Revised in place because revision 1 was
never approved or digest-pinned; the `_vN` rule governs approved artifacts, not a draft returned
for correction.

All eleven checklist items from the review are addressed. Where the review and revision 1
disagreed, **the review won on every point** — including two the drafter had marked as verified.

## 0. What changed, and why revision 1 was wrong

| Review finding | Disposition |
|---|---|
| P0-1 A had a hidden dependency cycle | **Accepted.** A promised a "ready" ledger while B owned integrity readiness and D owned the service credential. A could only close by doing part of B and D, or by calling an admin-credentialed service with incomplete integrity "ready". Recast in §3. |
| P0-2 H9 mis-homed in D | **Accepted.** Creating the least-privileged role *is* a provisioning action; A cannot "provision from nothing" while D owns the identity provisioning must create. Moved to A. |
| P0-3 M16 two-thirds homeless | **Accepted, and it exposes a verification failure — see below.** |
| P1-4 H12 cannot wait for evidence closure | **Accepted.** Split temporally; the gate contract precedes A. |
| P1-5 C need not depend on all of B | **Accepted.** Only H4 has a latch interaction. |
| Corrected triage | **Adopted verbatim.** "No known live trigger" was not a valid downgrade basis. |
| Non-goal clarifications 1-4 | **Accepted**, including that the other five entry kinds are deferred, not permanent non-goals. |
| Cursor/credential-lifecycle dependency | **Accepted**; verified at pool lines 112-113. |
| Adjacent custody overlap | **Accepted**; resolved in §7. |

**The verification failure worth recording.** Revision 1 reported "coverage EXACT 1:1, all 17
findings, one home each." That check compared *labels*. M16 contains three independent obligations —
production audit recording, rate/concurrency bounds, typed integrity status — and revision 1
assigned only the third. The script proved the wrong property and the drafter reported its output as
if it proved the right one. **This revision's coverage matrix is stated at obligation level (§6), not
label level, and any future check must operate on that matrix.** A mechanical check that passes
while the semantic property fails is worse than no check, because it manufactures confidence.

## 1. Why this is not one plan

Seventeen findings span composition, security wiring, data-path authorization, packaging, privilege,
runtime observability, and evidence regeneration. Bundling them repeats the "Plan 9.96 was ~3 plans
in one" scoping failure.

**Corrected sequencing claim.** Revision 1 said "nothing else can be proven before A." That was too
absolute and needlessly serialized the program. The accurate statement:

> B, C, and D can prove their component invariants with focused unit and integration tests while A
> is being built. What no slice can obtain without A is **clean-installed production acceptance** —
> proof that the shipped, installed artifact reaches the fixed behaviour. F is the only cumulative
> trust closure.

Every slice therefore carries **two evidence levels**:

1. **Component proof** — focused unit/integration evidence, independent of A; and
2. **Clean-wheel composition acceptance** — depends on A, and is **re-run as each subsequent slice
   lands**, not once.

## 2. Naming and numbering

Evidence/handoff product work carries **no plan numbers** (enforced by
`test_new_pool_has_no_scheduling_plan_numbers`). Slices take product feature IDs, tracked in
`docs/superpowers/plans/archive/evidence-handoff-open-work-pool.md`.

Revision 2 dropped this table by mistake; restored here with the sixth ID minted per R2-2. All six
verified unused repo-wide.

| Slice | Feature ID |
|---|---|
| A — Installed composition substrate | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` |
| B — Integrity as a mandatory boundary | `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` |
| C — Data-path authorization and atomicity | `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` |
| D — Runtime service security and transport bounds | `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` |
| E — Audit wiring and evidence observability | `EVIDENCE-HANDOFF-FEAT-LEDGER-AUDIT-WIRING` |
| F — Evidence and DoD closure | `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` |

`…-RUNTIME-BOUNDARY` replaces revision 2's `…-PRIVILEGE`, which became inaccurate once H9 moved to A
and M16b joined D.

Later amendment of an approved slice creates `_v2` of that file per the 2026-08-11 rule.

## 3. Proposed slices

### Slice A — Installed composition substrate  **[enabling, not the trust gate]**

Covers **C1**, **C3**, **H7**, **H9**, **M15**.

One fail-closed composition root plus an operator runbook provisioning from nothing: create the
**least-privileged application DB role** and pass only that credential onward; apply **packaged**
migrations; resolve first-run signing-key custody in a valid order; initialize metadata; enroll
principals and issue credentials; start and stop the real MCP service; report truthful
**cross-process** status; classify malformed `ledger_instance.json` as an instance fault rather than
silently overwriting it; document cleanup and recovery.

*Grouped because* C3 is a defect **in the start sequence itself**; H7 is what makes the runbook
executable from an installed artifact; H9's role creation **is** a provisioning action — the same
seam that caused the original composition failure; and M15 is the same start/status surface. Fixing
any separately means standing the composition root up more than once.

**Explicitly NOT the trust gate.** A closes with the feature **default-off and untrusted**. A does
not claim integrity readiness (B) or a trusted runtime boundary (D).

**A ships a fail-closed readiness seam whose pre-B default verdict is NOT-READY.** This is the last
hidden B dependency and it is closed by construction: A must not close by starting a service that
serves ledger operations without B, and "running" must not quietly require B's monitor. A also
**must never select the H8 unauthenticated stub** in its composition path — the separately callable
public-stub defect remains D's.

**Done when:** a clean Windows walkthrough from an **installed wheel** — not a checkout — reaches a
**running service process held non-ready for ledger operations**, then tears it down. The
walkthrough proves:

- installation, packaged migrations, metadata, key custody, enrolments and credential issuance;
- creation and **exclusive** use of the application DB role — the lifecycle/admin credential
  **never enters the service process**;
- service-process start/stop and truthful cross-process lifecycle status;
- authentication rejection and identity binding at the perimeter; and
- **authenticated ledger tool traffic is refused with a stable not-ready outcome** until B installs
  a successful readiness provider/verdict.

### Slice B — Integrity as a mandatory boundary

Covers **C2**, **H13**, **M16c**.

Construct `IntegrityMonitor` in production; verify the declared ordinary genesis **or recovery
anchor** through head before accepting traffic; latch every detected chain, counter, or instance
fault; reject corrupt latch representations rather than reading them as "no incident"; guard append,
**all** reads, delivery confirmation, cursor advance, and acknowledgement **at operation entry**;
make replacement audits anchor-aware; report `INTEGRITY_FAILED` distinctly from `UNAVAILABLE`.

H13 is **trust-blocking, not adjacent recovery work**: B's defining contract is full verification
from ordinary genesis *or* recovery anchor, and a verifier that rejects its own valid linked
replacement fails that contract.

### Slice C — Data-path authorization and atomicity

Covers **H4**, **H5**, **H6**.

Remove or recipient-filter-and-chain-verify direct `review_ruling_read`; require the sanitizer
success type to be `SanitizedDraft` rather than accepting any object lacking an `ok` attribute;
execute status, range verification, witness, and token creation in one consistent snapshot.

**Parallel with B.** Only H4 touches the latch. C carries one combined post-B regression proving
direct reads and snapshot/token paths also respect the latch; that checkpoint does not block C's
implementation.

### Slice D — Runtime service security and transport bounds

Covers **H8**, **M14**, **M16b**.

Make the unauthenticated stub test-only and unreachable from the public CLI; fail closed when the
auth bundle cannot be deleted or its permissions proven restrictive; add pre-parse rate and
concurrency bounds.

Renamed from "Privilege" because H9 moved to A. These three govern **whether the service process may
launch and how much traffic it will admit** — one coherent runtime launch and transport-protection
surface, with shared failure modes and shared evidence.

### Slice E — Audit wiring and evidence observability

Covers **M16a**.

Construct and use `AuditRecorder` across transport, authentication, session, delivery, and integrity
paths.

**Split out as its own slice per R2-2, decided now rather than deferred to design.** M16a crosses
six subsystems, and its change surface, failure modes and evidence differ from D's launch/transport
work. Leaving the split to Slice D's design would have asked that design to rule on whether its own
cross-cutting scope was too large — reintroducing exactly the ambiguity this scoping stage exists to
remove.

E may define its event/recorder contract **in parallel** with B/C/D, but its production integration
acceptance follows the **stable B/C/D event surfaces** and must **precede** F.

### Slice F — Evidence and DoD closure  **[must be last]**

Covers **H10**, **H11**, **H12 (cumulative half)**.

Replace assertion-only capstone sign-off; require the
`explicit_recipient_delivery_reaches_other_agents` outcome absent from `REQUIRED_OUTCOMES`; probe the
endpoint rather than syntax-checking it; archive exactly the filename and layout the verifier
consumes; run cumulative clean-install, CI, live-tier and documentation-freshness evidence.

**F must not reintroduce the identity overclaim.** A server-signed receipt binds an *authenticated
principal credential* to a *server-observed operation*; it cannot prove which native executable held
that credential. Raw client transcripts are corroboration. F uses a claim-to-evidence table stating
those exact strengths — "bind client to request" is too ambiguous to be an acceptance criterion.

### Pre-A — Program gate contract  *(process infrastructure, not a slice)*

Covers **H12 (contract half)**.

Before Slice A is planned: one program-level gate inventory reconciling the plan list and CI, plus a
checkbox rule every slice inherits — a checked box requires its command to exit 0 **with the intended
tier actually selected**. Today neither the plan nor CI is a superset of the other, and a step whose
command exited 5 with all tests deselected was checked. Leaving this until F would repeat the exact
process failure under review.

### Immediate — pool correction  *(documentation only)*

Covers **M17**. The row says `Closed` and is wrong on tip commit, commit count, and "no PR opened".
It must also reconcile the design-refresh, credential-lifecycle, at-rest-integrity and peer-liveness
ownership statements — not merely the three Git facts. Must not edit any digest-pinned artifact.

## 4. Explicit scope fence

**Out of this remediation; absence is not a defect** (frozen-design non-goals): automatic agent
wakeup, real-time relay, peer-liveness synthesis, verified native-process identity, cryptographic
non-repudiation, resistance to a malicious same-OS user.

**Deferred, NOT permanent non-goals — retained under existing roadmap custody:** the other five v1
protocol entry kinds. Revision 1 wrongly labelled these "do not remediate", which mislabels deferred
protocol completion as a design decision.

**The malicious-same-user non-goal does not excuse M14.** Restrictive permissions and deletion of the
signing-key/DB bundle are explicit shipped controls against ordinary exposure and must fail closed.

## 5. Triage — adopted from the review

Revision 1's table is withdrawn. "No known live trigger" was not a valid downgrade basis: concurrent
append is normal A2A behaviour (H6) and linked replacement is a required recovery path (H13).

| Class | Findings |
|---|---|
| **Must fix before any trust** | C1, C2, C3, H4, H5, H6, H7, H8, H9, H13, M14, M15, M16b, M16c |
| **Must exist before an evidence claim** | M16a, H10, H11, H12 |
| **Immediate documentation correction** | M17 |

There is no "Should fix" or "Accept or schedule" bucket. **M16 may be accepted only through an
approved design amendment** that changes the frozen security/observability requirements and states
the residual risk — a triage table cannot silently waive frozen design.

## 6. Coverage matrix — obligation level, not label level

| Obligation | Slice |
|---|---|
| C1 composition root and runbook | A |
| C2 integrity wired, latched, guarded at entry | B |
| C3 first-run key custody ordering | A |
| H4 recipient confidentiality on direct reads | C |
| H5 sanitizer success type | C |
| H6 single-snapshot read/token coherence | C |
| H7 migrations packaged in the wheel | A |
| H8 no authenticated-looking stub from the public CLI | D |
| H9 least-privileged service DB role | A |
| H10 capstone evidence strength | F |
| H11 verifier proves delivery and liveness | F |
| H12a program gate contract | Pre-A |
| H12b cumulative DoD closure | F |
| H13 replacement-anchor-aware audit | B |
| M14 fail closed on bundle protection/deletion | D |
| M15 cross-process status; malformed instance file | A |
| M16a production audit recording | **E** |
| M16b rate and concurrency bounds | D |
| M16c typed integrity state | B |
| M17 pool correction | Immediate |

20 obligations from 17 findings. Every obligation has exactly one owner. The R2-2 split moved M16a
from D to the new Slice E and renumbered evidence closure to F; the obligation count is unchanged.

**Dependency order:** Pre-A → A → {B, C, D in parallel} → E (production integration acceptance) → F.
E's contract definition may begin in parallel; only its integration acceptance is ordered.

## 7. Adjacent custody — resolved, no dual ownership

- **`A2A-LEDGER-DESIGN-REFRESH`** — **ruled (R2-3): B absorbs the operation-entry guard
  requirement.** When B is scheduled, the pool must **remove that sub-item** from DESIGN-REFRESH,
  which retains the design `_v2` restatement, the Docker-versus-wslc correction, and the session
  Option A item. No dual owner.
- **`AT-REST-INTEGRITY`** — **ruled (R2-3); revision 2's categorical "B does NOT absorb" wording was
  wrong** and is replaced by this split:
  - **B owns** startup/readiness full declared-anchor-to-head verification, **explicit
    operator-triggered on-demand full-chain audit using the same verifier**, incident persistence,
    and operation-entry refusal.
  - **AT-REST-INTEGRITY owns** periodic/scheduled re-verification **after** readiness, including
    detection of tampering behind every confirmed cursor, and **does not weaken or substitute for**
    B's on-scan/readiness guards.

  The old wording was misleading because B's anchor-to-head readiness **is itself** historical
  verification, and omitting the operator-triggered audit would leave a frozen first-slice
  requirement unremediated. Narrow the at-rest pool row when B is scheduled — narrowed, not
  duplicated.
- **`CREDENTIAL-LIFECYCLE`** owns OAuth, rotation, `kid`/JWKS, dynamic registration, and the gated
  OAuth-discovery / missing `WWW-Authenticate` interoperability defect recorded at pool lines
  112-113. **F's native-client claim depends on the interoperability subset of that row, or F must
  narrow its claim.** F must not present a probe or workaround as proof that stock Cursor
  integration works.
- **`PEER-LIVENESS-SIGNAL`** remains independently owned and untouched.

## 8. Open questions for the operator

1. **Is the feature still wanted?** A-F is substantial and the audit establishes the ledger is not
   close to shippable. Declaring it explicitly **not shipped**, fixing only M17, and deferring A-F
   until a consumer justifies them is defensible and the review agrees. What is *not* defensible is
   calling it trusted while deferring anything in the first two triage rows. **Decide before Slice A
   design work begins.**
2. **Implementer assignment.** Cursor implemented the original slice — natural implementer, wrong
   self-assessor. Codex holds audit context but is reviewing. Needs deliberate assignment.
3. **Slice D/E split** — decided now per R2-2 (six slices). Confirm no further split is wanted.

<!-- PRESERVED-BODY-END -->
