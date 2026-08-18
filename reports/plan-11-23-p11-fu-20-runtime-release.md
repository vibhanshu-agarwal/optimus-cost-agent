# Plan 11.23 — Client-MCP Runtime Interim Release Review

**Implementation commit reviewed:** `80a4ea3` (`test: prove client MCP runtime composition`)

## Interim disposition

The Plan 11.23 **code/state prerequisite is satisfied**: Tasks 1–4 supply
the production discovery-to-composition path end to end, and the recorded
hermetic real-object evidence passed. This is not a closure decision for
`P11-FU-20`.

`P11-FU-20` remains open. Task 6 separately owns the independently authored
ACP/write-server, live Redis/TimeSeries, Gateway-authority, TTY ceremony, and
potentially paid-call evidence required for closure. None of those external
prerequisites was exercised or inferred here.

The Task 4 evidence at the reviewed commit records:

- the eight-file hermetic set: `173 passed in 5.66s`;
- full coverage: `3254 passed, 28 skipped, 111 deselected, 1 warning`;
- `coverage report --fail-under=80`: `82% coverage`, exit 0;
- `uv run --frozen ruff check .`: `All checks passed!`; and
- real-object lazy composition, guard-before-dispatch, and exactly-once
  connection teardown evidence.

## Source-anchor review

The following documented WP-4 searches were rerun against `src/**/*.py` at
`80a4ea3`. Their exact results replace the drafting-time absence observations
only as source evidence; they do not substitute for Task 6 live evidence.

| Claim | Exact command | Exact result | Classification |
| --- | --- | --- | --- |
| Production adapter constructor | `rg -n --glob '*.py' 'ClientMcpSdkAdapter\(' src` | `src\\optimus\\acp\\bootstrap.py:207:    sdk_adapter = ClientMcpSdkAdapter(` | Present source anchor: bootstrap constructs the owned adapter. |
| Concrete service | `rg -n --glob '*.py' 'class .+\(ClientMcpToolService\)' src` | `src\\optimus\\mcp\\client_catalog.py:636:class AdapterBackedClientMcpToolService(ClientMcpToolService):` | Present source anchor: the concrete adapter-backed dispatch service exists. |
| Materialization caller | `rg -n --glob '*.py' 'materialize_tool_service\(' src` | `src\\optimus\\mcp\\client_disposition.py:254:    def materialize_tool_service(`; `src\\optimus\\mcp\\client_disposition.py:346:            service = self.materialize_tool_service(` | Present source anchor: line 254 is the definition and line 346 is the production lazy-resolver caller. |
| Catalog construction | `rg -n --glob '*.py' 'ClientMcpDescriptorExposureAdapter\(\)\.build' src` | `src\\optimus\\mcp\\client_disposition.py:279:            catalog = ClientMcpDescriptorExposureAdapter().build(` | Present source anchor: materialization builds the admitted catalog. |
| Registry registration | `rg -n --glob '*.py' 'state\.tool_service\.register\(' src` | `src\\optimus\\mcp\\client_disposition.py:302:        state.tool_service.register(service)` | Present source anchor: materialization registers the concrete service in the session registry. |

No command above returned zero matches. Had one done so, this report would have
classified it solely as absence evidence rather than inferring a missing
runtime path.

Source inspection of the matched resolver confirms the composition order:
`sdk_adapter.open(...)`, `sdk_adapter.discover(...)`, concrete service
factory creation, `materialize_tool_service(...)`, session registration, and
an owned adapter close hook. Failure unregisters any service and closes the
opened connection.

## Current-state documentation audit

Audit scope was limited to `README.md`,
`docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, and
`docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`.

Exact command:

```powershell
rg -n -i -e 'P11-FU-20' -e 'ClientMcpToolService' -e 'one-call' -e 'client MCP' README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
```

`README.md` and the Phase 1 roadmap returned zero matches. Every match was in
the consolidated deferred backlog and is classified below.

| Lines | Matches | Classification and disposition |
| --- | --- | --- |
| 170 | `P11-FU-20`; `one-call`; `client-MCP` | **Current custody index.** Its “production composition not yet wired” wording is superseded by the source anchors above, but the pool remains unchanged: this task does not authorize a closure or a status edit. |
| 1436 | `P11-FU-20`; `one-call` | **Current custody heading.** The entry remains the live owner. |
| 1444–1465 | `one-call`; `ClientMcpToolService` | **Frozen historical provenance.** These describe the original P11-FU-9 gap and acceptance criteria, including frozen-plan boundaries; they are not a claim that Task 6 has passed. |
| 1478–1482 | `P11-FU-20`; `one-call` | **Current interim status.** The stated unrun live tier remains true; its prior “production composition not yet wired” subclaim is now historical/stale but must not be changed in this Task 5 package. |
| 1483–1484 | evidence links; `P11-FU-20` | **Evidence and frozen provenance.** The Plan 11.20 release/evidence links are historical evidence; the frozen P11-FU-9 Task 6 reference cannot establish this item’s closure. |

No README or roadmap claim requires amendment in this interim package. No frozen
artifact was modified, and the consolidated pool status remains unchanged.

## External prerequisite custody

The code/state prerequisite changed from unsatisfied at plan drafting to
**satisfied** by Tasks 1–4 and the recorded hermetic evidence. The remaining
external prerequisites are still outstanding and owned as follows:

| Prerequisite | Status | Owner / disposition |
| --- | --- | --- |
| Redis with TimeSeries reachable for the real ACP process | unknown until Task 6 preflight | Operator; Task 6 must establish it before a live claim. |
| Independently authored write-capable MCP server | unsatisfied | Operator with Task 6 selection record; genuinely hard external dependency. |
| Billing-enabled Optimus Gateway credentials and authority | unsatisfied | Operator; genuinely hard external authority. |
| Identity-matching durable `side_effect_eligible` record via real TTY | unsatisfied | Operator; merely unauthorized interactive ceremony. |
| Paid Gateway model-turn approval | unsatisfied | Operator; genuinely hard cost authority. |
| Independently authored `acpx` execution | installed but not run here | Operator; merely unauthorized in this package. |

Task 6, its E2E/marker work, live systems, Redis, Gateway, `acpx`, paid call,
and TTY ceremony were not started.
