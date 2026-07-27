# Plan 11.2 (P11-FEAT-GATEWAY-TOOLS) — Task 6 Staging §9D Evidence

- **Date:** 2026-07-27
- **Branch:** `agent/cursor/plan-11-2-gateway-tools`
- **Implementation SHA (worktree HEAD):** `3a9e9050fd7267f1a7ca6aaa5cb4d0ded588993c`
- **Gateway environment class:** local staging process on loopback (`http://127.0.0.1:8765`), real provider adapters (Tavily / PyPI / OSV), real Redis-backed tool state, credentials from agent one-key surface only (`OPTIMUS_GATEWAY_URL` + `OPTIMUS_API_KEY`)
- **Command:**
  ```
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_tools_live.py -m requires_gateway -q
  ```
- **Result:** `7 passed, 7 deselected in 2.58s`

## What this evidence proves

`tests/integration/optimus_gateway/test_gateway_tools_live.py` Task 6 cases talk to an
already-running Optimus Gateway over real HTTP. They do **not** start an in-process
server and do **not** inject provider doubles. Requests are formed from
`OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` only (with optional `.env` fallback for those
two names). Provider keys stay on the Gateway side.

This is distinct from Task 4's local-process artifact
(`reports/plan-11-2-gateway-tools-local-process-evidence.md`), which used injected
deterministic providers inside the test process.

## Policy denials (Step 1)

| Scenario | Test | Status | `rule_id` | Sample `gateway_request_id` |
|---|---|---|---|---|
| Blocked domain search (`allowed_domains=["evil.example"]`) | `test_staging_blocked_domain_search_is_denied` | 403 | `EMPTY_DOMAIN_INTERSECTION` | `gw-tool-4ba3a4c019dd4721a326dca041391786` |
| Extract URL not in prior search for `run_id` | `test_staging_extract_without_prior_search_is_denied` | 403 | `URL_NOT_IN_SEARCH_PROVENANCE` | `gw-tool-5964496c2d354b11959f30e2324c9e2a` |
| Web search with `PACKAGE_VERSION` reason | `test_staging_web_search_rejects_package_or_advisory_reason[PACKAGE_VERSION-package]` | 403 | `POLICY_SIGNAL_MISMATCH` | `gw-tool-7ddb8ce595e0459fa1ed2dd6477260b0` |
| Web search with `SECURITY_ADVISORY` reason | `test_staging_web_search_rejects_package_or_advisory_reason[SECURITY_ADVISORY-advisory]` | 403 | `POLICY_SIGNAL_MISMATCH` | `gw-tool-f15409efa6aa4672be129c00259db13a` |
| Call-cap overage on shared `run_id` + package tool class | `test_staging_call_cap_overage_is_denied` | 429 | `CALL_CAP_EXCEEDED` | `gw-tool-b8e2232f6a6e487ba6ec0d018362bee2` |

Call-cap note: Gateway `OPTIMUS_GATEWAY_TOOL_MAX_CALLS_PER_TOOL=5`; the 6th package
lookup on one `run_id` returned 429. Sample overage `run_id`:
`staging-cap-e06b97df009f4610beb1fe4a3de5a878`.

Wrong-signal note: package/advisory HTTP routes hardcode their policy signals, so the
Gateway-visible wrong-signal proof for those families is attempting web search with
package/advisory evidence reasons (`POLICY_SIGNAL_MISMATCH`).

## Success paths (Step 2)

| Scenario | Test | Status | Sanitized summary | Sample `gateway_request_id` |
|---|---|---|---|---|
| Package lookup (`pytest` / `pypi`) | `test_staging_package_lookup_success_path` | 200 | `tool_class=package_and_advisory_metadata`, `policy_signal=DEPENDENCY_VERSION_CHECK`, `latest_version=9.1.1`, 1 HTTPS citation, `gateway_usage.provider=pypi`, `billing_units=0`, `cost_usd=0` | `gw-tool-5bff3e1341844118abe43f0fad5a4cdb` |
| Security advisory (`pytest` / `pypi`) | `test_staging_security_advisory_success_path` | 200 | `tool_class=package_and_advisory_metadata`, `policy_signal=SECURITY_OR_CVE_CHECK`, 2 advisories (`GHSA-6w46-j5rx-g56g`, `PYSEC-2026-1845`), HTTPS citations only, `gateway_usage.provider=osv`, `billing_units=0`, `cost_usd=0` | `gw-tool-0d46f142544044afa90b420c1e470199` |

Provider label note: the real `PackageRegistryToolProvider` reports usage provider as
the registry backend (`pypi` / `npm` / `maven`). Task 4's local-process fake used the
stand-in label `package-registry`; staging asserts the real backend label.

## One-key credential boundary

Staging tests resolve only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` for the HTTP
client. No Tavily / OSV / registry keys are read by the test process when forming
requests. Provider credentials remain Gateway-owned via `.env.gateway` projected into
the Gateway child process.

## Sanitization

Evidence capture and test assertions use status codes, `rule_id`, structured error
text already returned by the Gateway, public package/advisory identifiers, HTTPS
citation presence, and `gateway_usage` fields. Raw provider response bodies, API keys,
and Redis internals are not written into this report.
