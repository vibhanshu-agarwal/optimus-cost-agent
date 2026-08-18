# Plan 11.20 P11-FU-20 — Task 4 real-dependency disposition

**Status:** Live one-call write-approval assertion **unrun**. P11-FU-20 remains open (Promoted to Plan 11.20). Do not close.

**Date:** 2026-08-18

**Implementation SHA:** `d7183849a27644f06bd8e554fe09187e16d3bbc3`  
(`fix: issue client MCP approvals through session authorizers`; branch `agent/cursor/plan-11-20-client-mcp-one-call`)

Content-free only. No credentials, tokens, headers, configuration values, arguments, transcript bodies, env values, or binary paths.

## Presence (booleans only)

| Dependency | Present |
|---|---|
| Independently authored `acpx` on PATH | yes (`acpx_version` 0.12.0; `acpx_path_digest` `9922637b8318da4dfe0207e53bc289245c314895e247ab6b5bfde90d14deb44c`) |
| `optimus-agent` | yes |
| `optimus-trust` | yes — **not invoked** (trust ceremony is an operator stop) |
| Docker binary | yes |
| Docker daemon reachable (already running; daemon not started by this task) | yes |
| `OPTIMUS_GATEWAY_URL` | no |
| `OPTIMUS_API_KEY` | no |
| Phoenix / OTLP collector env | no |

Phoenix and Gateway processes were not started. `optimus-trust` was not started.

## Live one-call assertion not added

Existing live files lack a one-call write-approval flow:

- `tests/e2e/test_client_mcp_acpx.py` — empty `mcpServers` capture plus harness verifiers
- `tests/integration/mcp/test_client_mcp_live.py` — digest-pinned Terraform stdio catalog listing / protocol negotiation (tokenized write count 0)

A full live one-call assertion would need independently authored `acpx` to drive `session/new`, a transport allow-once, a guarded write call, a separate one-call allow, and a terminal result, without interactive TTY.

That flow was **not** added because it would require:

1. Gateway credentials (both absent) for a real agent turn that can reach a write tool
2. The `optimus-trust` ceremony (binary present; operator-owned; not started)
3. A write-capable independently authored client-MCP path beyond the current catalog fixture (Terraform tokenized write=0; adding a write server would be new machine-state / Docker work)
4. Or else a project-authored ACP client / fake SDK client — forbidden

Tasks 1–3 remain the real-adapter unit proof (actual `AcpDuplexAdapter`, registry, authorizer, `PreToolGuard`). This report does not substitute a project harness for the live ACP-protocol claim.

Live one-call fields that a passing real-tier run would record were **not observed**:

| Field | Value |
|---|---|
| Client version | `acpx` 0.12.0 (binary present; live capture incomplete) |
| Client path digest | `9922637b8318da4dfe0207e53bc289245c314895e247ab6b5bfde90d14deb44c` |
| Safe server/tool names (one-call write) | none observed |
| Token presence | unobserved (boolean: no) |
| Token consumption | unobserved (boolean: no) |
| Protocol disposition | live capture incomplete (`stop_reason` none) |
| Implementation SHA | `d7183849a27644f06bd8e554fe09187e16d3bbc3` |

## Commands

Default `pyproject.toml` addopts deselect `requires_acpx`, `e2e`, and `requires_mcp_stdio`. Collecting both live files under default addopts: **5 deselected** (unrun).

CLI `-m requires_acpx` / `-m requires_mcp_stdio` **overrode** the addopts `-m` expression on this host (tests collected). Attempted runs still used `-o addopts=` as required so deselection cannot be mistaken for a pass.

### `requires_acpx`

```powershell
uv run --frozen pytest -o addopts= -m requires_acpx tests/e2e/test_client_mcp_acpx.py -q --strict-markers -rs --tb=line
```

**Command result:** 2 passed, 1 skipped in 1.32s. Independently authored `acpx` only; no project ACP client.

| Node | Disposition | Reason |
|---|---|---|
| `test_scratch_ignore_rules_are_in_force_before_acpx_capture` | passed | gitignore/check-ignore harness; not a live session |
| `test_extract_safe_evidence_from_fixture_transcript_does_not_require_live_acpx` | passed | fixture JSONL verifier; not a live session |
| `test_empty_mcp_servers_array_is_exact_noop_via_acpx` | **unrun** | skip `acpx_capture_incomplete exit=1 stop=None` |

Skip/deselection is **unrun**, never a pass. The live ACP session capture is unrun. Harness greens do not discharge P11-FU-20.

### `requires_mcp_stdio`

```powershell
uv run --frozen pytest -o addopts= -m requires_mcp_stdio tests/integration/mcp/test_client_mcp_live.py -q --strict-markers -rs --tb=line
```

**Command result:** 1 passed, 1 deselected in 10.07s.

