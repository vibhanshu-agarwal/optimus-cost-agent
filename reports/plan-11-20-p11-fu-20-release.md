# Plan 11.20 P11-FU-20 release

**Date:** 2026-08-18  
**Branch:** `agent/cursor/plan-11-20-client-mcp-one-call`  
**Implementation SHA:** `d7183849a27644f06bd8e554fe09187e16d3bbc3`

## Outcome

| Lane | Pool status | Reason |
|---|---|---|
| `P11-FU-20` | **Promoted / Open** (not Closed) | Unit adapter wiring complete at `d718384`. Seam built and unit-tested; production composition not yet wired. Live one-call write-approval tier and `requires_acpx` session capture remain **unrun**. |

## Claim-to-evidence

| Claim | Required evidence | Result |
|---|---|---|
| P11-FU-20 has independent scheduled/closure custody | Task 0/5 pool hygiene and P11-FU-20-only report links | Pool row remains `Promoted -> Plan 11.20`; hygiene test `test_plan_1120_p11_fu_20_scheduled_custody_rejects_p11_fu_9_task_6_closure` **passed** |
| `session/new` never opens MCP transport | Task 2 controlled probe across allow/reject/timeout/unavailable branches | `test_valid_entry_requests_safe_approval_without_opening_transport`; `test_allow_once_stays_transport_free_until_lazy_materialization_registers` — unit **passed** |
| Matching service is real, per-server, session-isolated | Task 2 real state/registry composition tests | `test_two_sessions_and_two_servers_do_not_cross_consume`; `test_unavailable_and_budget_failure_register_nothing` — unit **passed** |
| ACP cannot fabricate an unbound approval | Task 3 actual adapter closure plus no-authorizer `None` test | `test_spec_mcp_broker_issue_fails_closed_until_catalog_authorizer_attached`; `test_session_registry_issuance_returns_none_without_creating_token` — unit **passed** |
| Token is bound and one-call-only | Task 1/3 real authorizer digest, mismatch, replay assertions | `test_session_registry_issues_bound_one_call_approval`; `test_session_registry_issued_token_is_consumed_once_by_service_guard`; spec allow-once → `PreToolGuard` ALLOW / replay not ALLOW — unit **passed** |
| `PreToolGuard` remains operation-entry authority | Task 1/3 service-call assertions and unchanged guard branch | Service builds `PreToolRequest` and invokes `PreToolGuard.check()` before dispatch — unit **passed** |
| ACP/protocol claim does not rest on a project-authored client | Task 4 `acpx` run or explicit unrun disposition | **Unrun** — `test_empty_mcp_servers_array_is_exact_noop_via_acpx` skipped (`acpx_capture_incomplete`); harness greens do not discharge |
| No safety or documentation regression | Task 5 focused suite, coverage, Ruff, diff check, frozen committed-blob digest, freshness audit | Focused suite green; coverage ≥ 80%; Ruff clean; frozen P11-FU-9 digest unchanged |

## Unrun / residual

- **Production composition:** seam built and unit-tested; production composition not yet wired. `materialize_tool_service` is the only `.register()` site and has no production caller, so `_tool_service` still never receives a service in real operation. A live one-call run could not succeed until that composition exists.
- **Live one-call write-approval tier:** not present in live files; would require Gateway credentials, trust ceremony, and a write-capable independently authored client-MCP path. **Unrun, not a pass.**
- **`requires_acpx` live session capture:** `tests/e2e/test_client_mcp_acpx.py::test_empty_mcp_servers_array_is_exact_noop_via_acpx` — skip `acpx_capture_incomplete exit=1 stop=None`. **Unrun.**
- **`requires_mcp_stdio` catalog pass:** `test_terraform_stdio_catalog_distributions_and_negotiation` passed (catalog/negotiation only; tokenized write=0). This is **not** one-call binding or `PreToolGuard` consumption evidence.
- Default `pyproject.toml` addopts deselect `requires_acpx`, `e2e`, and `requires_mcp_stdio` — 5 deselected under default collection (unrun).

## Freshness audit

Searched `README.md`, `docs`, and `reports` for `P11-FU-20`, `one-call`, `ClientMcpOneCallApproval`, `mcp.client.one_call_unknown`, and `Plan 11.20`.

| Location | Classification | Action |
|---|---|---|
| `README.md` | No live P11-FU-20 status claims | No edit |
| `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` | No P11-FU-20 references | No edit |
| `docs/superpowers/plans/2026-08-06-p11-fu-9-*.md` | Frozen P11-FU-9 provenance | Not edited |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Living pool | Updated index Evidence column and detail residual with release/evidence links; status remains Promoted |
| `reports/plan-11-20-p11-fu-20-*.md` | Task evidence artifacts | Created/retained |
| Historical one-call references in other plans/specs | Frozen provenance | Not edited |

## Fitness at release

Focused suite (Task 5 Step 3): unit docs/MCP/ACP/guardrails nodes green.  
Full `coverage run -m pytest` with `--fail-under=80` recorded at commit time.  
`ruff check .` clean. `git diff --check` clean.  
Frozen P11-FU-9 plan digest verified from committed blob (`git cat-file blob HEAD:docs/superpowers/plans/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-implementation.md`).

## Sanitized artifact locations

| Artifact | Role |
|---|---|
| `reports/plan-11-20-p11-fu-20-release.md` | This release disposition (Task 5) |
| `reports/plan-11-20-p11-fu-20-evidence.md` | Task 4 real-dependency disposition |
| `reports/plan-11-20-p11-fu-20-baseline.md` | Task 0 baseline |
