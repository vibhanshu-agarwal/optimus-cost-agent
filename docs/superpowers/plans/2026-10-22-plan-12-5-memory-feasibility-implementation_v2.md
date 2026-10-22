# Proposed Plan 12.5 v2: independently closable feasibility probes (M0a-3)

> **For agentic workers:** after exact-revision approval, establish Task 0 and the safe runner in Task 1, review Checkpoint 1, then execute/disposition Tasks 2–5 independently and close at Checkpoint 2. Do not execute this draft now.

**Goal:** resolve or explicitly hand off package/parser/embedding/worker, Redis, Postgres and ACP/Zed feasibility. This extracts former Tasks 4–6 and their closure from the preserved combined M0a draft, SHA-256 `365304b45dfc3ba26df3aaf66be417f148754ab6b8d1fd74fccb3c9936c35a84`. It does not require all probes to succeed or even be released.

**Architecture/stack:** bounded CPython 3.14+ probe tools over synthetic inputs, isolated candidate environments and separately approved disposable services/clients. Probe records are standalone; they do not import the Plan 12.3 policy/registry or Plan 12.4 grader. Real dependencies are mandatory only for claims about their behavior.

**Authority/base:** frozen v12 SHA-256 `33670c6b84aceccd629437c14f03609ba4293d70cde95b242dd93a2b0ad4fb14`; updated freeze record `13880f7779a72a51a90444d0f659faaf8f9a251cc430e06cbdc37daa68c4073f`; post-freeze brief `f81a080b3b9065295dd47b817fbd411c00d2cba9b3614b1d69c41dc06796acd9`. Source inspected at main `dbdfaa3210b329c9fae6de2fb80811174e361786`. [Whole-feature spec v3](../specs/2026-10-22-plan12-memory-design_v3.md) defines the accepted boundaries and proposed mechanisms.

**Publication/authority:** unregistered review draft in an artifact folder, not a live root plan or execution release. Recheck the proposed linear number, ADR number, source drift and overlap before authorized filing. Each plan needs its own issue and issue-only work-register pointer, plus the current docs index entry, under ADR-022. Preserve predecessor documents and frozen handoff inputs. No issue/label, branch, infrastructure, commit, push, PR or merge is authorized by authoring this plan.

**Roles:** Codex authors; Claude reviews and owns the operator chat; the operator approves the exact spec/plan revision there. Claude implements only after that release. At each named checkpoint Fable reviews first, then Codex. No per-task review ceremony or execution delegation is implied. Record reviewer evidence under the repository's owner/reviewer workflow; private memory is never authority.

**Assessment:** proposed `priority:high`, `handler:claude`, `difficulty:high`, `estimate:5d`. Claude/Codex consensus is five active working days, excluding setup/release waits, subject to exact-revision operator approval. A blocked probe is an owned handoff, not an instruction to keep waiting. Runtime implementation remains in later slices.

**Review revision (2026-10-23):** complete successor to preserved `2026-10-22-plan-12-5-memory-feasibility-implementation.md`, SHA-256 `3646ca9f82a50fa548c75b2d53e9b7dace66ee351361d1b66ca44662e6713914`. Claude review: `1872834f0d8c344abd6dedbf18dd74f1797dc0ac5dcffd1086c9bca946dc7bac`; endorsed cover note: `ebde0286753248ca7bdf3b230b4abc87579115a16debeebdaa5b887627941633`. All review dispositions are in spec §10. Reviewed drafts and frozen inputs stay unchanged.

**Run order:** **12.4 → 12.3 → 12.5**, as endorsed. #385 remains open/unassigned and gates 12.3; assigning its hardening owner is a separate GitHub write. Scheduling does not create implementation dependencies between these independently closable plans.

## Prerequisites

