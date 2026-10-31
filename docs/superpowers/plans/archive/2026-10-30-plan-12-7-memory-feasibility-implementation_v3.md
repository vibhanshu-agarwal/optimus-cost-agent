# Proposed Plan 12.7 v3: Memory feasibility probes (M0a-3, #391)

> **For agentic workers:** Task 0 establishes attainable scope read-only. The operator must approve this exact revision’s hash in Claude’s chat before Task 1 executes. Claude implements; Codex reviews read-only through the CLI at two checkpoints: safe-probe release and close. Each live operation requires its own operator release.

**File:** `docs/superpowers/plans/2026-10-30-plan-12-7-memory-feasibility-implementation_v3.md`

**Goal:** resolve or explicitly hand off package/parser/embedding/worker, Redis, Postgres and ACP/Zed feasibility. This extracts former Tasks 4–6 and their closure from the preserved combined M0a draft, SHA-256 `365304b45dfc3ba26df3aaf66be417f148754ab6b8d1fd74fccb3c9936c35a84`. It does not require all probes to succeed or even be released.

**Architecture/stack:** bounded CPython 3.14+ probe tools over synthetic inputs, isolated candidate environments and separately approved disposable services/clients. Add new modules to the existing `tools/plan12_memory/` namespace. Probe records remain standalone: they do not import Plan 12.6’s `optimus.guardrails.file_policy` or `optimus.context.project_registry`, or Plan 12.5’s grader/contracts. Real dependencies are mandatory for claims about their behavior.

**Authority/base:** source inspected at main `18093a78961172ec3478b6e40dbc5fc2c64fd6f8`; supplied checkout is `optimus-cost-agent-wt-claude-p127probe`, branch `agent/claude/plan12-7-memory-feasibility`, clean at that HEAD. [Whole-feature spec v4](../specs/2026-10-22-plan12-memory-design_v4.md), SHA-256 `708e0e7831f6d4c56b5f6442cd37c4e02eecffd2659db04f3e6a6b1c54506ff9`, supplies the design. Frozen v12 remains SHA-256 `33670c6b84aceccd629437c14f03609ba4293d70cde95b242dd93a2b0ad4fb14`; its freeze record is `13880f7779a72a51a90444d0f659faaf8f9a251cc430e06cbdc37daa68c4073f`, and the post-freeze brief is `f81a080b3b9065295dd47b817fbd411c00d2cba9b3614b1d69c41dc06796acd9`. Private originals are archival provenance, never execution dependencies.

## Revision v3

Complete successor to the operator-approved v2, `2026-10-22-plan-12-5-memory-feasibility-implementation_v2.md`, SHA-256 `5734863716237935a546eb9ad63607d64309a6806baca2349e17172b5bb34b08`, approved against spec v3 on 2026-10-23 without execution authority. Preserve those bytes.

This revision assigns **Plan 12.7**, corrects sibling references and run order, adopts spec v4 and main `18093a7`, records accepted ADR-031 and Plan 12.6’s selected parser, extends the existing tools namespace, adds required repository inventories, applies the lean two-checkpoint workflow and blocker-absorption rule, specifies filing/corrective-comment authority, and names the #447 Windows exception. The proposed estimate becomes **4 working days**.

