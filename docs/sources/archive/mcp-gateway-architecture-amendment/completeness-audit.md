# MCP Gateway architecture amendment completeness audit

## Status and method

Task 10 Step 3 was run against the approved design, consolidated redline, security reference,
changed-page sources, and extracted candidate PDFs. The 26 required-evidence rows in design §12
are all mapped below to a document section, source-page mapping, and an extracted phrase. The
page numbers are source-document page numbers; the exact fragment-to-source mapping is recorded
in `changed-pages-manifest.md`.

The audit distinguishes architecture evidence from implementation evidence. The publication
proves that each claim and its required evidence obligation is present in the documents; it does
not claim that the future MCP runtime or live Gateway evidence already exists.

## Design §12 required-evidence rows

| # | Design claim | Publication citation and extracted phrase | Result |
|---:|---|---|---|
| 1 | Agent holds no upstream MCP credential | HLD §5A, p.3: `zero upstream credentials in the agent process`; HLD §10.C, p.9: `no model, search, MCP, OTel, or other upstream credential is resolvable` | PASS |
| 2 | Direct bearer caller cannot widen tools | HLD §11, p.10: `cannot exceed the operator-provisioned Gateway allowlist`; Guardrails §2.4, p.4: `Gateway allowlist enforcement is mandatory on every MCP call` | PASS |
| 3 | Profile changes force reapproval | LLD §12, p.39: `mcp.manifest_hash_changed` for rotation and Gateway profile changes; Test Strategy §6, p.6: `secret rotation` and `profile revisioning` tests | PASS |
| 4 | Rotation property survives migration | Test Strategy §6-7, pp.5-6: the `named successor` proves Gateway-side rotation causes agent-side reapproval without secret or secret-derived logging; LLD §12D, p.40 preserves the denial class | PASS |
| 5 | Bootstrap is satisfiable | LLD §0.D, p.2: `registration requires profile_id and profile_revision`; LLD §0.E, p.3: `restart activation`; Test Strategy §6, p.5: `registration bootstrap` | PASS |
| 6 | Descriptor drift is bounded | LLD §0.D, p.2: `freshness: stale_marked` on recoverable refresh failure and denial on drift; Guardrails §5.2, p.8: `complete-only` freshness and drift distinction | PASS |
| 7 | Tool namespace is collision-safe | LLD §0.D, p.2: `profile_id.tool_name`; Test Strategy §6, p.5: `two-name-space collisions` and `canonical hash equality` | PASS |
| 8 | Deferred protocol features fail closed | Guardrails §3.3, p.6: `input_required is a typed, call-scoped denial`; Test Strategy §11-14, pp.10-14: fail-closed fixtures for roots, sampling, elicitation, logging, subscriptions, and auto-dereference | PASS |
| 9 | HTTP header mirroring is absent | LLD §0.D, p.2: `invalid x-mcp-header definitions are excluded` and `no Mcp-Param-* emission`; Guardrails §5.2, p.8 repeats the boundary | PASS |
| 10 | Stdio credential isolation is real | Guardrails §5.3, p.8: `Docker digest image`, `no host mounts/devices/socket`, and safe `-e NAME` projection; Test Strategy §6, p.5: Docker stdio isolation evidence | PASS |
| 11 | Resource controls are symmetric | HLD §11.1, p.11: `resource + budget + usage controls`; Guardrails §5.3, p.8: timeout/output limits, bounded reads, termination, and platform-gated confinement | PASS |
| 12 | Unknown spend is never zero | LLD §9E, p.31: `settled | explicit_zero | unavailable`; Test Strategy §8A, p.8: consumer sweep, strict denial, display, and reconciliation | PASS |
| 13 | Indeterminate mutation is not silently repeated | LLD §12D, p.40: `holds a side-effecting (profile_id, tool) until operator acknowledgment`; Guardrails §7.3, p.10: no automatic `tools/call` retry | PASS |
| 14 | Accounting failure cannot escape budget control | LLD §9E, p.31: `withholds the result and holds the run`; Test Strategy §8-9, pp.8-9: persistence-only recovery under the same request ID | PASS |
| 15 | Protocol interoperability is real | Test Strategy §1-3, pp.1-3: `real Gateway plus independently authored MCP servers over both transports`; §14.10, p.14 maps live evidence to release obligations | PASS |
| 16 | Protocol generation is correct | LLD §0.D, p.2: only `server/discover`, `tools/list`, and `tools/call` at `2026-07-28`; Test Strategy §6, p.6: no HTTP `initialize`/session/ping and discovery-first stdio negotiation | PASS |
| 17 | Context7 compatibility dependency is honest | HLD §11, p.10: `authenticated Gateway-originated probe`; Test Strategy §11-14, pp.10-14: configured endpoint must prove exact version plus tools; unsupported evidence yields `mcp.protocol_version_unsupported` | PASS |
| 18 | Pagination is complete or absent | HLD §6, p.4: `complete bounded tools/list pagination` and no partial prefix; LLD §0.D, p.2: malformed/incomplete pages reject discovery atomically; Test Strategy §6, p.6: cursor-loop and malformed-page denial | PASS |
| 19 | Registry cannot become autoload | HLD §10.A, p.7: `operator consults catalog` with no data-plane registry edge; Guardrails §8.3, p.10: catalog can only prefill a pending operator proposal | PASS |
| 20 | Provisioning and connections stay separate | LLD §6.1, pp.20-21: `transport lifetime cannot mutate profiles`; Guardrails §8.3, p.10: open/close cannot activate; Test Strategy §10, p.9: lifecycle test | PASS |
| 21 | Elicitation remains triply closed | LLD §12B, p.40: `v1 path rejects all three boundaries`; Test Strategy §11-14, pp.10-14: no schema, URL, or request state reaches the planner | PASS |
| 22 | Sampling cannot spend or inject | HLD §5A, p.3: sampling is closed because it can initiate model spend; LLD §9E, p.31: no v1 sampling-only schema fields and two human decisions; Test Strategy §9, p.9: no model call, reservation, provider usage, MCP usage, or response | PASS |
| 23 | Descriptor context is cost-bounded | HLD §5A, p.3: operator-selected subset plus descriptor-count and UTF-8-byte ceilings; Guardrails §5.2, p.8: admission and recording; Test Strategy §10, p.10: ceilings and selected identities | PASS |
| 24 | MCP errors extend existing retry | LLD §6.1, pp.20-21: only transient discovery/list failures use existing `RetryPolicy`; Test Strategy §8-9, pp.8-9: `tools/call` never retries and discovery retry is capped | PASS |
| 25 | OWASP voice and ownership are non-ambiguous | HLD §11, p.10 and LLD §12B, p.40: every generalized row is `REFERENCE — Cross-cutting`; separate rows are `NORMATIVE — P11-FEAT-GATEWAY-MCP`; Test Strategy §14.10, p.14 explicitly excludes reference rows from acceptance criteria | PASS |
| 26 | Exclusion provenance is honest | Guardrails §13, p.16: repaired v1.0/v1.1/v1.2 chain and `hosted-SaaS-premise explanation is therefore unconfirmed`; HLD §11, p.10 preserves the same unconfirmed framing | PASS |