| Requirement | Satisfied today? | Owner | Disposition / first task |
|---|---|---|---|
| Approved revision, own issue/filing and isolated contributor checkout | no | Operator releases; Claude establishes | Merely unauthorized. Task 0 establishes without requiring another M0a plan to close. |
| CPython 3.14+, uv/Git and frozen dev/test environment | unknown | Operator; Claude inventories | Task 0 resolves before runner work; environment absence can hold runner implementation, not be reported as a successful measurement. |
| Candidate packages/model files, Windows wheels and licenses | unknown | Claude; operator owns downloads | Per-probe inventory before Task 2. No global install or unrestricted model download. |
| Dedicated Redis 8.4+ Search/JSON/TimeSeries, port/ACL/volume and resource release | unknown | Operator owns resource release; Claude verifies | Task 0 distinguishes absent versus unauthorized. A missing resource hands P3 to M1, leaving other probes free. |
| Separate loopback Postgres and driver/connectivity release | unknown | Operator; Claude verifies | Missing resource hands P4 to M0b; never reuse evidence-handoff or product credentials/data. |
| Installed Zed/ACP/acpx path, synthetic workspace and manual ceremony | unknown | Operator owns client state; Claude records | Missing/unreleased resource hands P5 to M1/M3 with disk/first-response fallback. |
| Network/model/service/GUI budget and endpoints | no | Operator | Merely unauthorized until a bounded release per probe. Zero paid-call authority. Unreleased operation stays UNRUN. |
| One isolated coverage writer/test context | unknown | Operator owns schedule; Claude verifies | Establish for runner tests and final checks. No authority over other lanes. |
| Plans 12.3/12.4 and real corpus | yes — not prerequisites | None | Use synthetic fixtures and local standalone records. Optional real-corpus sampling is a separately gated extension, not a closure condition. |

## Constraints and evidence discipline

- No paid calls. All later provider traffic must use Gateway accounting and separately approved budgets. This plan does not implement Auto or change a model picker.
- B1: feature artifacts retain pointers/hashes, sanitized metadata and synthetic data; source/buffer bodies remain RAM-only. Existing Q27 diagnostics are separate scope.
- Neutral `context_engine` imports no host/Gateway/security/evidence/model-policy implementation. Existing Optimus/compaction must work when the feature is absent.
- All checkboxes start empty; every implementation/test/probe result is **UNRUN** at authoring. Fixture validity, administrative closure and production acceptance are different claims.
- Preserve failed attempts, skips, UNKNOWN and platform qualifications. No retry-to-green, forced runs, cleared pytest addopts, borrowed hook exceptions or mock substituted for a named real dependency.
- Use an isolated contributor checkout and test context, its own `.venv` and `uv sync --frozen --extra dev`, after authorized setup. Never mutate another lane or adopt a production/default test service. Only one coverage writer per checkout.

## Planned files and interfaces

| Unit | Paths / contract |
|---|---|
| Runner/records | `tools/plan12_memory/{__init__,probes,redis_probe,client_probe}.py`; optional small package/Postgres helpers only when needed. `run_probe(kind: str, config: ProbeConfig) -> ProbeResult`; no import-time work. If the namespace already exists, preserve its owner and avoid overlapping edits. |
| Config | `ProbeConfig` identifies probe, source/environment/config hash, authorization reference, synthetic fixture, endpoints/resource/time/download limits and predeclared numeric targets. Redis requires explicit `redis.endpoint` and released container/port/volume identity; pytest reads the config path only from required `OPTIMUS_PLAN12_PROBE_CONFIG`. No generic Redis env/preflight default. Credential references only, never literal secrets. |
| Result | `ProbeResult` records attempt/run IDs, start/end UTC, platform/packages/service digests, observations/counters/artifact hashes, outcome, retained failed attempts, capability scope, limitation, follow-up owner and closure disposition. Execution status and administrative disposition are distinct fields. |
| Tests | `tests/unit/tools/test_plan12_memory_probes.py`; real Redis tier `tests/integration/tools/test_plan12_memory_redis_probe.py` marked only with dedicated `requires_plan12_probe_redis`, never `requires_redis`. Extend `tests/unit/tools/test_run_context.py` for the revised approved marker expression and guarded-default behavior. Doubles test parsing/containment only. |
| Marker/selection | Modify `pyproject.toml` marker registration/default exclusion and `tools/testing/run_context.py` approved `EXCLUDED_BY_DEFAULT` list in lockstep. Check static profile/explicit selection behavior through existing `tests/support/profiles_plugin.py` and its selection tests; do not broaden profiles or disable guards. |
| Evidence | `reports/plan12-memory-feasibility/{manifest,probe-config,qualification,handoffs}.json`, sanitized Markdown report. Independent attempt records per probe; no bodies/buffers/secrets in persistent output. |
| Deferred probes | No Initializr/graph/L2 implementation here. Their future `dependency_probe.py`/tests/config are owned by starts of M5a/M7/M5b. |

