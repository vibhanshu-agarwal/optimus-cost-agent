# #361 specification and implementation validation

This is a dated evidence record, not the work register. [#361](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/361) owns current acceptance, review, CI and completion; subsequent records retain their own source identities. Production changes descend from main `43e5e5b415140a17005045d3d21c6de2ed8595b3`. Local runs below are dirty-tree development evidence; they do not claim a clean final commit or full-suite acceptance.

## Document inputs and outputs

The immediately preceding HLD v2.24, LLD v2.47 and Test Strategy v1.10 were rebuilt byte-for-byte from the complete Plan12.9 bundle before applying 21 exact edits. Predecessor SHA-256 values are respectively `cfd627f2cc5c3c026072940590f535a8c65c282c26fd19f0ed14893e6f3852c5`, `e8e42bb59dcdcfe17f297ad968854950e8bca3babfaad440221ef1a649ba0d51`, and `e9346917c705099631d3b171fa70da130ad17619e496802675701ec8b0bab95a`. Archived predecessors retain those bytes. Covers qualify the narrow #361 refresh; all carried claims retain their own earlier pins and failed/skip/UNRUN/reused/warning limits.

The filed `build-manifest.json` identifies every complete successor output, its source hashes, native-baseline page mapping and complete predecessor-page coverage. `document-validation.json` reports no failures for all three documents: manifest/page count, contiguous mapping, carried native bodies, predecessor hashes/page coverage, page label/footer and escape-artifact checks. Source derivation independently reproduced all ten complete inputs from the exact edit ledger. Toolchain: Python 3.14.4, ReportLab 5.0.0, pypdf 6.10.2, installed Windows Arial fonts and Poppler.

Codex visually inspected contact sheets and changed pages: HLD 1/13/14/15/24/25; LLD 1/2/4/34/41/58/59; Test Strategy 1/2/5/22/23. No clipping, overprinting or broken tables was observed. Private rendered images and raw local run records are archival evidence, never a contributor's required build/test dependency. Historical font CMap warnings appeared during a separate text-inspection attempt; exact predecessor reproduction and the filed validator still passed.

## Local checks and qualifications

| Run / scope | Observed result | Interpretation |
|---|---|---|
| `baseline-windows`: original core four-file unit selection | 137 passed, exit 0 | Clean starting code; active default selection, valid Windows native job, full process-guard protection, COMPLETE records; parent UNKNOWN retained. |
| `red-core` | Six expected failures, four passed, 94 deselected | Missing Tavily still hid metadata; absent web direct handlers returned validation errors. |
| `red-bounded` | Exit 5; zero selected, 62 deselected | Unsuccessful selector attempt retained; not RED acceptance. |
| `red-bounded-selected` | Two expected failures, five passed | Actual builder lacked a metadata-only bundle in both web paths. |
| `green-core` | 166 passed, exit 0 | First production fix; active/default, native valid, full Windows protection, COMPLETE records; source unchanged during run. Later extra guard tests are covered by the scoped run below. |
| `windows-policy` | 64 passed, exit 0 | Existing policy/state/provider regression controls; no live tier. |
| `focused-docs` | One failure, 27 passed | Index rejected a new external-link form; corrected locally without changing index tests. |
| `focused-docs-corrected` | 28 passed, exit 0 | Index, directory hygiene, relocation-equivalence and both Gateway example readers. |
| `windows-scoped-coverage` | **237 passed; exit 1, 75.85% scoped coverage below 80%** | Denominator is only `providers.py`, `tool_handlers.py`, `server.py`; untouched server routes account for the shortfall. Every added executable production statement was covered. The threshold failure is retained, not called green or repository aggregate acceptance. |
| `windows-mypy` | Five missing optional imports in three unrelated modules | Dev-only environment lacked locked memory/index extras; this is an environment failure, not a hidden passing result. |
| `windows-mypy-with-memory` | Success, 287 source files, exit 0 | Existing locked memory extra installed into the isolated environment; dependency files unchanged. |
| Ruff and whitespace check | Passed | No hook bypass or local full suite claimed. |
| Initial WSL attempt | Exit 3 during collection; no tests ran | Windows-format Git-worktree pointer fails after root conftest deliberately removes inherited GIT_* overrides. Harness protection remains unchanged; independent native-Git verification checkout prepared instead. Successful alternate-checkout results, once available, belong to their own follow-on evidence record. |

Windows checks use the checkout's frozen dev environment (Python 3.14.4); Mypy's final run adds the existing locked memory extra. WSL uses an independent frozen Linux dev environment (Python 3.14.6), never the Windows environment. A WSL hardlink-to-copy warning, Git CRLF-to-LF warnings and the unsuccessful setup/selection attempts are retained. Linux functional evidence must not imply Windows native protection parity.

Exact local commands, before/after HEAD/status/diff hashes, interpreters, configuration/lock identities, stdout/stderr, exits and test-run-context records are retained separately. Source changed during none of the reported completed runs. The approved plan's initial bytes remain in the delivered Plan11.33 file; the two verbatim plan reviews and adoption record are posted to #361. A separate operator-approved [receiving-custody note](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/362#issuecomment-6953756630) places the unchanged extract-independence target in #362.

## Acceptance boundary

Only configuration/dispatch independence is implemented and locally exercised. The config-built positive test uses real package/OSV providers against a loopback HTTP fixture through configured base URLs, replacing only Redis's state factory. Direct and bounded HTTP tests cover both disabled web routes, auth/domain/cap/failure controls and model fallthrough exclusion. These fixtures are not live provider/Redis evidence. Test Strategy's real release gate remains UNRUN.

No local full-suite rerun is part of this record. Final-head PR CI and actual-merge CI must supply their own full-suite coverage gate, validity, source/tree and qualifications before acceptance/closure; no earlier PR head, synthetic merge or this focused dataset substitutes for actual-merge evidence. Branch/worktree cleanup and live probes remain prohibited.