## Redline-cluster coverage

| Cluster | Authored citation | Extracted evidence anchor |
|---|---|---|
| HLD-MCP-1 | HLD §5A, p.3 | `zero upstream credentials`, `MCPUsageRecord`, descriptor-context ceilings, sampling no-spend position |
| HLD-MCP-2 | HLD §6, p.4 | guarded MCP branch, `server/discover`, complete `tools/list`, cursor/transient/capacity distinction |
| HLD-MCP-3 | HLD §10.A, p.7 | remote HTTP and local stdio Gateway edges; catalog-only operator reference; no agent-to-MCP edge |
| HLD-MCP-4 | HLD §10.C, p.9 | only Gateway URL/API key in agent; profile-isolated MCP secrets |
| HLD-MCP-5 | HLD §11, p.10 | protocol floor, Context7 probe, split-authority residual, OAuth/elicitation positions, two-voice panel |
| HLD-MCP-6 | HLD §§11.1-12, pp.11-12 | agent/Gateway gates, result accounting before release, quality/evidence gates, logging denial |
| LLD-MCP-1 | LLD §§0.B-0.C, pp.1-2 | typed broker components and separate `MCPTrustRegistry` |
| LLD-MCP-2 | LLD §0.D, pp.2-3 | exactly two MCP routes, arguments-only payload, HTTP/stdio method sets |
| LLD-MCP-3 | LLD §§0.E-0A, pp.3-5 | profile union, revision/activation, OAuth binding discriminator, configuration limits |
| LLD-MCP-4 | LLD §§9-10A, pp.31-35 | attribution states, strict-budget denial, persistence recovery, consumer sweep |
| LLD-MCP-5 | LLD §§12-12D, pp.39-40 | trust integration, indeterminate holds, reference/normative tables, future elicitation contract |
| LLD-MCP-6 | LLD §6.1 and runtime checklist, pp.20-21, 26-30 | existing retry taxonomy, stateless HTTP, bounded stdio teardown, stale refresh |
| GR-MCP-1 | Guardrails §§2-3, pp.4, 6 | split authority, direct-bearer residual, pre-tool admission, call-scoped denials |
| GR-MCP-2 | Guardrails §5, p.8 | supply-chain pins, discovery/pagination, result/resource controls, catalog-only handling |
| GR-MCP-3 | Guardrails §§5.2, 9, 11, pp.8, 10-14 | explicit enforced/platform-gated/residual stdio tiers, accounting, sandbox disclaimer |
| GR-MCP-4 | Guardrails §13, p.16 | v1.0/v1.1/v1.2 document-control chain and unconfirmed provenance |
| TS-MCP-1 | Test Strategy §§1-3, pp.1-3 | named custody for out-of-scope OAuth/deferred capabilities/ACP seams and real evidence tiers |
| TS-MCP-2 | Test Strategy §§6-7, pp.5-6 | bootstrap/restart, allowlists, namespace/hash, protocol generation, Docker/HTTP evidence |
| TS-MCP-3 | Test Strategy §§8-10, pp.8-9 | accounting consumer sweep, retry taxonomy, result withholding, schema/result boundaries |
| TS-MCP-4 | Test Strategy §§11-14, pp.10-14 | fail-closed fixtures, Context7 probe, extended §14.4/§14.5, normative traceability |

