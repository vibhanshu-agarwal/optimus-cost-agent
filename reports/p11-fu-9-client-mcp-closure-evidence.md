# P11-FU-9 closure evidence

**Commit baseline:** `5026b62` (Task 8 tip at kickoff; update on close if HEAD advances).
**Platforms:** verified on native Windows (authoritative platform) + reproduced on WSL2 (CI-parity check).
**Authority:** implementation plan `docs/superpowers/plans/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-implementation.md`; design
`docs/superpowers/specs/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md`.

## Design digest

Approved frozen design-body SHA-256 (UTF-8 LF-normalized body after removing the digest header line):

`66606036b37ddc59cf9f2f4c8a713156a1f839fb771679a16937a5263c9ca4a2`

Unit oracle: `tests/unit/mcp/test_client_mcp_closure.py::test_approved_design_digest_still_matches_frozen_body`.

## Client-supplied ACP MCP vs Gateway-brokered MCP

| Surface | Authority | Telemetry / provenance |
|---|---|---|
| Client-supplied ACP `mcpServers` | Agent-owned `ClientMcpDisposition` + CLI durable trust + `PreToolGuard` / `ConfigTrustScanner` | `client_supplied_acp` only |
| Gateway-brokered MCP | Gateway profiles / signed manifests / `MCPTrustRegistry` (`legacy_manifest`) | Must not be labeled `client_supplied_acp` |

Credentials for client-owned servers stay transient on the connection path, never model context, argv, telemetry, evidence reports, or durable records as raw values.

## Claim-to-evidence map

| Claim | Evidence |
|---|---|
| Design freeze | Digest above; design spec header |
| Terraform stdio real dependency | Image `sha256:bd095e2b442a2cb61255fe4db52f9e824f35d307a2044784c95d37a93f18d324`; `requires_mcp_stdio` PASSED on native Windows Docker Desktop (`reports/p11-fu-9-client-mcp-live-evidence.md`) |
| Context7 HTTP real dependency | Negotiated protocol version `2025-11-25`; public credential-free URL; `requires_mcp_http` PASSED |
| Official `mcp` SDK composition | `tests/integration/mcp/test_client_sdk_real.py` — injected hardened `httpx2.AsyncClient(follow_redirects=False, trust_env=False)` + streamed byte-budget (`REMOTE_BYTE_OVERFLOW`); no fake session/transport |
| Scanner / credential boundaries | `ConfigTrustScanner` + `PreToolGuard` on client catalog/call path; credential name fingerprints only in durable records / audit fields |
| Transport capability status | Equal CLI-ceremony baseline for durable stdio/HTTP/SSE; live probes exercised stdio (Terraform) and Streamable HTTP (Context7); SSE remains capability-advertisement + ceremony-equal, not a separate authenticated upstream claim |
| Generic-tool-only model surface | Model/tools see only static generic MCP list/call operations (`MCP_LIST` / `MCP_CALL`); no dynamic model-tool registration |
| `session/new` allow-once / timeout | ACP permission options include `allow_once`; one-call approvals and disposition timeouts fail closed; write path remains fail-closed until `P11-FU-20` attaches a real authorizer (`issue` → `None`) |
| Session shutdown ordering | `ClientMcpDisposition` / supervisor teardown closes client MCP sessions before ACP duplex end; Windows process-tree seam + POSIX group seam selected by platform |
| Classifier distributions | Terraform tokenized read=9/network=0/write=0 vs legacy read=0/network=6/write=3; Context7 tokenized read=2/network=0/write=0 vs legacy read=0/network=2/write=0 |
| acpx empty-array | Live capture still SKIPPED (`acpx_capture_incomplete exit=1 stop=None`) — known acpx↔optimus-agent gap, not fabricated success. Harness + fixture verifier prove empty `mcpServers` noop shape and content-free report fields |
| Per-advertised-transport evidence | Advertised `mcpCapabilities` http/sse fields recorded in safe evidence extract; live non-empty per-transport acpx sessions remain residual with the empty-array skip (stdio/HTTP proven at MCP SDK/live tiers, not via completed acpx empty-array capture) |
| `session/load` exclusion | Explicitly owned by `P11-FEAT-ZED-RESUME` (Plan 11.7); this plan does not implement `session/load` |

## Deferred custody (named backlog headers — not resolved here)

These remain tracked, not yet scheduled, in
`docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`. Closure links them; it does not close them:

1. ### Durable client-MCP descriptor-surface pinning and named tool allowlists
2. ### Client-MCP durable HTTP/SSE trust relaxation
3. ### Authenticated client-owned MCP upstream evidence
4. ### Plan 11.8 Windows `WinError 10053` MCP test flake

Additional related follow-ups raised during implementation (`P11-FU-18`, `P11-FU-19`, `P11-FU-20`, …) stay in the same backlog with their own status lines; they are not silently folded into this closure.

## Live / fitness anchors (Task 8, reconfirmed for closure)

- Step 4 selector: `999 passed, 19 skipped` (native Windows; hang fixed).
- Full default `pytest -q` at Task 9 gate: `2874 passed, 27 skipped, 81 deselected`.
- Coverage: `85%` aggregate (`coverage report --fail-under=80`).
- Ruff clean; `git diff --check` clean; Plan 9.96 custody gate passed (Task 8).
- Live: Terraform stdio PASSED; Context7 + real SDK httpx2 PASSED; acpx e2e 2 passed / 1 skipped (empty-array residual).

## Residuals after plan closure

1. Live acpx empty-array / completed per-advertised-transport ACP capture (`acpx_capture_incomplete`).
2. The three P11-FU-9 deferral headers and the Plan 11.8 `WinError 10053` flake above.
3. `P11-FU-20` real catalog/authorizer attachment for one-call issuance.
4. Authenticated client-owned upstream evidence (same named deferral header).