## Probe completion and handoff contract

| Probe | Observed result may conclude | If blocked/unreleased/inconclusive: owner and consequence |
|---|---|---|
| P1 packages/parsers | Exact compatible pins/licenses or an observed unsupported combination | Claude, frozen v12 M1 for indexing packages; M3 for encryption dependency. Re-run the missing combination before using it; no blanket CPython 3.14 support claim. |
| P2 embeddings/worker | Bounded throughput/RAM and cancel/resume/owner-exit behavior | Claude, frozen v12 M1. Keep performance assumptions unqualified and select no unmeasured model/runtime; prototype cursor is not a product worker. |
| P3 Redis K2 | Synthetic one-instance measured pass/fail and provisional fallback choice | Claude, frozen v12 M1. No qualified topology or capacity claim until the missing synthetic run and real-corpus run are obtained; production Gate still belongs to M3. |
| P4 Postgres | Native driver, commit/rollback/reconnect readiness | Claude, frozen v12 M0b. Resolve connection/packaging before ledger integration; no durable-ledger acceptance inferred. |
| P5 client capabilities | Exact client/version observations for buffers, pre-prompt display, model-independent host cards and nonpersistent-display canaries | Claude, frozen v12 M1 (buffers), M3 (brief/notices/phrase channel). Default to disk-backed context and first-response brief. No proven confidential display means qualify the restricted-file fallback in M3 or disable encryption/rotation, not core memory. |

A blocked handoff includes source/config, reason, last attempt/status, missing release/resource, named owner/roadmap entry, required follow-up check, fallback and effect on dependent claims. The owner/reviewers acknowledge custody at the checkpoint; create/link an issue only under normal filing authority. **Closed-with-handoff is not PASS.** Failed observations remain FAIL; missing execution stays UNRUN; ambiguous evidence stays INCONCLUSIVE. The parent may close when all entries are concluded or accepted in custody, without any sibling waiting for a resource. A later slice cannot treat that administrative closure as evidence that its prerequisite passed.

## Dedicated Redis admission rules (R-2)

The load tier is `requires_plan12_probe_redis`. Register it and exclude it from the default marker expression; update the run-context approved exclusion tuple in the same change so default tests remain ACTIVE/guarded. An explicit probe run selects this marker and uses its own fixture. Never borrow `live_redis_store`, `live_redis_telemetry`, shared `run_preflight`, `OPTIMUS_REDIS_URL` or a shared Redis factory.

The pytest fixture requires `OPTIMUS_PLAN12_PROBE_CONFIG` naming a validated `ProbeConfig` with `redis.endpoint` and the separately released resource binding. No config/endpoint means skip with a specific missing-prerequisite reason, record the live result UNRUN and make **no client construction/socket call**. An explicitly supplied invalid/protected endpoint is rejected, not silently skipped or defaulted. The standalone runner enforces the same admission function.

Before connection, parse/normalize the endpoint, resolve loopback aliases and compare protected endpoints by host/address and port **independent of database number**. Refuse shared/default `redis://127.0.0.1:6379/0`, localhost/IPv6 aliases and every database on that server, plus any registered shared-test/product endpoint. Allow only the operator-released dedicated loopback mapping. Bind the approved port to the disposable container/image and distinct volume through inspected resource metadata; absent/ambiguous identity or an alias/proxy to a protected service is refused before load/mutation. A new key prefix or DB number is not isolation. Confirm native server identity/config read-only before load; abort on mismatch. Restart tests reconcile that same container/volume identity rather than treating a changed Redis process run ID as permission to adopt a different server.

