# MCP Gateway Security Best-Practices Reference

**Purpose:** External reference material for the HLD/LLD/Guardrails architecture amendment that
reverses the current "MCP Gateway contract out of scope" exclusion (see
`docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`, `P11-FU-3`, and
`P11-FEAT-GATEWAY-MCP`). This document does not decide Optimus's design. It collects what the
cited sources say MCP clients/gateways should do, and for each theme names the open question the
amendment must resolve. Operator directive (2026-08-05): ensure proper security safeguards and
best practices are applied when reversing the exclusion.

**Status:** Reference input, not a design document. Required reading before drafting the
architecture amendment; does not itself authorize any implementation.

## Sources

| # | Source | Type | Captured |
|---|---|---|---|
| 1 | [Anthropic — "Code execution with MCP"](https://www.anthropic.com/engineering/code-execution-with-mcp) | Engineering blog | 2026-08-05 |
| 2 | [mcpmanager.ai — "MCP Permissions"](https://mcpmanager.ai/blog/mcp-permissions/) | Vendor blog | 2026-08-05 |
| 3 | [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/) | Standards body | Re-verified 2026-08-05 against the OWASP GenAI Security Project canonical list. The **2025** edition is current; the earlier v1.1-era numbering originally captured here was stale and has been corrected throughout this document |
| 4 | *AI Agents with MCP* (O'Reilly), Ch. 4 — client capabilities, OAuth, multi-server, context engineering, best practices | Book excerpt | Pasted verbatim by operator, 2026-08-05 |

Sources 1–3 were fetched and summarized by an intermediate model, not read verbatim end-to-end;
treat the extracted points below as directionally accurate and re-verify any specific claim before
citing it as a hard requirement in the amendment.

## Theme 1 — MCP servers are arbitrary code; the client/gateway is the trust boundary

**Source 4 (O'Reilly):** "In MCP, the client acts as the trust boundary between potentially
malicious or compromised servers and the host application (and thus, the user)." Also: local MCP
servers mean arbitrary code execution in the host's environment — "pin local server versions and
rely on trusted MCP registries for locating servers."

**Source 3 (OWASP 2025):** LLM03:2025 Supply Chain — third-party models, packages, and plugins
introduce vulnerable or malicious components. Note that the standalone *Insecure Plugin Design*
category from the older edition no longer exists in the 2025 list; its substance is now split
across LLM03:2025 Supply Chain and LLM06:2025 Excessive Agency, so an amendment cannot cite
"insecure plugin design" as a current OWASP category.

**Already true in Optimus today:** LLD §12B and Guardrails §5/§5.2 already establish this exact
principle locally (`MCPTrustRegistry`, `ConfigTrustScanner`, no implicit trust/auto-load,
manifest-hash re-approval). This is the layer the amendment must extend, not replace.

**Open question for the amendment:** if transport moves to the Gateway process, does server/tool
trust-vetting stay agent-side (Gateway only ever executes pre-approved calls) or does trust
evaluation need a Gateway-side counterpart? A trust decision made in one process and enforced in
another is exactly the kind of seam that gets silently bypassed later — the amendment must state
which process is authoritative and why, not just where each guard function happens to live today.

## Theme 2 — Permission model: least privilege, explicit consent, distinct identity

**Source 4 (O'Reilly):** Roots are explicitly **not** a security measure — "servers can choose to
not respect the boundaries set by roots, so your host application should have the final say."
Elicitations require clear server attribution, explicit accept/decline/cancel, schema validation,
and rate limiting. Sampling requires human-in-the-loop approval both before forwarding a server's
request to the LLM and before returning the LLM's response to the server — "both myself and
Anthropic strongly recommend" this.

**Source 2 (mcpmanager.ai):** Recommends attribute-based (not just role-based) access control —
who, what, when, where, how much. Names a real GitHub PAT vulnerability class: an over-broad scope
(`Read and Write`) silently authorizes unintended endpoints (e.g. PR merging) alongside the
intended one. Best practices: distinct identity per agent (not shared/conflated with user or
service identity) for audit traceability; time-limited and scope-limited grants; least privilege
as the starting point, expanded only when justified; centralized declarative policy rather than
logic scattered across code; test permission logic against simulated prompt-injection attacks
before production.

**Source 3 (OWASP 2025):** LLM06:2025 Excessive Agency — granting the model too much
functionality, permission, or autonomy lets an influenced model take harmful actions.

**Already true in Optimus today:** `MCPServerTrustRecord` already carries `allowed_tools` and
`permission_scope`; `PreToolGuard`/`ToolSurface.MCP` already gates execution on
`approval_granted`. This is a real head start, not a gap — the amendment should show how Gateway
transport composes with this existing scoping rather than introducing a second, parallel
permission model.

**Open question for the amendment:** does a Gateway-brokered MCP call get its own audit identity
distinct from the model/search/extract/package/advisory calls it already accounts for? Roots not
being a real security boundary means: if Optimus ever exposes filesystem-scoped MCP tools, the
enforcement point has to be the existing pre-tool guard, never the MCP `roots` mechanism alone.

## Theme 3 — Tool definitions and tool results are untrusted input

**Source 4 (O'Reilly):** "Remember, even tool definitions and their results are untrusted input
that gets injected into the model context. This is, quite literally, prompt injection... In MCP,
this is by design, which forces the client developer to distinguish between desired and malicious
prompt injection." Mitigation: keep the human in the loop, display tool descriptions/names/schemas
for approval, re-obtain consent on any `listChanged` notification, and **namespace tools to their
server** to prevent name-shadowing attacks when multiple servers are connected.

**Source 3 (OWASP 2025):** LLM01:2025 Prompt Injection; LLM05:2025 Improper Output Handling —
model output passed to downstream systems without validation enables injection, SSRF, or remote
code execution.

**Open question for the amendment:** Optimus already has a `ConfigTrustScanner` for manifest
ingestion — does the same (or an equivalent) scanning discipline extend to live tool-call
*results* coming back through the Gateway, not just server configuration at registration time? If
Optimus connects to more than one MCP server (the operator's own example, Context7, plus
potentially others), tool namespacing needs an explicit answer before that becomes a real
collision risk rather than a hypothetical one.

## Theme 4 — Remote/authenticated servers use OAuth 2.1, not ambient credentials

**Source 4 (O'Reilly):** For streaming-HTTP MCP servers, the client is the OAuth client, the MCP
server is the resource server, and the authorization server is separate from MCP itself. Prefer
Client ID Metadata Document (CIMD) registration; fall back to dynamic client registration.
Per-server token storage (`TokenStorage` protocol) is required. For stdio (local) connections,
credentials come from the environment, not OAuth.

**Existing Optimus constraint this must reconcile with:** the whole Gateway architecture today
holds exactly **one** developer-owned aggregator credential (`OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY`
today; see also `P11-FU-8`'s naming discussion) and the agent process gets zero upstream
credentials. Arbitrary MCP servers — potentially many, each with independent OAuth scopes and
tokens — is a materially different credential-management shape than "one aggregator secret."

**Open question for the amendment:** this is the single largest architectural decision the
amendment has to make explicitly, not gesture at. Candidates worth the design comparing on their
merits (not a recommendation — this is the amendment's job): per-server credential storage inside
the Gateway process (extending "isolate upstream credentials from the agent process" to N servers
instead of 1); an explicit allow-list of pre-provisioned MCP servers only, deferring dynamic OAuth
entirely to a later phase; or something else. Silently assuming OAuth token storage "just works"
inside the existing one-key model without stating so is exactly the kind of implicit widening the
requirement-extraction gate exists to catch.

## Theme 5 — Context/cost efficiency and sandboxing (code execution pattern)

**Source 1 (Anthropic):** Loading many tool definitions upfront and round-tripping intermediate
results through the model both waste tokens and money — large results can double-count context
("flows through twice"). Anthropic's alternative (code execution / "code mode"): the model writes
code against typed tool stubs in a sandbox; intermediate results and PII stay in the sandbox and
never enter model context; reports a 98.7% token-use reduction in their own measurement.
Sandboxing requirements if this pattern is ever adopted: no outbound network access from the
sandbox, no credentials inside the sandbox (those stay at the client/Gateway boundary), no path
back into the host application's own execution environment.

**Source 4 (O'Reilly):** Complementary lighter-weight pattern — "tool search": give the model one
search tool instead of the full tool list, inject only matched tools into context per turn.

**Open question for the amendment:** not a security question first — a cost/architecture one, but
with a real security dimension if code execution is ever pursued (a sandboxed code-execution path
is a materially larger security surface than a synchronous per-call broker, and Optimus's existing
budget/cost-attribution ledger would need to account for it differently). The amendment should at
minimum state whether Gateway-MCP v1 is a simple call-broker or leaves room for a future
code-execution mode, since that choice affects the credential/sandbox questions above.

## Theme 6 — Connection resilience (operational, not strictly security)

**Source 4 (O'Reilly):** Post-2026-07-28 spec, MCP connections are stateless — clients recover by
retrying the last request with backoff, not by resuming a session. Non-idempotent tool calls are
the client/host's responsibility to deduplicate on retry, not the protocol's.

**Relevance:** worth the amendment noting explicitly given Optimus is mid-thread on a *different*
resume/durability problem (`P11-FEAT-ZED-RESUME`, ACP `session/load`) — MCP's statelessness is
unrelated to ACP session resume and the two must not be conflated in the design.

## Cross-reference: OWASP LLM Top 10 relevance

Re-verified 2026-08-05 against the **2025** edition. Any amendment text citing OWASP must use these
IDs; the older numbering originally captured in this document was wrong for every category except
LLM01, and one category it leaned on (*Insecure Plugin Design*) no longer exists.

| Risk (2025 edition) | Direct relevance to Gateway-brokered MCP |
|---|---|
| LLM01:2025 Prompt Injection | Tool definitions and results returned from MCP servers are untrusted input into the model context (Theme 3). |
| LLM02:2025 Sensitive Information Disclosure | Per-server credentials and any PII passing through MCP tool calls (Theme 4, Theme 5). |
| LLM03:2025 Supply Chain | Which MCP servers/versions are trusted, and how they are pinned (Theme 1). |
| LLM05:2025 Improper Output Handling | MCP tool results must not be trusted or executed without validation downstream. |
| LLM06:2025 Excessive Agency | Scope/approval boundaries on what an MCP-brokered call may actually do (Theme 2). This category, together with LLM03, absorbs the withdrawn *Insecure Plugin Design* entry, making it the closest current analogue to the core shape of this feature. |
| LLM07:2025 System Prompt Leakage | New in 2025 and not previously considered here: a connected MCP server participates in the model's context loop, so the amendment must state whether any system-prompt or instruction content can reach a server. |
| LLM10:2025 Unbounded Consumption | New in 2025 and not previously considered here: an MCP server returning unbounded results consumes both context and budget, which ties directly to the cost/ledger-attribution question rather than being a pure availability concern. |

(LLM04:2025 Data and Model Poisoning, LLM08:2025 Vector and Embedding Weaknesses, and LLM09:2025
Misinformation are less directly implicated by this specific feature and are not expanded here.)

## Checklist for the amendment (must be explicitly addressed, not silently assumed)

- [ ] States which process (agent vs. Gateway) is authoritative for MCP trust/permission decisions
      once transport exists, and reconciles it with the existing agent-side `MCPTrustRegistry`.
- [ ] Defines the credential-isolation model for potentially many independent MCP servers,
      explicitly extending (not quietly bypassing) the one-key/aggregator-credential principle.
- [ ] Defines whether/how OAuth 2.1 is supported for remote MCP servers, or explicitly excludes it
      for v1 with a stated reason.
- [ ] Defines tool-result trust handling (not just manifest/config trust) and tool namespacing
      across multiple connected servers.
- [ ] States whether roots-style filesystem exposure (if used) is enforced only by Optimus's own
      pre-tool guard, never trusted from the MCP server side alone.
- [ ] Defines cost/budget attribution for MCP tool calls within the existing usage ledger.
- [ ] States explicitly that this does not change or weaken ACP `session/load` resume work
      (`P11-FEAT-ZED-RESUME`) — separate protocols, separate statefulness models.
- [x] Cites current OWASP LLM Top 10 numbering for any risk claims made in the amendment's own
      text. **Resolved 2026-08-05:** the 2025 edition is confirmed current and the cross-reference
      table above has been corrected to it. The amendment must not reintroduce the withdrawn
      *Insecure Plugin Design* category or the pre-2025 IDs.
