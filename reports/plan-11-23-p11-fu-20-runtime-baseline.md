# Plan 11.23 — Client-MCP Runtime Baseline

**Committed base:** `0790956527019b52c0dfed6809c6b9729d4292ed`

**Purpose:** Record the production-composition absence before the Plan 11.23
runtime tasks. This report neither changes nor closes the P11-FU-20 pool row.

## WP-4 negative-existence searches

All commands below were run against `src/**/*.py` at the committed base.

| Claim | Exact search | Result |
|---|---|---|
| No production SDK-adapter construction | `rg -n --glob '*.py' 'ClientMcpSdkAdapter\(' src` | 0 matches |
| No concrete production `ClientMcpToolService` | `rg -n --glob '*.py' 'class .+\(ClientMcpToolService\)' src` | 0 matches |
| No production caller of materialization | `rg -n --glob '*.py' 'materialize_tool_service\(' src` | 1 match, the definition only: `src/optimus/mcp/client_disposition.py:209` |
| Catalog construction remains inside materialization | `rg -n --glob '*.py' 'ClientMcpDescriptorExposureAdapter\(\)\.build' src` | 1 match: `src/optimus/mcp/client_disposition.py:234` |
| Session-service registration remains inside materialization | `rg -n --glob '*.py' 'state\.tool_service\.register\(' src` | 1 match: `src/optimus/mcp/client_disposition.py:254` |
| No live ACP one-call test drives the relevant sequence | `rg -n -i 'session/new|session/request_permission|mcp_call|allow_once|issue_one_call_approval' tests/e2e tests/integration/mcp` | 0 matches |

## Baseline behavior contracts

- `test_allow_once_stays_transport_free_until_lazy_materialization_registers`
  verifies the existing zero-open `session/new`/disposition boundary before explicit
  materialization.
- `test_spec_mcp_broker_issue_fails_closed_until_catalog_authorizer_attached`
  verifies the existing fail-closed ACP broker before a catalog authorizer is registered.
- `test_leased_server_static_list_lazily_admits_catalog` is intentionally RED on this
  base: the actual session-scoped `ClientMcpSessionService` returns
  `unavailable:unknown_server` for a leased server because no production resolver reaches
  open, discovery, catalog admission, and registration. It controls only the real
  `ClientMcpSdkAdapter` remote edge and requires the first successful static list to record
  exactly `open`, then `discover`.

P11-FU-20 remains open pending both the runtime implementation and the separately required
real evidence. This baseline does not amend frozen plan/spec artifacts or alter its pool row.