Offline negative controls cover missing config, malformed URL, shared endpoint/aliases/alternate DB, unsafe resource mapping and accidental shared-fixture use; assert no connector invocation. A released dedicated-server positive control supplies the real-dependency proof. Default/profile collection checks must show this tier deselected, without overriding addopts or weakening normal run-context guards.

## Task 0 — Establish each probe's attainable scope

**Consumes:** authority/base and machine/resource inventory. **Produces:** independent release/config rows and test context. **Checks:** all attribution/safety prerequisites, no production acceptance.

- [ ] Recheck source, numbers, overlap and own issue; obtain exact-revision execution/filing authority before implementation. Inventory prerequisites as yes/no with owner and absent/unauthorized/hard disposition.
- [ ] Fix per-probe endpoints, maximum elapsed time, RAM/disk, package/model bytes, permitted public egress and disposable resource IDs. Paid-call limit is zero. GUI/client launch or strict preflight requiring provider traffic remains UNRUN without a separate release.
- [ ] Before any qualifying Redis run, require numeric config values for synthetic item/vector count/dimensions/bytes, concurrency, logical `maxmemory`/admission reserve, physical RAM, disk, acknowledgement/projection latency, restart-to-usable deadline and purge logical/physical-erasure deadlines. Record the proposed values and review them before execution. A labelled exploratory run can inform values; it is never the qualifying run. No after-the-fact target change may turn a failed run green.
- [ ] Disposition missing resources independently in the handoff table. Synthetic-input probes need neither #385 integration nor the real project policy. If a representative real-workspace sample is later proposed, first require accepted #385/shared-policy checks and separate source/egress authority; omit it without holding this synthetic plan open.

**Verify:** reviewer inspection of independent config/release rows and numeric target completeness. Expected: no implicit network/service/paid operation and no unresolved dependency silently passed.

## Task 1 — Safe runner and attributable records

**Consumes:** Task 0 permitted scopes. **Produces:** standalone bounded runner, fixtures and result contract. **Checks:** K1 persistence/egress guard controls; K2/K6 evidence attribution.

- [ ] **Red:** timeout/cancel, missing wheel/resource, hash/license mismatch, forbidden egress, synthetic secret in stdout, raw-body persistence, partial output and malformed native result. Include a valid same-view control. A parser failure/inspection failure is INCONCLUSIVE, never proof that the product denies something.
- [ ] **Green:** implement no-work-at-import dispatch, the dedicated Redis admission rules above, exact resource allowlists, cancellation/cleanup journaling and sanitized output. Register/exclude the new marker in pyproject and the run-context approved list together; prove missing probe config never constructs a client and generic Redis environment variables cannot supply a fallback. Keep raw synthetic/model-buffer bodies in RAM; persist only allowed counters/hashes and structured observations. Separate unavailable, error, fail, inconclusive and unrun.
- [ ] Preserve every attempt with its source/config/run identity. Do not overwrite failed qualification with a successful rerun. Cleanup is limited to released disposable paths/resources; no prune or deletion of another lane.
- [ ] Test the runner offline with explicit doubles. Add marker/config negative controls and collection/guard tests: the canonical default expression stays ACTIVE, profiles do not add this live tier, and explicit probe selection does not inherit shared fixtures. No offline runner test may produce a native-service/client PASS.

**Verify:** `uv run --no-sync pytest --no-cov tests/unit/tools/test_plan12_memory_probes.py tests/unit/tools/test_run_context.py -q`. Use collection-only/selection controls without native connections to verify the dedicated marker is excluded from default/profile runs. Expected: positive path works, negative controls are attributable, default-run protection is preserved and no secret/body persists.

## Checkpoint 1 — Safe probe release