## Security-reference closing checklist

| Security-reference requirement | Publication evidence | Result |
|---|---|---|
| Agent/Gateway authority reconciled | HLD §11 p.10 names agent approval/scope/effect authority and Gateway profile/allowlist/budget authority; Guardrails §2.4 p.4 repeats the residual | PASS |
| Many-server credential isolation | HLD §§5A/10.C pp.3,9 and LLD §0A p.4 define Gateway-only, profile-scoped references with no secret-derived agent data | PASS |
| OAuth 2.1 explicitly scoped | HLD §11 p.10 and LLD §0A p.4 state static-credential-only v1 and distinguish same-grant refresh from rotation/reapproval | PASS |
| Result trust and namespacing | LLD §§0.D/12 pp.2,39 and Guardrails §5.2 p.8 require namespaced tools, untrusted content, complete-only results, and inert resources | PASS |
| Roots controlled by Optimus | Guardrails §5.3 p.8 states roots are not containment; Test Strategy §11-14 pp.10-14 has roots fail-closed fixtures | PASS |
| MCP cost/budget attribution | LLD §9E p.31 defines `MCPUsageRecord` states and strict unknown-cost denial; Test Strategy §8A p.8 covers consumers | PASS |
| ACP session resume kept separate | Test Strategy §1-3 pp.1-3 names `P11-FEAT-ZED-RESUME` as distinct custody; no MCP transport resume is claimed | PASS |
| Current OWASP numbering and voice | HLD §11 p.10 and LLD §12B p.40 use 2025 LLM01/02/03/05/06/07/10 reference rows; Test Strategy §14.10 p.14 excludes them from acceptance criteria | PASS |

## OWASP voice and ownership audit

The HLD architectural-reference panel on source p.10 and the LLD reference table on source p.40
contain the literal `REFERENCE — Cross-cutting` label and no normative ownership/test obligation.
The physically separate MCP tables contain the literal `NORMATIVE — P11-FEAT-GATEWAY-MCP` label.
Test Strategy §14.10 (source p.14) maps only the normative rows and explicitly states that reference
rows do not create acceptance criteria. The validator's candidate-PDF phase passed the corresponding
voice/ownership and source-inventory checks; no generalized OWASP row is treated as a release test.

## Provenance, ruling, and custody audit

- The prior local-Gateway v3 redline rule 14 explicitly said `MCP is outside this correction`,
  kept `P11-FU-3` open, and kept `P11-FEAT-GATEWAY-MCP` blocked. The amendment replaces that
  exclusion with the separately approved typed-contract publication; it does not rewrite the old
  rule or claim that its hosted-SaaS rationale was confirmed.
- Guardrails source p.16 preserves the v1.0 entry, adds the missing v1.1 local-Gateway correction,
  and records v1.2. The same page says the hosted-SaaS-premise explanation is unconfirmed.
- HLD §11 source p.10 cites official Go SDK v1.7.0 as support evidence and separately identifies
  immutable snapshot `f817239` as frozen wire content under `schema/draft/`, not final per-version
  specification publication.
- HLD §11 source p.10 and Test Strategy source pp.10-14 name Context7 as a dependency but require
  an authenticated Gateway-originated exact-version/tools probe before any reachability claim.
- Remote HTTP is documented as no-fallback at `2026-07-28`; containerized stdio retains
  discovery-first modern/legacy negotiation. External MCP logging is closed without altering
  Optimus audit logging.
- The five custody entries `P11-FU-12` through `P11-FU-16` are present in the amended backlog;
  no sixth signed-per-call-capability follow-up is created. `P11-FU-9`, `P11-FEAT-ZED-RESUME`, and
  `P11-FEAT-REGISTRY` remain explicitly non-conflated.

