# Plan 11.16 deadline-seam release

**Date:** 2026-08-15
**Branch:** `agent/cursor/plan-11-16-deadline-seams`
**Implementation SHA for P11-FU-19 evidence:** `6159200137b76198307591f7496ed83046af45ab`

## Outcome

| Lane | Pool status | Reason |
|---|---|---|
| `P11-FU-7` | **Still scheduled** (Promoted -> Plan 11.16) | Test clock removed; 25 full Windows `--cov` gate stopped at 4/25 on unrelated `P11-FU-6` WinError 10053. Not Closed. |
| `P11-FU-19` | **Closed** | Production one-deadline helper; Windows full `--cov` green; native WSL ext4 200/200 standalone selectors. |

Lanes were not cross-credited.

## Claim-to-evidence

| Claim | Required evidence | Result |
|---|---|---|
| P11-FU-7 is test-side only | `server.py` no-diff, retained assertions, 25 Windows coverage logs | `git diff -- src/optimus/acp/server.py` empty. Sanitization assertions retained. 25-run gate **not complete** (4 clean + 1 unrelated stop). |
| P11-FU-7 did not widen a clock | captured deterministic red and finite-EOF test diff | Red: `TimeoutError` from `wait_for(..., timeout=1)` after cancellation-resistant 1.1s injector. Diff: two `await serve_ndjson(...)` wrappers, no timeout. |
| P11-FU-19 is production code | four `client_sdk.py` entries and controlled real-adapter starvation red/green | `_submit_operation` used by `open`, `discover`, `call`, `read_streamed_bytes_for_tests`. Red: `MCPSupervisorError("SUBMIT_TIMEOUT")` under loop starvation. Green: `ClientMcpSdkError("OPERATION_TIMEOUT")`. |
| SDK expiry never exposes `SUBMIT_TIMEOUT` | open/discover/call/stream tests | `test_operation_deadline_is_enforced`, `test_discover_over_budget_is_operation_timeout`, `test_call_over_budget_is_operation_timeout`, `test_stream_over_budget_is_operation_timeout`. |
| Generic supervisor remains bounded | direct `submit(..., timeout_seconds=0.2)` test | `test_submit_times_out_and_cancels_slow_coroutine` unchanged. |
| P11-FU-19 is not load-dependent | 200 standalone WSL results and separately reported full-unit run | Native `/root/src/optimus-cost-agent`, `/usr/bin/git`, ext4, 200/200, then 3059 passed / 13 skipped unit. |
| Entries close independently | separate pool detail/report links | FU-19 Closed citing only FU-19 reports. FU-7 Promoted citing only FU-7 residual report. |

## Unrun / residual

- `tests/integration/mcp/test_client_sdk_real.py` (`requires_mcp_http`): marker skip / deselected. **Unrun, not a pass.** Independently authored live client-MCP HTTP tier is not discharged.
- P11-FU-7 25× `pytest --cov -q`: **4/25 clean, 21 unrun** after run 5 `P11-FU-6` WinError 10053. Isolated/non-coverage runs were not substituted.
- P11-FU-7 remains the named open owner of the NDJSON coverage-timing row.

## Freshness audit

README, roadmap, Plan 11 charter, and `docs/runbooks/local-live-dependencies.md` do not carry live P11-FU-7 / P11-FU-19 status. Frozen Plan 11.16 plan bytes and historical `reports/plan-11-flake-triage.md` were not edited.

## Fitness at close

Windows full `--cov` at `6159200`: 3142 passed, 28 skipped, 110 deselected, **81.66%**.
WSL `tests/unit`: 3059 passed, 13 skipped. `ruff check .` clean.