Fable then Codex review the runner controls, predeclared config/targets, individual release boundaries and handoff schema. Resolve safety blockers before a dependent live operation. Offline focused checks suffice here; full canonical checks belong to final closure. Release of one probe is not release of all five. A blocked live probe can immediately receive custody while other released probes proceed.

## Task 2 — Packages, parsers, embeddings and worker feasibility (P1/P2)

**Files:** runner/package helpers, unit tests and independent P1/P2 records. **Consumes:** only the packages/models released for this probe. **Produces:** measured support and bounded execution matrix. **Checks:** K2 inputs; K1 artifact constraints.

- [ ] Inventory RedisVL, tree-sitter/per-language grammar wheels, rustworkx, graspologic-native, pathspec, optional cryptography and the proposed embedding driver/model. Record distributions/versions/hashes/licenses/native prerequisites and Windows CPython 3.14 status. If 12.3 already selected pathspec, record that pin as an input, not a prerequisite. Exclude noncommercial weights; runtime pulling does not by itself make a copyleft server license a blocker. No automatic grammar/model download or new agent framework.
- [ ] Use a finite synthetic corpus to parse/embed in RAM. Record hardware, dimensions/chunking, wall time, peak RAM, throughput, output identity and resource limits. No model/download release means UNRUN throughput, not zero or “supported.”
- [ ] Exercise cancel/resume of a synthetic probe cursor and owner exit/restart to inform an in-process resumable worker. This is a feasibility prototype, not the persisted-generation production indexer.
- [ ] Close P1/P2 separately, including partial matrices and named follow-up for unavailable combinations. Do not promote every candidate to a product dependency; add only needed tools and exact pins under the approved implementation scope.

**Verify:** offline suite, then `uv run --no-sync python -m tools.plan12_memory.probes --kind packages --config reports/plan12-memory-feasibility/probe-config.json` and the same command with `--kind embedding`, only for released operations. Expected: source-bound observations or explicit handoff; no broad compatibility claim.

## Task 3 — Synthetic real Redis K2 (P3)

**Files:** Redis helper and named integration test. **Consumes:** dedicated released Redis and Task 0 numeric config, not P1/P2 completion. **Produces:** synthetic measured capacity/recovery result or handoff. **Checks:** K2 feasibility only.

- [ ] Apply the dedicated Redis admission rules before client creation. Verify explicit config path/endpoint, inspected container/image/port/volume binding, distinct ACL, Search/JSON/TimeSeries, `noeviction`, AOF and redis-py APIs. Refuse default/shared endpoints and aliases (any DB); never invoke existing shared-test Redis fixtures or an existing user's dataset.
- [ ] Use bounded synthetic vectors/events/JSON projections, a rebuild burst and derived-growth pressure. Test same-connection append then `WAITAOF 1 0 <timeout>`, returned count, slow persistence, acknowledgement and served projection latency, AOF rewrite/RDB save, restart to usable memory, logical purge and physical erasure horizon.
- [ ] Measure logical `used_memory - mem_not_counted_for_evict`, physical process/container RAM including copy-on-write peaks, and disk independently. Admission reserve is labelled a reserve; scale includes vector count/dimensions and index/persistence bytes. Do not infer memory from LOC.
- [ ] Compare with the preregistered numeric bounds. A failed single-instance result selects the two-instance fallback/design change. Qualify the fallback if separately released; otherwise hand that missing run to M1 with its consequence. Preserve the failed single-instance record.
- [ ] Label the choice provisional: M1 repeats K2 on the real corpus and production adapters; M3 proves the actual Gate, notices, fsync and erasure workflow. A prototype append does not prove production atomicity or durable save notification.

**Verify:** `uv run --no-sync pytest --no-cov -m requires_plan12_probe_redis tests/integration/tools/test_plan12_memory_redis_probe.py -q` with required `OPTIMUS_PLAN12_PROBE_CONFIG` bound to only the released real instance. Preserve other pytest/run-context settings. Expected: metrics and positive/negative native controls bound to source/config, or honestly unrun/inconclusive disposition. Without explicit config/endpoint the live case skips as UNRUN before any connection; a protected endpoint fails admission, with no shared-server access. Marked live evidence remains separate from final default-suite evidence.