## Exclusion and residual findings

The candidate-PDF exclusion-reversal scan returned zero matches for the four prohibited current
exclusion phrases. Historical source material remains confined to the approved provenance and
historical-version locations. Runtime implementation, live Gateway, Context7, Windows/Linux
process-confinement, and future OAuth/elicitation/sampling evidence remain implementation or

## Task 11 current-state claim sweep

The prescribed repository scan was run over `README.md`, `docs/superpowers`, and `docs/sources`:

```text
rg -n -i "no mcp endpoint|mcp.*out of scope|mcp.*blocked|P11-FU-3|P11-FEAT-GATEWAY-MCP|one upstream credential|one aggregator credential|single-key" README.md docs/superpowers docs/sources
```

Every hit was classified by owning document and context. The results are:

| Hit class | Locations | Classification and action |
|---|---|---|
| Ratified current state | The amendment package, amended charter, consolidated backlog, roadmap, redline, security reference, and publication plan | Updated normative state. These documents describe the bounded tools-only/static-profile/dual-transport contract, `P11-FEAT-GATEWAY-MCP` ownership, conditional `P11-FU-3` closure, and five distinct custody entries. The retained HLD §5A “Single-Key Model” heading is a source-section label; its body and candidate evidence explicitly state zero upstream provider credentials in the agent process. No stale current-state edit is required inside the already-approved package. |
| Current README credential claims | `README.md` runtime, configuration-foundation, release-gate, and local-Gateway paragraphs | Stale shorthand. Updated to state zero upstream provider credentials in the agent process, with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` as local inputs; credential-scan implementation names were not changed. |
| Current roadmap/backlog credential claims | `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` release-gate/scanner language and the named backlog acceptance criterion | Stale shorthand. Updated to “Gateway-only” or “zero-upstream-credential” terminology without changing gate ownership or implementation scope. |
| Current authoritative section map | `docs/superpowers/reports/2026-07-25-plan-11-authoritative-doc-section-map.md` source set, diagram survey, MCP ownership finding, and credential rows | Stale current-state map. Added the Task 10-approved candidate versions, page counts, output hashes, replacement-page counts, diagram survey, and amendment ownership overlay; legacy v3 rows are explicitly marked as source-pin provenance and no longer serve as current MCP conclusions. |
| Historical baseline evidence | `docs/sources/local-gateway-architecture-v3`, the v3 redline/correction reports, the pre-amendment 2026-07-27 design/spec, and older implementation plans/reviews | Historical or superseded evidence. Their “no endpoint”, “blocked”, and one-key wording records the state that the amendment reviewed; no current-state edit is authorized or required in those frozen records. |
| Procedural scan patterns and verification evidence | The publication plan commands, verification record, and extracted historical/source audit files | Procedural or audit evidence. Pattern strings and historical matches are intentionally retained; they do not assert the old state as the current publication contract. |

`README.md` had no MCP endpoint/blocking exclusion claim beyond the credential shorthand addressed
above. The scan found no unowned current MCP follow-up: `P11-FU-12` through `P11-FU-16` remain the
five named custody entries, while `P11-FU-9`, `P11-FEAT-ZED-RESUME`, and `P11-FEAT-REGISTRY` remain
separate identities.

## Task 11 custody consistency

Cross-file identity checks passed across the charter, consolidated backlog, roadmap, refreshed
section map, redline, and final candidate-text extracts:

| Identity | Canonical wording / boundary | Result |
|---|---|---|
| `P11-FEAT-GATEWAY-MCP` | Bounded v1 Gateway MCP tools-only brokering through static profiles over remote HTTP and Docker-contained stdio; owned by the amendment and gated by `P11-FU-3` until final approval/publication | PASS |
| `P11-FU-12` | MCP OAuth 2.1 lifecycle | PASS |
| `P11-FU-13` | Deferred MCP capabilities and long-lived interaction | PASS |
| `P11-FU-14` | MCP registry discover-and-connect, distinct from ACP `P11-FEAT-REGISTRY` | PASS |
| `P11-FU-15` | MCP tool search and context minimization | PASS |
| `P11-FU-16` | Reverse research-to-documentation freshness gate | PASS |
| `P11-FU-9` / `P11-FEAT-ZED-RESUME` | Client-supplied ACP `mcpServers` and ACP session custody remain separate from Gateway-brokered MCP | PASS |
| `P11-FEAT-REGISTRY` | ACP registry publication/release identity remains separate from MCP catalog metadata and discover/connect | PASS |

No sixth MCP follow-up or conflated ACP custody identity appears in the refreshed section map,
charter, backlog, roadmap, redline, or candidate evidence.
