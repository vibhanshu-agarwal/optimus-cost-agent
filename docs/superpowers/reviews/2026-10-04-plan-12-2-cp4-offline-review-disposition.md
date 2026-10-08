# Plan 12 — consolidated CP4 offline disposition

2026-10-04. Codex, Senior Architect/reviewer. No product code or tests implemented. Review scope: `dea4624..cf9bb9d`, the sealed final return, Fable's review and Claude's disposition. **The offline implementation batch is technically accepted within its disclosed scope. Full CP4 remains OPEN.**

## Candidate and verified evidence

The clean local candidate is `cf9bb9d73ac6c8c3be508966245e0db7cdaaa503`, branch `agent/claude/plan12-context-engine-cp4`. Main `a929aab` was integrated locally through `739b3dc`; this review makes no new remote-drift claim and performs no fetch. No publication, merge or activation follows.

Independently verified all **77 payloads**, with **zero mismatches**, against `cp4-release/MANIFEST.sha256`: `23efd63fc29bcbe7c45c679f10b5bb22826bb1ca3bfe5165d4411756e38e1296`. Final return SHA-256: `734193336243b6ac620d77ea30c767bd1469852960c0e44be65297c047935d94`. Retained gate records identify the same clean candidate, fixed full pytest command, true exit and dataset hash; logs retain actual selection/run-context and counts. See `evidence-verification.json` for the architect's independent checks.

| Evidence | Candidate | Verified result |
|---|---|---|
| Windows final-gate-2 | cf9bb9d | Exit 0; 6830 passed, 0 failed, 39 skipped, 111 deselected, 1 warning; 1:10:40 |
| WSL wsl-full-1 | cf9bb9d | Exit 0; 6641 passed, 0 failed, 228 skipped, 111 deselected, 1 warning; 40:09 |
| Required coverage, Windows | cf9bb9d | Optimus group 89.4393%; context_engine 95.9243%; optimus_model_policy 96.9880% measured |
| Required coverage, WSL | cf9bb9d | Optimus group 88.9078%; context_engine 95.9243%; optimus_model_policy 96.9880% measured |
| Limits | cc6959b | Zero proposal violations; max_repacks=1; planning material 43795 bytes; D7 upper bound 185581 bytes/35.40% |
| Independent wheel proof | cc6959b | Exit 0; wheel SHA-256 `13b061327ee677b912578aa0e96185f87f6d9fd65a7a1fbd4f85a0e6bc1ffd36`; shipped effective registry hash unchanged |

Limits/wheel evidence carries only over unchanged `src/`, `pyproject.toml` and lockfile inputs: the final commit changes tools/tests. It does not become a wheel build at cf9bb9d. Evidence Handoff is below its informational 80% threshold on both systems; that is reported as BELOW, not passed. Aggregate coverage remains informational.

The failed `final-gate-1` remains failed (3 failed, 6807 passed); its walker violation and two frozen-lane regressions were corrected before the final runs. Wrong-path no-op logs and the stopped tools run remain non-passing. WSL's port-6379 positive control and one existing TCP reachability probe were blocked; the probe issued no Redis command. This does not establish general network isolation or Windows job-control parity. No new product full-suite run was performed by Codex.

## Five requested rulings

1. **M2: retain the established rounded comparison.** The installed coverage.py `should_fail_under` returns `round(total, precision) < fail_under`; pytest-cov's exit-decision path calls it. Fable's claim that the previous gate/interim hook use an unrounded exit comparison is incorrect. At precision 0, 79.5% compares as 80% and passes; 79.0% fails. Keep both measured and compared values visible. The final required measurements exceed 80% even unrounded, so no result depends on this boundary. This is an explicit technical disposition preserving the established semantics, not a silent claim of an unrounded floor. No code change or rerun is requested.

2. **Secret-scan remedies: accept the narrow changes.** Moving the two new telemetry tests into their own file avoids touching unrelated old fixtures; it does not waive scanning. The runner has five line-scoped markers on existing public commit/fixture/task identity pins, not credentials. Independently checked that removing those comments leaves the same AST and that the identity values match cc6959b. The actual runner guard/import are intentional functional changes; the AST claim applies only to the markers. No scanner baseline, hook or broad exemption is changed.