## Task 4 — Isolated Postgres readiness (P4)

**Consumes:** its own released loopback database and driver, not Redis/embedding results. **Produces:** packaging/connectivity/transaction observations. **Checks:** K3 readiness only.

- [ ] Reuse the existing evidence-handoff backend pattern while keeping its database/credentials/data untouched. Record exact driver/server versions and scoped temporary database/schema.
- [ ] Observe commit/readback, rollback, disconnect/reconnect and failure behavior using synthetic rows with positive controls. No cost ledger/outbox or accounting calculation is implemented here.
- [ ] Record connection/packaging requirements and close or hand off to M0b, even if Redis or Zed is blocked.

**Verify:** `uv run --no-sync python -m tools.plan12_memory.probes --kind postgres --config reports/plan12-memory-feasibility/probe-config.json` for the released native backend. Expected: attributable readiness observations; no ledger durability/completeness claim.

## Task 5 — Version-bound ACP/Zed capabilities (P5)

**Consumes:** independently released installed client/trust/manual ceremony. **Produces:** four named sub-observations, each with its own status/fallback. **Checks:** K6; informs M1 buffers and M3 brief/notices/recovery channel.

- [ ] Record exact Zed/ACP/acpx/reference-agent versions and launch requirements. Use a disposable trusted synthetic workspace, never a personal editor buffer or existing paid session. All canaries are synthetic; never generate or show a real recovery phrase in this probe.
- [ ] **P5-a, buffer access:** inspect advertised `fs.readTextFile`; invoke `fs/read_text_file` only when advertised. Compare a synthetic unsaved buffer and disk in RAM. Distinguish unsupported, failed call and unrun. Use an independently authored ACP client for protocol evidence; a project probe cannot alone prove interoperability.
- [ ] **P5-b, welcome-back timing:** observe pre-prompt update rendering and first-response fallback. A reference/stub peer may isolate editor rendering, labelled client-only evidence; it does not establish Optimus integration. Unsupported pre-prompt display selects the first-response brief.
- [ ] **P5-c, model-independent notices (N-5):** attempt a synthetic host-generated ACP tool-call/update card through the actual Optimus outbound path, without a model turn or Gateway/provider request; record creation/update IDs, rendering and delivery outcome. Check the zero-call condition with the isolated process/transport observations, not only a missing ledger row. Use an independent client and real Zed for their respective interoperability/rendering claims. A reference-peer card is a separate client-only control, not proof that Optimus can emit one. No ad-hoc production save mechanism is added; if the actual path/zero-call launch cannot be exercised, record UNRUN with the M3 owner and reason. Actual save-to-notice binding remains M3.
- [ ] **P5-d, nonpersistent display (R-1):** investigate any documented/client-supported display path with a unique synthetic canary. Check visible history, close/reopen, client restart and accessible persisted thread state/logs/export paths for that exact version, including card content where relevant. Do not remove history or disable logging to manufacture a private-channel result. Record which sinks were inspected; an inaccessible/unknown sink makes confidentiality INCONCLUSIVE. A successful rendering or canary absent from one file is insufficient. Carry any candidate channel to M3 for explicit acceptance and qualification; otherwise use the restricted-file fallback in spec §6.1.1, or keep encryption/rotation unavailable.
- [ ] If strict preflight/provider access/manual ceremony is unreleased, record each dependent observation UNRUN and name its prerequisite; do not consume a call. Missing P5-c/P5-d evidence does not hold the other P5 observations or sibling probes. M1/M3 own real product/client acceptance.

**Verify:** `uv run --no-sync python -m tools.plan12_memory.probes --kind zed --config reports/plan12-memory-feasibility/probe-config.json` plus actual independent-client/editor observations where released. Expected: a version-bound result and evidence scope for **each P5-a–d**, zero real secrets, zero model/provider calls for P5-c, or an owned unrun/inconclusive handoff.

