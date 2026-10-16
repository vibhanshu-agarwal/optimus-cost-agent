# Hypothesis compatibility sanitizer oracle — delivered-source record

Record date: 2026-10-16 (Asia/Calcutta). Work disposition and authority belong to [#364](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/364). This is a sanitized terminal evidence summary, not a new implementation plan or a second work register.

## Delivered source and review

[PR #365](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/365) merged at 2026-10-16T10:13:54Z as `f173d98f54be8616317214bb4b4ccccd2aba99fa`, tree `b254b1e450a905770df47e8a9822bfd30c6ed280`. Ordered parents are `b27e99a347428a063050d7460e031eb47369b71c` and `f1b248015cff0fa9aebe7af7e521f157e6265f5e`. The actual merge tree equals the accepted CP2 head and the distinct tested PR integration `c06fd80555e5ab9702a365abe1325f97547c6b37`.

Seven paths added 418 lines: the six-test compatibility-policy oracle, Hypothesis 6.167.1 and required sortedcontainers 2.4.0, and four adopted documentation paths. No production sanitizer, checker, test protection, hook or CI configuration changed. Claims cover bounded compatibility-policy free text only; generation is not a universal proof or a cross-version input identity guarantee.

Claude independently accepted [CP1](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/364#issuecomment-6205789554), [committed-source CP2](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/364#issuecomment-6212501720), [CP3 pre-merge](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/364#issuecomment-6213175611), and [actual delivered main](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/364#issuecomment-6213637440). These are distinct source-bound receipts; no earlier verdict was transferred to changed source.

## Verification evidence

- CP1 killed all six required mutants with attributable assertion failures and green real-function/unmodified-clone controls. Two detections were incremental relative only to the old sanitization file's direct public-function calls.
- CP2 retained three fresh-process security baseline/candidate timing pairs per OS. Median paired added cost was 3.8420882 s on Windows and 5.0572219 s on Linux. Six-test ordinary serial runs were 4.1845687 s and 7.6821240 s; supported two-worker runs were 5.0864549 s and 12.0409897 s. Both 30-second budgets passed. Linux local evidence includes the WSL Windows-filesystem bridge qualification. Cold isolated storage was confined to timing repetitions; ordinary ignored cache writes remained allowed.
- The normal hook-enforced local commit passed after the retained first attempt and reviewed documentation repairs. Committed-head documentation checks passed 110 tests. Native Windows CP2 full-product evidence passed 7,788 tests, skipped 40 and deselected 111, with one existing warning. Its independent exactly-one proof considered 371 terminal records and selected session `20261016T083348-42568-ba8bf3`. Native Windows protection was valid/full; UNKNOWN ancestry observations remain qualified. Exact-base comparison found no safety-module regression.
- Hosted PR Linux evidence passed 7,615 tests, skipped 213 and deselected 111, with one existing warning. The actual main's own original [push guardrails run 38885847937](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/38885847937), attempt 1, also passed with those totals, in 1,097.84 s. REST, checkout and report head all bind to the actual merge. No manual CI retry or duplicate full suite was used.
- Main's independent typed-record eligibility replay found exactly one eligible full/default session among all 67 uploaded terminal records: `20261016T101443-2880-ed5871`, selected 7,828, deselected 111, zero collection errors, reconciled. Universe digest: `ba5608aff5a4e14195a4dbf5649101e7699b8497c2b68b04483e559c2526ff09`. A separate producer validation collection receipt supplied the universe, rather than selecting the latest/largest or merely naming a record.
- Main product floors passed: Optimus 88.89697852202403%, ContextEngine 95.92430858806405%, model policy 96.98795180722891%, aggregate 84.08698334361505% against 80%. EvidenceHandoff 65.96291012838802% remains informational/deferred. All seven safety statement/branch rows and every measured file are identical to the accepted PR producer. The sanitizer remains 340/345 statements.

Linux records are active/default/COMPLETE with full audit depth, native support false, protection none and parent unsupported; Windows protection parity is not claimed. Hosted artifacts contain terminal records, not raw individual call-phase streams. The six new nodes' membership and the full passing verdict, together with six additional passes versus exact base and unchanged skips/deselections, establish the count-based Linux result. Windows retains the direct six-call proof. Main's separate validation recollection was 4.200026 s; initial full-suite collection was not separately instrumented. Hosted full-suite times span different machines and remain descriptive, not controlled timing proof.

## Artifact and packet custody

Main artifact ID `12040352649`, `product-coverage-f173d98f54be8616317214bb4b4ccccd2aba99fa-1`: GitHub ZIP digest and independently recomputed SHA256 are `dea8b4d7a6f6be019531bcf06a1b901e4692e932a63da1e0a320003915353249`. Gate report SHA256 is `2323a0f065e66c2fe4ffff1a4ecb68fda88c13c3b2abf1cc60187003fa18085f`; coverage SHA256 is `19c8677cb4a89d89ee7fb42c7151d8e2b069e50c13d38374e1705b168085e319`. Claude independently downloaded the original artifact and verified the source, digest, bindings, floors and exactly-one result.

Retained sealed packet manifests:

| Packet | Entries | Manifest SHA256 |
|---|---:|---|
| CP1 | 405 | `c90c52f0c3d3191a9e581baf9a52332303ef0786802c1eefa1cd9bc16c10298d` |
| CP2 pre-commit | 612 | `71e2157563f3a424e2e0cfb7c452d2a9d474bd3e75683972e825dafc3d737291` |
| CP2 committed source | 188 | `9e82d74c5dcb947a1d2b4617c61719ba6c278687a3559789d9a8fca669690683` |
| CP3 pre-merge | 172 | `a049fa95fbe55d88acaf52dc53fffe7d1c5687e642e23c833cf76501435b0f0c` |
| Actual main | 172 | `a4aea4a43968146fe227dc3060ef159eea9a0b85223b0f59d9170e7d409958c0` |

The actual-main review report SHA256 is `9cbfa84e1b4824fe3716a6b75832a480499c112a6557cc70d75d68b3862b3381`. All 172 entries were rehashed by both agents. Raw workstation packets, environments, clones and logs remain retained provenance; no build, test or future review depends on an individual workstation path. The original failed attempts, diagnostic-only runs, skipped/UNKNOWN observations, hook-cache/environment repairs and unchanged all-files secret-scan failure (683 locations in 149 pre-existing files) remain preserved without waiver or relabelling. No sealed report, manifest or evidence bytes are changed by archival.

## Archival disposition and boundaries

The operator directly authorized: "Approved: Codex may close #364 and archive the plan and evidence docs per the custody rules. Branch and worktree cleanup stays held."

The issue records the terminal disposition before repository archival. The frozen [v2 plan](../../plans/archive/2026-10-16-hypothesis-sanitizer-oracle-port_v2.md) retains SHA256 `d203eb4167ac3e204406558067b24f50d9276c7918935a7baca23a74bf7245c6`; the [pre-commit checkpoint](2026-10-16-hypothesis-sanitizer-oracle-port-checkpoint.md) retains its original bytes and explicitly dated evidence limits. Its pending-gate language and the plan's unchecked boxes remain historical snapshots; final acceptance is in the linked issue receipts and this record. Only mutable index/registry pointers change. The complete draft v1, v2 and Claude reviews remain unchanged in planning custody.

#364 has no track parent by the recorded joint decision. #316/#332 retain analysis-tool evaluation, #313 retains test-double work, and #339 retains security-text consolidation and its separate throughput observation. Evidence-policy/structured/streaming expansion and the held typing/MCP portfolio are outside this port; no follow-up implementation or parent completion is claimed. No new residual was created or silently dropped by this delivery.

Implementation branch `agent/codex/hypothesis-sanitizer-oracle-port`, the implementation lane, exact-base clone, all raw `tmp/` evidence and historical lanes remain retained. Branch/worktree/evidence cleanup, services and private-memory writes stay held. Document archival grants none of those authorities.