**Run order:** **Plan 12.5 / M0a-2 evaluation (#389, closed through PR #444) → Plan 12.6 / M0a-1 foundations (#390, closed through PR #446, merge `efa1235`, including absorbed #385) → Plan 12.7 / M0a-3 feasibility (#391)**. The first two are complete and archived through PR #449. Plan 12.3 is loop control; Plan 12.4 is Auto mode. Scheduling creates no new implementation dependency between these independently closable slices.

The operator’s Round 83 directions supersede dated numbering, ownership, sequencing and review wording in the predecessor/spec. Probe scope and accepted design boundaries remain unchanged.

## Authority, roles and filing

Codex authors; Claude Opus reviews the plan, implements and owns the operator chat. The operator approves the saved revision’s exact hash there before Task 1. Codex reviews at the two named checkpoints through:

```bash
codex exec -m gpt-6.1-sol -c 'model_reasoning_effort="high"' -s read-only
```

Pass model and effort explicitly on every invocation, including resumed sessions. Fable is used only for genuinely complex points, at Claude’s judgment; no Fable-first or per-task review step applies. **Codex’s checkpoint acceptance counts as the operator’s review verdict.** It grants no execution, live-operation, GitHub, push, PR or merge authority.

Claude maintains `docs/superpowers/reviews/plan-12-7-review-checkpoints.md`, with Current State and dated rulings, gitignored and unstaged. Under approved GitHub writes, post CLI reviews verbatim to #391 using the required reviewer/model/effort/session heading.

**Filing happens in this plan’s PR:** this successor, `docs/README.md`, and one ADR-022 issue-only live-plan registry pointer to #391. Under operator-approved GitHub writes, set the issue title to **“Plan 12.7 — Memory feasibility probes (M0a-3)”**, apply agreed labels, and post a corrective comment identifying this plan, spec v4, their full hashes, corrected siblings/run order, workflow and #447 exception. **Do not edit #391’s historical body.** Keep current status and next gate in the issue, without a second work register.

[ADR-031](../../decisions/ADR-031-project-memory-and-evidence.md), Accepted through PR #448, already records the memory architecture and selected parser. **No new ADR is planned:** these probes measure that design and inform its provisional choices. A finding requiring a change to an accepted architectural decision needs a recorded disposition before dependent implementation; never rewrite frozen ADR-031.

**Blockers:** under the operator’s 2026-10-30 rule, issues blocking Plan 12.x work are fixed as tasks inside the blocked plan. Check existing issue ownership before proposing any new issue; do not send an in-scope blocker to another lane. Missing live-operation authority remains an honest handoff under this plan’s contract. The expressly excluded #447 baseline failures remain with #447.

**Assessment:** `priority:high`, `handler:claude`, proposed `difficulty:high`, proposed `estimate:4d`. Four working days cover runner/admission controls, package/worker probes, service/client probes, and evidence/final verification. The reduction from v2’s 5d reflects the delivered parser, existing drivers/lifecycle pattern and lean reviews. Release waits and CI queue time are excluded. Claude/Codex agreement and operator approval precede label writes.

## Prerequisites

| Requirement | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Exact-revision execution approval | no | Operator | Merely unauthorized. Required before Task 1; predecessor approval did not release execution. |
| Dedicated contributor checkout/branch | yes | Claude | Supplied checkout exists and is clean at `18093a7`. Task 0 rechecks source drift and overlap. |
| CPython 3.14, uv/Git/Bash | yes | Operator owns machine state; Claude inventories | Claude observed CPython 3.14 and uv 0.11.29 on 2026-10-30; Git/Bash paths are present. Record exact identities in Task 0. |
| Frozen worktree environment and one coverage writer | unknown | Operator owns schedule; Claude verifies | Task 0 establishes before tests; use this checkout’s own `.venv`. Any needed package download requires release. |
| Docker engine | yes | Operator owns machine state | Claude observed server 29.9.2 on 2026-10-30. Availability does not release container operations. |
| Dedicated Redis 8.4+ with Search/JSON/TimeSeries, ACL/port/volume | unknown | Operator releases; Claude verifies | Task 0 establishes availability and authority separately. Shared `optimus-redis`, image `redis:8`, at `127.0.0.1:6379` is protected and cannot qualify P3. |
| Isolated Postgres and driver | unknown | Operator releases; Claude verifies | `psycopg[binary]>=3.2,<4` is already a runtime dependency; no `psql` CLI is installed or required. Task 0 inventories a separate disposable server before P4. |
| Candidate package/model availability and licenses | unknown | Claude; operator owns downloads | Inventory before Task 2; no automatic downloads or global installation. |
| Zed/acpx binaries | yes | Operator owns machine state | Claude observed Zed 1.26.2 at `%LOCALAPPDATA%\Programs\Zed` and global npm acpx 0.12.0. Recheck versions before version-bound evidence. |
| Disposable client workspace, trust/TTY/manual ceremony and usable zero-call path | unknown | Operator; Claude verifies | Establish before each P5 observation. A binary’s presence does not establish this prerequisite. |
| Per-operation service/download/GUI releases | no | Operator | Merely unauthorized. Each container start, package/model download and Zed/GUI session needs its own bounded release. Zero paid calls. |
| Linux PR CI and filing/publication authority | no | Operator | Merely unauthorized; GitHub writes, push, PR and merge require approval. |
| Sibling product APIs and real corpus | yes | None | Siblings are delivered; probes use synthetic inputs and standalone records. Real-corpus qualification remains M1. |

For every unknown, Task 0 records whether the capability is merely unauthorized, genuinely absent but buildable now, or genuinely hard because of an external dependency or unknown difficulty. Establish that disposition before dependent work.

## Constraints and evidence discipline

- **Scope:** multi-file tools/tests/configuration/documentation changeset. No production memory runtime, Gate, ledger, indexer or save mechanism is implemented here.
- No paid calls. Any later provider traffic requires Gateway accounting and separate authority. This plan does not implement Auto or change a model picker.
- **B1:** feature artifacts retain pointers/hashes, sanitized metadata and synthetic data; source/buffer bodies remain RAM-only. Existing Q27 diagnostics remain separate scope.
- Neutral `context_engine` imports no host/Gateway/security/evidence/model-policy implementation. Existing Optimus and compaction must work when the feature is absent.
- Every checkbox starts empty. Implementation tests and probes are **UNRUN** at authoring. Fixture validity, administrative closure and production acceptance are distinct.
- Preserve failed attempts, skips, UNKNOWN and platform qualifications. No retry-to-green, cleared pytest addopts, borrowed hook exceptions or fake substituted for a tier’s named real dependency.
- Use the worktree’s own frozen environment, established with `uv sync --frozen --extra dev` under applicable setup/download authority. Only one coverage writer per checkout.
- Targeted tests per change; authorized commits skip **only** `optimus-pytest-coverage`. Every other applicable hook runs.
- Exactly one Windows full suite with coverage on the final code head, then Linux PR CI as the second full run. WSL is reserved for non-trivial CI failures.
- Resource creation, restart, download, GUI interaction and cleanup must stay within their separate operator releases. No authority over another lane or shared service is implied.

## Planned files and interfaces

| Unit | Paths / contract |
|---|---|
| Runner/records | Create `tools/plan12_memory/probes.py`: validated `ProbeConfig`, `ProbeResult`, `run_probe(kind: str, config: ProbeConfig) -> ProbeResult`, CLI dispatch for `packages`, `embedding`, `redis`, `postgres`, `zed`; bounded package/worker/Postgres helpers. No import-time work. |
| Service/client helpers | Create `tools/plan12_memory/redis_probe.py` and `tools/plan12_memory/client_probe.py`; shared admission through the runner contract, bounded native observations and sanitized results. |
| Existing namespace | Preserve `__init__.py`, `contracts.py`, `evaluate.py`, `harness.py` and Plan 12.5’s fixtures/tests. No changes are planned to those files; probe records do not depend on their grader/contracts. |
| Config | `ProbeConfig` binds source/environment/config hash, authorization reference, synthetic fixture, endpoints, resource/time/download limits and predeclared numeric targets. Redis requires explicit `redis.endpoint` and released container/port/volume identity. Pytest reads the path from `OPTIMUS_PLAN12_PROBE_CONFIG`; no generic Redis default. Credential references only. |
| Result/evidence | `ProbeResult` carries attempt/run IDs, UTC times, source/config/platform/package/service identities, observations/counters/artifact hashes, outcome, capability scope, limitations, owner and closure disposition. Keep execution outcome separate from administrative disposition. Proposed outputs: `reports/plan12-memory-feasibility/{manifest,probe-config,qualification,handoffs}.json`, independent attempt records and sanitized Markdown report. |
| Tests | Create `tests/unit/tools/test_plan12_memory_probes.py` and `tests/integration/tools/test_plan12_memory_redis_probe.py`. The live Redis file uses only `requires_plan12_probe_redis`, never shared `requires_redis`. Extend `tests/unit/tools/test_run_context.py` for marker/default-admission controls. |
| Marker/selection | Modify `pyproject.toml` addopts/markers and `tools/testing/run_context.py` `EXCLUDED_BY_DEFAULT` together. Preserve equality enforced by the guardrail test and existing profile selection behavior. |
| Establishing-import inventory | If any new runtime module enters the establishing-import closure, update `tools/probe_p11_zed_session_load.py`’s closure list and the corresponding HEAD-keyed pin/control in `tests/unit/tools/test_probe_p11_zed_session_load.py`. Standalone probe modules outside that closure do not receive invented entries. |
| Logging-surface inventory | Append every new file/serialization sink to `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`, with a real sanitizer/rationale and named test. Serialize appended JSON with `ensure_ascii=True`; preserve existing entries. |
| Walker/index inventories | Register new filesystem walkers with reasons in `tests/unit/guardrails/test_tracked_file_scanners.py`; repository-truth enumeration uses `tools.tracked_repository_files`. Any new `ls-files` use needs an `_INDEX_LISTINGS` reason in `tests/unit/tools/test_tracked_repository_files.py`. |
| Child/platform inventories | Register new child launches in `tests/unit/tools/run_context_child_sites.json`; update `_REVIEWED_CHEAP_LAUNCHERS` in `tests/unit/tools/test_test_profiles.py` and `tests/profiles.toml` `[parallel].serial` using existing launcher/classification rules. Every test reading `sys.platform` receives the `platform` tag in `tests/profiles.toml`. |
| Filing | This successor, `docs/README.md`, and `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`’s issue-only registry pointer to #391. Issue corrections/labels are separately approved GitHub writes. |
| Deferred probes | No Initializr/graph/L2 implementation here; their probes remain at the starts of M5a/M7/M5b. |

## Review focus

The owning tasks test five likely false claims: endpoint aliases mistaken for isolation; malformed observations mistaken for denial; artifact/stdout leakage despite RAM-only inputs; client rendering mistaken for Optimus integration or confidentiality; and an accepted handoff mistaken for a measured PASS.

## Probe completion and handoff contract

| Probe | Observed result may conclude | If blocked/unreleased/inconclusive: owner and consequence |
|---|---|---|
| P1 packages/parsers | Exact compatible pins/licenses or an observed unsupported combination | Claude, frozen v12 M1 for indexing packages; M3 for encryption dependency. Re-run missing combinations before use; no blanket CPython 3.14 claim. |
| P2 embeddings/worker | Bounded throughput/RAM and cancel/resume/owner-exit behavior | Claude, frozen v12 M1. Keep performance assumptions unqualified and select no unmeasured model/runtime; prototype cursor is not a product worker. |
| P3 Redis K2 | Synthetic single-instance measured pass/fail and provisional fallback choice | Claude, frozen v12 M1. No qualified topology/capacity claim until missing synthetic and real-corpus runs exist; production Gate remains M3. |
| P4 Postgres | Native driver, commit/rollback/reconnect readiness | Claude, frozen v12 M0b. Resolve connection/packaging before ledger integration; no durable-ledger acceptance. |
| P5 client capabilities | Exact version-bound observations for buffers, pre-prompt display, model-independent host cards and nonpersistent-display canaries | Claude, frozen v12 M1 for buffers; M3 for brief/notices/phrase channel. Default to disk context and first-response brief. No qualified confidential display means M3 qualifies the restricted-file fallback or leaves encryption/rotation unavailable. |

A handoff includes source/config, reason, last attempt/status, missing release/resource, named owner/roadmap entry, required follow-up check, fallback and consequences. Claude accepts custody and Codex reviews it at the checkpoint; link an existing issue before proposing a new one, and obtain normal filing authority for writes.

**Closed-with-handoff is not PASS.** Failed observations remain FAIL; missing execution stays UNRUN; ambiguous evidence stays INCONCLUSIVE. Administrative closure is allowed when all probes have observations or accepted custody. Later slices must obtain any necessary missing proof before dependent execution. Runner defects cannot be disguised as external-resource handoffs.

## Dedicated Redis admission rules (R-2)

The load tier is `requires_plan12_probe_redis`. Register and exclude it from default/profile runs, updating the approved run-context exclusion tuple in the same change so default tests remain ACTIVE/guarded. Explicit probe runs use their own fixture. Never borrow `live_redis_store`, `live_redis_telemetry`, shared `run_preflight`, `OPTIMUS_REDIS_URL` or a shared Redis factory.

The fixture requires `OPTIMUS_PLAN12_PROBE_CONFIG` naming a validated config with `redis.endpoint` and separately released resource binding. Missing config/endpoint means a specific prerequisite skip, live result UNRUN and **no client construction/socket call**. An explicitly invalid/protected endpoint is rejected, not silently skipped or defaulted. The standalone runner uses the same admission function.

Before connection, parse/normalize the endpoint, resolve loopback aliases and compare protected endpoints by host/address and port **independent of database number**. Refuse shared/default `redis://127.0.0.1:6379/0`, localhost/IPv6 aliases and every database on that server, including protected `optimus-redis`, plus registered shared-test/product endpoints.

Allow only the released dedicated loopback mapping. Bind its port to the disposable container/image and distinct volume through inspected resource metadata. Missing/ambiguous identity or an alias/proxy to a protected service is refused before load/mutation. A key prefix or different database number is not isolation. Confirm native server identity/config read-only before load; abort on mismatch. Restart tests reconcile the same container/volume rather than adopting a different server because its process run ID changed.

Offline negative controls cover missing config, malformed URLs, shared aliases/alternate databases, unsafe mappings and accidental shared-fixture use; assert no connector invocation. A released dedicated-server positive control provides real-dependency proof. Collection controls establish default/profile exclusion without clearing addopts or weakening guards.

## Task 0 — Establish each probe’s attainable scope

**Consumes:** pinned source, authority and machine inventory. **Produces:** independent prerequisite/release/config rows and test context. Read-only preparation does not release implementation.

- [ ] Recheck branch/HEAD/status, current-main drift, overlap, #391 and existing issue ownership. Record exact tooling/environment identities and resolve every unknown prerequisite before its dependent task. Absorb in-scope blockers as tasks here; preserve the explicit #447 exception.
- [ ] Obtain the operator’s exact-v3-hash approval before Task 1. Record separate releases for live operations and GitHub/publication actions; prepare filing/corrective-comment content for this plan’s PR.
- [ ] Fix per-probe endpoints, elapsed-time/RAM/disk/download limits, permitted public egress and disposable resource IDs. Inventory dedicated Redis/Postgres images and client ceremony without starting them. Paid-call limit is zero.
- [ ] **Before any qualifying Redis run**, declare numeric synthetic item/vector counts, dimensions/bytes, concurrency, logical `maxmemory`/admission reserve, physical RAM, disk, acknowledgement/projection latency, restart-to-usable deadline, and logical-purge/physical-erasure deadlines. Review these before execution. A separately released exploratory run may inform them but never becomes the qualifying run. No retrospective target change turns failure green.
- [ ] Disposition unavailable resources independently. Synthetic probes do not depend on product-policy imports. Any proposed representative workspace sample first requires Plan 12.6’s accepted policy checks and separate source/egress authority; omit that extension without holding this synthetic plan open.

**Verify:** inspect independent prerequisite/release/config rows and target completeness. Expected: no implicit service/network/GUI/paid operation and no unknown silently treated as satisfied.

## Task 1 — Safe runner and attributable records

**Files:** runner/helpers, unit tests, marker configuration and applicable inventories above.  
**Consumes:** approved revision and Task 0 boundaries. **Produces:** bounded runner and standalone result contract. **Checks:** K1 persistence/egress controls and K2/K6 attribution.

- [ ] **Red:** timeout/cancel, missing wheel/resource, hash/license mismatch, forbidden egress, synthetic-secret stdout, raw-body persistence, partial output and malformed native result. Include valid same-view controls. Parser/inspection failure is INCONCLUSIVE, never proof of product denial.
- [ ] **Green:** implement no-work-at-import dispatch, shared Redis admission, resource allowlists, cancellation/cleanup journaling and sanitized output. Prove missing config cannot construct a client and generic Redis variables cannot supply fallback. Keep source/model-buffer bodies in RAM; persist only permitted counters/hashes/observations. Distinguish unavailable, error, fail, inconclusive and unrun.
- [ ] Retain every attempt with source/config/run identity; never overwrite failed qualification. Limit cleanup to released disposable resources. Complete all applicable logging, closure, walker, launch, index and platform inventories with the new code.
- [ ] Test offline with explicit doubles. Prove canonical default selection remains ACTIVE, profiles exclude the live tier, and explicit probe selection cannot inherit shared fixtures. Offline tests cannot produce native-service/client PASS.

**Verify:**

```bash
uv run --no-sync pytest --no-cov tests/unit/tools/test_plan12_memory_probes.py tests/unit/tools/test_run_context.py -q
```

Run affected inventory tests and connection-free collection controls. Expected: attributable controls, unchanged default protection and no leaked secret/body.

## Checkpoint 1 — Safe-probe release

Codex reviews runner controls, dedicated-resource admission, predeclared targets, per-operation boundaries, repository inventories and handoff schema. Resolve safety blockers before dependent live work. Focused offline checks suffice; no full suite is scheduled here.

Codex acceptance is the review verdict. The operator separately releases each live operation. One probe’s release does not release the others; an unreleased probe may receive accepted custody while released probes proceed.

## Task 2 — Packages, parsers, embeddings and worker feasibility (P1/P2)

**Files:** runner package/worker helpers, unit tests and independent P1/P2 records.  
**Consumes:** only released packages/models. **Produces:** measured compatibility/execution matrix. **Checks:** K2 inputs and K1 artifact constraints.

- [ ] Record Plan 12.6’s qualified **`pathspec==1.1.1`, MPL-2.0, pure Python, direct dependency**, as an input under ADR-031. Extend its wider compatibility matrix; do not re-select or upgrade the parser.
- [ ] Inventory RedisVL, tree-sitter/per-language grammar wheels, rustworkx, graspologic-native, optional cryptography and proposed embedding driver/model. Record exact distributions/versions/hashes/licenses/native prerequisites and Windows CPython 3.14 status. Exclude noncommercial weights; runtime pulling alone does not make a copyleft server license a blocker. No automatic grammar/model download or new agent framework.
- [ ] Parse/embed a finite synthetic corpus in RAM. Record hardware, dimensions/chunking, wall time, peak RAM, throughput, output identity and limits. Missing download/model release means UNRUN throughput, not zero or “supported.”
- [ ] Exercise cancel/resume of a synthetic cursor and owner exit/restart. This informs an in-process resumable worker; it does not implement persisted-generation production indexing.
- [ ] Close P1/P2 separately, retaining partial matrices and owned missing combinations. Do not promote every candidate into product dependencies; use isolated candidate environments and only approved exact pins.

**Verify:** focused offline tests, then released commands:

```bash
uv run --no-sync python -m tools.plan12_memory.probes --kind packages --config reports/plan12-memory-feasibility/probe-config.json
uv run --no-sync python -m tools.plan12_memory.probes --kind embedding --config reports/plan12-memory-feasibility/probe-config.json
```

Expected: source-bound observations or explicit handoff, without broad compatibility/performance claims.

## Task 3 — Synthetic real Redis K2 (P3)

**Files:** Redis helper and dedicated integration test.  
**Consumes:** its released dedicated Redis and predeclared numeric config, independently of P1/P2 completion. **Produces:** synthetic capacity/recovery result or handoff. **Checks:** K2 feasibility only.

- [ ] Apply R-2 before client creation. Verify explicit config, inspected container/image/port/volume, distinct ACL, Redis 8.4+ Search/JSON/TimeSeries, `noeviction`, AOF and redis-py APIs. `redis>=5` is already a runtime dependency; record the actual installed version. Never connect to protected/shared fixtures or data.
- [ ] Use bounded synthetic vectors/events/JSON projections, a rebuild burst and derived-growth pressure. Test same-connection append then `WAITAOF 1 0 <timeout>`, returned count, slow persistence, acknowledgement/projection latency, AOF rewrite/RDB save, restart-to-usable, logical purge and physical-erasure horizon.
- [ ] Measure logical `used_memory - mem_not_counted_for_evict`, physical process/container RAM including copy-on-write peaks, and disk separately. Label reserve as reserve; include vector counts/dimensions and index/persistence bytes. Do not infer memory from LOC.
- [ ] Compare with preregistered bounds. A failed single-instance result selects the two-instance fallback/design change. Qualify it only if separately released; otherwise hand the missing run and consequence to M1. Preserve the original failure.
- [ ] Label topology provisional: M1 repeats K2 on real corpus/production adapters; M3 proves the actual Gate, notices, fsync and erasure workflow. Prototype append does not establish production atomicity or save notification.

**Verify:**

```bash
uv run --no-sync pytest --no-cov -m requires_plan12_probe_redis tests/integration/tools/test_plan12_memory_redis_probe.py -q
```

Require `OPTIMUS_PLAN12_PROBE_CONFIG` bound to the released instance. Preserve other pytest/run-context settings. Missing config skips as UNRUN before connection; protected endpoints fail admission without shared access. Explicit-marker evidence is separate from ACTIVE default-suite protection.

## Task 4 — Isolated Postgres readiness (P4)

**Files:** runner Postgres helpers, offline tests and independent P4 record.  
**Consumes:** its separately released loopback database and installed driver. **Produces:** packaging/connectivity/transaction observations. **Checks:** K3 readiness only.

- [ ] Reuse the Docker identity, loopback mapping and disposable lifecycle pattern in `tests/integration/evidence_handoff/test_docker_lifecycle.py`, **never its database, credentials, volume or data**. Record exact driver/server/image/resource identities. Use installed psycopg; absence of `psql` is not a blocker.
- [ ] Observe commit/readback, rollback, disconnect/reconnect and failure behavior with synthetic rows and positive controls. Add no cost ledger/outbox or accounting calculation.
- [ ] Record packaging/connectivity requirements and conclude or hand off to M0b independently of Redis/Zed.

**Verify, only after its release:**

```bash
uv run --no-sync python -m tools.plan12_memory.probes --kind postgres --config reports/plan12-memory-feasibility/probe-config.json
```

Expected: attributable native readiness observations, without ledger durability/completeness claims.

## Task 5 — Version-bound ACP/Zed capabilities (P5)

**Files:** client helper, offline controls and P5-a–d records.  
**Consumes:** separately released client/workspace/trust/manual ceremony. **Produces:** four independently dispositioned observations. **Checks:** K6; informs M1 buffers and M3 brief/notices/recovery.

- [ ] Record exact Zed/ACP/acpx/reference-agent versions and launch requirements. Use a disposable trusted synthetic workspace and isolated client state, never personal buffers or an existing paid session. Canaries are synthetic; never generate/show a real recovery phrase.
- [ ] **P5-a — buffer access:** inspect advertised `fs.readTextFile`; invoke `fs/read_text_file` only when advertised. Compare unsaved synthetic buffer and disk in RAM. Distinguish unsupported, failed call and unrun. Use independently authored acpx for ACP interoperability evidence.
- [ ] **P5-b — welcome-back timing:** observe pre-prompt rendering and first-response fallback. A reference/stub peer may isolate editor rendering, explicitly client-only evidence. Unsupported unsolicited display selects the first-response brief.
- [ ] **P5-c — model-independent notices (N-5):** attempt a synthetic host-generated ACP tool-call/update card through the actual Optimus outbound path, without a model turn or Gateway/provider request. Record creation/update IDs, rendering and delivery. Establish zero calls from isolated process/transport observations, not merely a missing ledger row. Use acpx and real Zed for their respective interoperability/rendering claims. Reference-peer cards remain separate client-only controls. Add no ad-hoc production save mechanism; an unattainable zero-call product path is UNRUN with M3 custody. Actual save-to-notice binding remains M3.
- [ ] **P5-d — nonpersistent display (R-1):** test documented/client-supported candidate paths with unique synthetic canaries. Inspect visible history, close/reopen, restart and accessible persisted thread/log/export sinks, including cards. Never delete history or disable logging to manufacture privacy. Name inspected and inaccessible sinks; any unknown sink makes confidentiality INCONCLUSIVE. Rendering or absence from one file is insufficient. Carry a candidate to M3 for explicit acceptance/qualification; otherwise use spec §6.1.1’s restricted-file fallback or leave encryption/rotation unavailable.
- [ ] Unreleased strict preflight/provider access/manual ceremony leaves each dependent observation UNRUN with its prerequisite. No paid call is permitted. Missing P5-c/P5-d proof does not hold other observations or siblings; M1/M3 own integration acceptance.

**Verify:**

```bash
uv run --no-sync python -m tools.plan12_memory.probes --kind zed --config reports/plan12-memory-feasibility/probe-config.json
```

Add actual acpx/editor observations only under their releases. Expected: version-bound scope/status for **each P5-a–d**, no real secrets, zero model/provider calls for P5-c, or accepted owned handoff.

## Checkpoint 2 — Independently disposition all probes and close

- [ ] Produce P1–P5 rows and P5-a–d subrows with observations or accepted named custody. Preserve failures and missing releases; no all-probes-PASS condition.
- [ ] Resolve runner/in-scope blockers with targeted checks, finish repository inventories, and obtain one consolidated Codex CLI review. Use Fable only for genuinely complex points at Claude’s judgment.
- [ ] Complete final verification below. Record Redis admission/default exclusion, provisional topology, per-capability fallbacks and unqualified assumptions for M0b/M1/M3. Identify unproved production K1–K6 subsets.
- [ ] Preserve former Task 7 acceptance content at the starts of M5a/M7/M5b, per spec §8.1; none was executed or required here.
- [ ] Audit current-state documentation before the closing commit and again before merge: README, roadmap, docs/decision indexes, transitional registry and linked owning issues. Correct mutable claims in this PR; preserve frozen predecessors.
- [ ] Under explicit publication/GitHub authority, record the actual PR/CI/merge evidence and deliberately close #391 with all handoffs and limitations. Use **“Refs #391”** in PR wording; merge alone does not establish probe acceptance or issue closure.

**Closure:** accepted runner/tools, own tests/inventories, both checkpoints, final Windows evidence, Linux PR CI, and observed or accepted-custody disposition for every probe. #447 remains an explicitly disclosed baseline exception. Runner defects are not handoffs; administrative closure is not production acceptance.

## Verification and final review evidence

Record absolute checkout, branch, source HEAD/tree or provisional dirty-diff hash, interpreter/environment/configuration identities, run IDs, platform, exact commands, retained output and exit status. Record HEAD/status before and after measured runs. Preserve normal selection/root conftest, emitted mode/reason, guard/native validity, skips and incomplete records.

Run applicable inventory checks with focused tests before the final code freeze:

```bash
uv run --no-sync pytest --no-cov tests/unit/tools/test_verify_plan996_logging_surfaces.py tests/unit/guardrails/test_tracked_file_scanners.py tests/unit/tools/test_tracked_repository_files.py tests/unit/tools/test_run_context_child_sites.py tests/unit/tools/test_test_profiles.py -q
uv run --no-sync pytest --no-cov tests/unit/docs/test_docs_index.py tests/unit/docs/test_plan_directory_hygiene.py tests/unit/docs/test_open_work_pool_hygiene.py -q
```

Include the establishing-import closure check if that closure changes. Run existing Plan 12.5 evaluation/harness tests if shared namespace changes could affect them.

After focused fix cycles, run **exactly one Windows full suite with coverage on the final code head**, validate its export, and run Ruff:

```bash
uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
uv run --no-sync ruff check .
```

Apply canonical product floors, the 80% aggregate production-code requirement and safety-critical no-regression rule. Preserve the tools’ actual verdicts and precision; do not infer validity from pytest’s exit code or rounded totals. Missing/invalid coverage artifacts remain missing/invalid.

**Known baseline exception — [#447](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/447):** four Windows failures in `tests/unit/acp/test_plan1126_delivery_contract.py` are outside this plan:

- `test_delivery_contract_model_1000_seed_schedule`
- `test_h4_execution_emits_only_citations_for_behaviors_it_runs`
- `test_h4_literal_scenarios_are_coherent_primary_transitions`
- `test_h4_behavioral_mutations_change_or_invalidate_primary_observation`

Final evidence names their full node IDs, observed reasons and actual suite exit status. Do not deselect, xfail, edit pins or label the suite green to conceal them. Distinguish these baseline failures from new regressions and report coverage/validity independently.

**Linux PR CI is the second full run.** Bind it to the actual candidate SHA and retain its skips/results separately. Use WSL only to investigate non-trivial CI failures; infer no Windows parity from Linux success.

A code change after the Windows run invalidates final-code-head attribution. Preserve the run, disclose the exact delta and obtain operator disposition before any extra full run or acceptance of the changed bytes. Never silently rerun or relabel earlier evidence.

The final handoff contains sanitized source/config-bound manifests, every attempt/status, reviewer responses, requirement-to-check mapping, custody/exception owners and full hashes of the reviewed spec and saved plan. Archive/hash required evidence before temporary retention or cleanup can prune it. Private artifacts and memory are not project dependencies.

## Explicit exceptions and custody

| Outside this plan | Named owner and consequence |
|---|---|
| #385, shared file policy, project registry and architecture ADR | Delivered by Plan 12.6 / #390, including #385, through PR #446 (`efa1235`); ADR-031 accepted through PR #448. No reimplementation or direct probe-record imports. |
| Golden cases, grader and generic-harness selection | Delivered by Plan 12.5 / #389 through PR #444; native generic-harness/model campaign remains #248. |
| Former Task 7 Initializr | Start of frozen v12 M5a: timeout/unavailable and nonexistent-coordinate controls, public dated/hashed metadata, generated-POM/BOM import, authoritative fallback; no build/private upload. |
| Former Task 7 bounded graph | Start of frozen v12 M7: bounded G1′ extraction/traversal versus G0 over synthetic Java/Python modules, new/renamed caller invalidation, malformed/stale hash controls; file/node/time limits, no LLM extraction. |
| Former Task 7 L2 | Start of frozen v12 M5b: installed JVM/LSP/runtime availability, bounded resolution and missing-runtime controls; no automatic downloads. |
| Production ledger/outbox/Gateway copy and retention | Frozen v12 M0b; #303 retains broad telemetry scope. P4 cannot close these checks. |
| Production index/worker and real-corpus topology | Frozen v12 M1/M2; P1–P3 handoffs specify missing prerequisites and consequences. |
| Gate, notices, continuity, keys, backup/restore/purge/rotation | Frozen v12 M3, including native keystore deletion and K5-R1/R2; learning/archive remains M6. |
| Dependency/Q&A products; C3/C4 | Frozen v12 M5a/M5b/M7; only former Task 7 probe timing changed. |
| Savings UI, paid runs, session load, picker, Q27 | #248/OC-4, Plan 11.7/#240, model-selection work and separate diagnostics hardening respectively. |
| Four pre-existing Windows delivery-contract failures | #447; report unchanged baseline failures explicitly. No repair, suppression or green-suite claim here. |
| Service creation/deletion, real keyring/GUI, publication and cleanup | Separate bounded operator release; plan closure grants no destructive or external-write authority. |

**Authoring checks:** pinned predecessor/spec hashes, source, inventories and owning issues inspected read-only; no tests, implementation, downloads or service/GUI operations performed in Round 83.  
**Remaining risk:** live releases and measurements are pending; accepted handoffs qualify no unmeasured capability.