3. **Frozen Plan 9.88 verifier and runner guard: accept.** The common checker defaults to the current product prompt for Plan 9.87. The Plan 9.88 bridge supplies the fixed lane version, then validates the original summary's own version, lane, predicate, ranges, operator provenance and existing evidence claims. It does not take an arbitrary caller-selected prompt version. The runner refuses both new preregistration/capture paths once the product prompt differs; read-only validation remains available. Historical evidence is preserved without mislabelling a new prompt run as that frozen lane. The final full runs include the corrected regressions.

4. **No `run-gateway` profile flag: accept.** A profiled host must obtain its own profiled child through the trusted launch and authenticated manifest path. An already-listening/external Gateway or failure to obtain a child refuses with `TEST_PROFILE_GATEWAY_NOT_STARTED`. Parsing rejects `--no-auto-start`, `--framed` and `--strict`; an incompatible explicit model refuses before Redis/Gateway/server. A standalone profile flag would have no accepted adoption path. Non-strict config inspection is not enforcement proof. Before any later live run, deliberately resolve a conflicting Gateway under that run's service authority; this review does not authorize stopping it.

5. **Documentation split: resolved and acted on.** Codex supplies corrected complete successor sources, the rebuilt Architecture/HLD v2.19, LLD v2.42, Guardrails v1.4 and Test Strategy v1.8 PDFs, migration map and this disposition. Claude owns repository filing/verification under the existing human offline local-filing release. No install in Claude's environment is needed. The new packet preserves sealed predecessors and review editions unchanged and uses the bundled reviewer runtime. Its PDFs are complete reviewed local filing candidates; they do not assert publication, operator decision provenance or production activation.

## Other findings and evidence limits

Accept the reviewed M1, m1–m6 and associated NIT fixes. The repack case now refuses because one repack is insufficient while two fit, and the proposal/checker actually carries max_repacks. Wrapped maintenance proof goes through HostMaintenance/GatewaySummarizerCall. Approval wording now names the HMAC launch security-snapshot binding; the internal literal consistency check is not a second operator approval. No-cap product telemetry and explicitly capped evaluation retain their distinct semantics.

**M7's minimal provenance is sufficient for these externally verified final clean runs.** HEAD plus a dirty flag does not identify uncommitted file contents. The report-mode sidecar validates dataset identity, but does not authenticate selection or capture/compare a complete configuration/tree digest. Do not claim otherwise. This disposition deliberately replaces V2's richer proposed sidecar schema with the implemented minimal record plus external review of its corresponding sealed log/run context and unchanged source/configuration. Report mode is for a trusted known full-run record, not arbitrary JSON. Future profile-provenance automation belongs to the Test Strategy successor lane; no new CP4 product batch is commissioned for the current already-verified evidence.

Keep the two disclosed NITs: the meter records at local Gateway dispatch before the response, so a non-capacity Gateway rejection can leave a reading without provider delivery; CI's per-floor rows are retained in logs but JSON report upload is not implemented. Documents now describe those precise limits. Known INPUT_EXCEEDS_CAPACITY alone selects the capacity message; unknown CAPACITY_REFUSED remains generic.

## Filing and remaining closure

Claude's remaining documentation work is concrete: file the corrected complete sources/PDFs under the existing local-filing release; allocate ADR IDs from the then-current index; preserve predecessors; restore the three historical-edition references (roadmap PR #214, backlog 2026-10-02 acceptance, plan acceptance sentences); and record the existing internal cancellation diagnostic limitation. Do not rewrite sealed evidence or imply the new editions inherited an older acceptance. The saved ADR-011 session export is needed to insert Vibhanshu's exact D7 words; the placeholder is not an approval record. A documentation-only filing does not require another product full suite.

**Correct the final return's closure sentence:** CP4 does not clear merely when documentation is filed. Real route/estimator eligibility, a genuine summary-quality receipt and real-editor Task 13 remain required and UNRUN unless Vibhanshu separately records a specific disposition. Luna stays ineligible; Qwen stays unqualified. A synthetic positive profile is process/boundary evidence only.

Paid/live ceilings remain proposals on hold: qualification US$0.05/four physical attempts, editor US$0.50/24 attempts, combined US$0.55/28. Even later spend approval cannot substitute for missing eligibility. Production activation, shipped Haiku-default removal, sandbox synchronization, push, PR and merge remain held. This disposition grants none of them and sends no message to another chat.