## Checkpoint 2 — Independently disposition all probes and close

- [ ] Produce one row per P1–P5, with P5-a–d subrows, carrying observed status or accepted named handoff. Missing release never blocks sibling probe closure; failed results are retained and not relabelled as pass.
- [ ] Run final canonical runner checks below. Fable reviews first, then Codex. Resolve runner defects and in-scope evidence blockers; accept handoff custody with the named owner and next required proof.
- [ ] Record dedicated Redis admission/default-exclusion proof, provisional topology, per-capability fallbacks and all incomplete/unqualified assumptions for M0b/M1/M3. Mark production K1–K6 unproved subsets explicitly. Close the administrative plan under authorized workflow even when native measurements remain UNRUN.
- [ ] Confirm former Task 7 was not executed or required here: Initializr starts M5a, bounded G1′/G0 graph starts M7, L2 starts M5b. Preserve their acceptance content in the next-plan handoff per spec §8.1.

**Closure:** accepted runner/tools, own tests and both checkpoints, plus observed or accepted-custody disposition for every probe. No all-probes-PASS requirement. Unresolved defects in the runner are not hidden as external-resource handoffs.

## Verification and final review evidence

Record checkout, branch, source HEAD/tree or explicit dirty-diff hash, interpreter/environment/config, run IDs, platform, exact command, exit status and retained output. Focused tests prove only their named scope. At the final checkpoint run the canonical default selection and validity check once on the implementation revision, then Ruff:

```bash
uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
uv run --no-sync ruff check .
```

Follow current canonical product floors (Optimus/context engine/model policy), repository minimums and aggregate reporting; do not infer a gate from rounded output. Inspect run-context/guard validity. A fix after the full run requires relevant focused proof and disclosure of the exact delta; the earlier run cannot be attributed to newer bytes. Filing/index changes also require the repository docs-index, plan-directory and open-work-pool hygiene tests. Preserve any failure and resolve it under the current workflow, with no inherited bypass.

Final handoff includes sanitized source/config-bound manifest, per-check status, reviewer responses, requirement-to-check map, exceptions with owners and full hashes of the reviewed spec/plan. Claude reviews the returned artifacts; the operator's exact-revision approval and later publication/execution releases remain separate.

## Explicit exceptions and custody

| Outside this plan | Named owner and consequence |
|---|---|
| #385/shared policy/architecture ADR/registry | #385 hardening lane and Plan 12.3; synthetic probes need neither. |
| Golden cases, grader and generic-harness selection | Plan 12.4; native generic-harness/model campaign is #248. |
| Former Task 7 Initializr | Start of M5a: timeout/unavailable and nonexistent-coordinate controls, public dated/hashed metadata, generated-POM/BOM import, authoritative fallback; no build/private upload. |
| Former Task 7 bounded graph | Start of M7: G1′ extraction/traversal versus G0 over bounded synthetic Java/Python modules, new/renamed caller invalidation, malformed graph/stale hash controls; file/node/time limits, no LLM extraction. |
| Former Task 7 L2 | Start of M5b: installed JVM/LSP/runtime availability, bounded resolution and missing-runtime positive/negative controls; no automatic downloads. |
| Production ledger/outbox/Gateway copy and retention | M0b; #303 retains broad telemetry scope. P4 cannot close these checks. |
| Production index/worker and real-corpus topology | M1/M2; P1–P3 handoffs specify any blocking prerequisites. |
| Gate, notices, continuity, keys, backup/restore/purge/rotation | M3 including native keystore deletion and K5-R1/R2; learning/archive M6. |
| Dependency/Q&A products; C3/C4 | M5a/M5b/M7; only their probes' timing changes. |
| Savings UI, paid runs, session load, picker, Q27 | #248/OC-4, Plan 11.7/#240, model-selection work and separate diagnostics hardening respectively. |
| Service creation/deletion, real keyring/GUI, publication and cleanup | Separate bounded operator release; no destructive action inferred from plan closure. |