| Node | Disposition | Reason |
|---|---|---|
| `test_terraform_stdio_catalog_distributions_and_negotiation` | passed | already-present Docker daemon; digest-pinned HashiCorp Terraform MCP catalog; negotiated protocol `2025-11-25`; 9 tools; tokenized write=0 |
| `test_context7_http_catalog_distributions_accept_and_negotiation` | deselected | marker `requires_mcp_http` (not this command); **unrun** here |

This pass is catalog/negotiation only. It is not one-call binding or `PreToolGuard` consumption.

## Claim-to-evidence map

Focused unit mapping (this session, same SHA):

```powershell
uv run --frozen pytest tests/unit/mcp/test_client_catalog.py::test_session_registry_issues_bound_one_call_approval tests/unit/mcp/test_client_catalog.py::test_session_registry_issuance_returns_none_without_creating_token tests/unit/mcp/test_client_catalog.py::test_session_registry_issued_token_is_consumed_once_by_service_guard tests/unit/mcp/test_client_disposition.py::test_allow_once_stays_transport_free_until_lazy_materialization_registers tests/unit/mcp/test_client_disposition.py::test_unavailable_and_budget_failure_register_nothing tests/unit/mcp/test_client_disposition.py::test_two_sessions_and_two_servers_do_not_cross_consume tests/unit/mcp/test_client_disposition.py::test_valid_entry_requests_safe_approval_without_opening_transport tests/unit/acp/test_spec_protocol.py::test_spec_mcp_broker_issue_fails_closed_until_catalog_authorizer_attached -q --tb=line
```

**8 passed** in 0.21s. Unit fakes cannot discharge the live ACP-protocol claim.

| Claim | Focused evidence | Disposition |
|---|---|---|
| Lease then real per-server service registration after lazy materialization | `tests/unit/mcp/test_client_disposition.py::test_allow_once_stays_transport_free_until_lazy_materialization_registers`; `test_unavailable_and_budget_failure_register_nothing`; `test_two_sessions_and_two_servers_do_not_cross_consume` | unit **passed** |
| Fail-closed absence (no registered authorizer / mismatch → no token) | `tests/unit/acp/test_spec_protocol.py::test_spec_mcp_broker_issue_fails_closed_until_catalog_authorizer_attached` (empty state and wrong server `_issue_approval` is `None`); `tests/unit/mcp/test_client_catalog.py::test_session_registry_issuance_returns_none_without_creating_token` | unit **passed** |
| Exact one-call binding and one-call consumption | `tests/unit/mcp/test_client_catalog.py::test_session_registry_issues_bound_one_call_approval`; `test_session_registry_issued_token_is_consumed_once_by_service_guard`; spec node allow-once → real `PreToolGuard` `ALLOW` / `mcp.client.write_one_call_allowed` and replay not `ALLOW` | unit **passed** |
| `session/new` / disposition never opens MCP transport | `tests/unit/mcp/test_client_disposition.py::test_valid_entry_requests_safe_approval_without_opening_transport`; `test_allow_once_stays_transport_free_until_lazy_materialization_registers` | unit **passed** |
| Real-tier ACP one-call (`acpx` session/new → transport allow-once → write → one-call allow → terminal) | not present in live files; not added | **unrun** — Gateway env absent; trust ceremony not started; no write-capable live fixture without new machine-state |
| Independently authored `acpx` live session | `tests/e2e/test_client_mcp_acpx.py::test_empty_mcp_servers_array_is_exact_noop_via_acpx` | **unrun** (skip `acpx_capture_incomplete exit=1 stop=None`) |
| Real stdio catalog (not one-call) | `tests/integration/mcp/test_client_mcp_live.py::test_terraform_stdio_catalog_distributions_and_negotiation` | **passed** (catalog only) |

## Sanitized artifact locations

| Artifact | Role |
|---|---|
| `reports/plan-11-20-p11-fu-20-evidence.md` | This disposition (Task 4) |
| `reports/plan-11-20-p11-fu-20-baseline.md` | Task 0 baseline; P11-FU-20 not Closed |
| `.superpowers/sdd/task-1-report.md` | Registry issuance unit proof |
| `.superpowers/sdd/task-2-report.md` | Lease / lazy registration / zero-open transport unit proof |
| `.superpowers/sdd/task-3-report.md` | Real adapter broker fail-closed + allow → guard unit proof |

No live transcript, `.acpxrc.json`, `mcpServers.json`, or token material was written under `reports/`. Pytest used ephemeral `tmp_path` scratch only.

## Residual (P11-FU-20 stays open)

Named residual for Task 5: **live one-call write-approval tier unrun**, and **`requires_acpx` live session capture unrun** (`acpx_capture_incomplete`). WP-2: do not close P11-FU-20 while either live tier is unrun. Unit adapter wiring at `d718384` is not a substitute for independently authored `acpx` one-call evidence.
