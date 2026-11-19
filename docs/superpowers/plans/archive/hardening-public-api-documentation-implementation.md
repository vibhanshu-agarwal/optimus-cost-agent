# Public API documentation implementation plan

**Goal.** Document the user-approved Python import boundary for #335 and give maintainers a focused check for drift.

**Architecture.** Use one reference for the exact supported paths and selected operations. Reuse existing import paths and annotate the seven selected callable definitions using Sphinx/reStructuredText field lists. Describe schema-bearing classes and enum semantics in the reference so the documentation work does not alter generated descriptions.

**Environment.** Locked Python 3.14, uv, Ruff, pytest and Git. Baseline main `157947d298d31a48044f9fb15f218f291064a95a`. Use an isolated, clean worktree for any approved execution. Sync with `uv sync --frozen --all-extras` before commands that use `--no-sync`. Windows and WSL use separate environments on their own filesystems.

**Custody.** [#335](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/335) implements only `HARDENING-ITEM-PUBLIC-API-DOCSTRINGS` for [#322](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/322). [Masterplan acceptance row](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/157947d298d31a48044f9fb15f218f291064a95a/docs/superpowers/plans/hardening-runtime-quality-masterplan.md#L199) · [Parallel quality lane](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/157947d298d31a48044f9fb15f218f291064a95a/docs/superpowers/plans/hardening-runtime-quality-masterplan.md#L333) · [Historical source carried in #335](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/335) · [Transitional backlog checked](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/157947d298d31a48044f9fb15f218f291064a95a/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md)

The exact item identity, child filename and public-API coverage wording have no separate backlog row on this main. Two unrelated docstring references were found, including the closed launch-audit correction. #335 is the source for current work custody. The approved-boundary draft used for this plan has SHA-256 `09c860c81905b33ff4907fa31a2228421e0fcf46b8fd72cd45f2d73ec763cbca`. The 649 declared export paths and historical examples inform the work. The approved list defines the check. The pinned board key is `HARDENING-TRACK-PUBLIC-API-DOCS`, with child-plan projection `Not drafted`. `HARDENING-ITEM-PUBLIC-API-DOCSTRINGS` is the distinct child item identity.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
| --- | --- | --- | --- | --- |
| Scope | Exact import list, exclusions and Sphinx/reStructuredText convention approved | yes | Operator | Record the boundary digest and scope approval in the companion receipt before release |
| Source | Clean main and source-bound inventory and import receipt | yes | Drafter | The locked Windows check resolved all 33 names and located `ContextEngine.prepare_view` on the inspected source |
| Overlap | Path collision checked | yes | Drafter | Open draft PRs #504 and #474 touched none of the allowed paths below at inspection. Recheck before release and before committing a changed head |
| Review | Independent review of the exact child plan and disposition of findings | no | Independent reviewer | merely unauthorized until the review verdict and disposition are recorded |
| Execution | Named implementation owner and operator release for Tasks 1–2 | no | Operator | merely unauthorized |
| Publication | Commit, PR, merge, and any required full-suite CI authority | no | Operator | merely unauthorized |
| Terminal filing | Accepted delivery and separate filing and closure authority | no | Operator | merely unauthorized |

## Approved contract

| Canonical import from | Supported symbols |
| --- | --- |
| `context_engine` | `STRATEGIES`, `SUMMARIZING_STRATEGIES`, `ContractError`, `HistoryRevision`, `HistorySnapshot`, `MaintenanceCallback`, `MaintenanceRequest`, `MaintenanceResult`, `OrdinaryTurn`, `PreparedView`, `ProtectedTurnState`, `ReuseResult`, `StrategyParameters`, `SummaryCheckpoint`, `ViewLimits`, `history_digest`, `publish_checkpoint`, `reuse_checkpoint`, `turn_source_digest` |
| `context_engine.engine` | `ContextEngine`, with construction and `prepare_view` as the supported operations |
| `optimus_model_policy` | `EstimatorProfile`, `ModelEntry`, `Origin`, `Policy`, `RegistryError`, `RegistrySnapshot`, `Role`, `Tier`, `ValidationIssue`, `load_registry`, `validate_registry` |
| `optimus.telemetry` | `TelemetryEvent`, `TelemetryEventKind`, with construction and documented in-memory reads |

### Explicit Exceptions

The contract covers the bundled `optimus-cost-agent` distribution. Exclusions remain those in the approved boundary. They include other paths and symbols, deeper aliases and star imports, context memory/indexing/retrieval/storage/rendering, the other 14 model-policy facade exports and live admission/routing, and the other ten telemetry facade exports plus event factories and wire formats. Sensitive data handling, sinks, fanout, exporters and serialization retain their existing custody. All other Optimus runtime, transport, gateway, security and Evidence Handoff APIs are excluded, as are CLI, protocols, configuration tooling, tests and historical artifacts. Document constants and selected enum semantics in the reference without treating current membership or iteration order as a compatibility guarantee.

Use a one-line summary and optional contract prose, then applicable `:param name:`, `:returns:`, `:raises ExceptionType:` and `:ivar name:` fields. Keep types in Python annotations. Explain meaningful defaults, mutation, I/O and error rules. Class, data model and enum contract details belong in the reference to avoid changing schema descriptions through class docstrings. This documents missing types without requiring source edits to their definitions. No new documentation dependencies or documentation tooling is required.

## Task 0 · Release the reviewed plan

- [ ] Record the independent verdict against the exact plan digest and resolve required findings. The review row above describes the draft prerequisite. The separate receipt establishes its completion. Obtain owner release and identify the implementation owner before any implementation edits.
- [ ] Refresh main and compare the approved names, method, source files and open PR ownership. Recheck #335, #322 and the backlog if the source moves, and record the new pin even when the checked scope is equivalent. If a name or behavior contradicts the agreed scope, record the evidence and return to the owner.
- [ ] Audit the seven callables for consumers of their docstrings beyond ordinary help and reference display. Search production, tooling, tests and generated artifacts for `__doc__`, `inspect.getdoc`, callable or MCP registration, FastAPI/OpenAPI exposure, `validate_call`, docstring snapshots and schema extraction. Follow callable references, decorators and aliases into these mechanisms. Record the searched scope and observed zero consumers, or capture each consumer's exact baseline and require equivalent output after Task 1. Stop for a behavior-bearing difference.

## Task 1 · Write the reference and callable docstrings

Add `docs/public-python-api.md` and index it once by relative path in `docs/README.md`. The guide owns the canonical import table with exactly 33 explicit module-and-symbol rows, a separate `ContextEngine.prepare_view` operation entry, the approved exclusions, and contract text by group. Use the heading `## Supported import paths` and a two-column Markdown table with `Import from` and `Symbol` headers. Use backticked values in both cells and give each pair its own row. Follow with a separate `## Supported operations` section with one bullet containing `ContextEngine.prepare_view`. These are the only inputs to the reference check. Describe context-engine and telemetry construction in the group prose.

The following are the only Python source write paths. Limit writes to the leading docstring on each named definition and preserve every other source token outside the authorized docstring spans.

| File | Definitions | Contract points |
| --- | --- | --- |
| `src/context_engine/contracts.py` | `history_digest`, `turn_source_digest` | State which ordinary or protected source records are inputs. Limit deterministic behavior to the same version and identical inputs. Algorithm, encoding, cross-version or cross-platform digests and persistence are outside the promise. |
| `src/context_engine/checkpoints.py` | `publish_checkpoint`, `reuse_checkpoint` | Explain authority/revision, strategy and cancellation checks. Explain refusal and return values. The host owns storage. |
| `src/context_engine/engine.py` | `ContextEngine.prepare_view` | Explain sanitized immutable source records, input bounds, exact protected state, callback/cancellation and unavailable results. It returns a candidate view. |
| `src/optimus_model_policy/registry.py` | `load_registry` | Explain caller-supplied paths, override order, provenance, file-read exceptions and the distinction between YAML/schema errors and structural findings. YAML format and schema remain with the existing owner. |
| `src/optimus_model_policy/validation.py` | `validate_registry` | Explain ordered structural findings and what an empty tuple means. The result supplies no route authorization. |

- [ ] Write reference coverage for each approved symbol. Describe documented reads on returned policy snapshots, context host responsibilities and the telemetry fields already named in `TelemetryEvent`'s `:ivar:` list. Cover correlation, validation and shallow freezing while keeping per-kind payload shapes outside the commitment. Explain `TelemetryEventKind` as the discriminator with current member meanings, without fixing its membership or order. Keep all model, dataclass and enum class docstrings untouched. Document `TelemetryEvent` and `TelemetryEventKind` in the reference only. Keep event factories and serializer semantics outside the public documentation commitment.
- [ ] Include representative safe usage for context view preparation, local registry read/validation and in-memory telemetry construction. Use fixed synthetic data or a temporary fixture, a maintenance callback that needs no live provider, and a telemetry example with no secrets. The registry example accepts a caller-supplied file, and verification may supply the tracked `src/optimus_model_policy/defaults.yaml` fixture without making that path public. Describe the stable outcome and exclusions in the same section.
- [ ] Independently inspect the staged diff against the five-file, seven-definition docstring allowlist. Require `git diff --name-only` under `src/` to match the five files in the table. In both trees strip only the first string-constant expression of each of the seven named definitions when present. Compare `ast.dump(..., include_attributes=False)` and the remaining tokens including `COMMENT`, ignoring only positional data and docstring-line trivia. Require no new definition or module/class docstring change. Confirm import facades, models, schema metadata, configurations and dependencies were untouched. Record the checked definitions and any intentional line movement in the receipt.

## Task 2 · Verify reference coverage and existing behavior

- [ ] Add `tests/unit/docs/test_public_python_api_reference.py`. Compare the reference table to the independently pinned 33 pairs from this plan and compare its separately-listed method to `ContextEngine.prepare_view`. Require exactly one of each heading, the expected headers and backticked cells, 33 unique pairs in exact bidirectional agreement, and exactly one operation entry. Check missing, extra, duplicate and wrong-module rows and a duplicate heading as negative controls. Resolve the 33 bindings and callable method with `subprocess.run([sys.executable, "-c", …], check=True)` in each synced environment. Run from a disposable directory with `PYTHONPATH` unset, and confirm imported files come from the expected installed checkout. Do not derive expectations from `__all__`.
- [ ] Use exactly three named fenced Python examples under `## Examples`, headed `### Context view`, `### Registry inspection` and `### Telemetry envelope`. Execute the exact fences in the focused reference test in a temporary directory with an offline callback and a fixture copy of `defaults.yaml` named `registry.yaml`. The registry example uses `Path("registry.yaml")` as its caller-provided input. Assert the view availability and retained authority, successful registry load and repeatable validation, and the in-memory event's correlation default. The source location of the fixture is test-only. The telemetry example does not serialize or publish the event.
- [ ] Review every material guide and docstring claim against current source and a listed focused test or the corresponding executable example. Qualify or omit anything beyond that evidence. Match documented exception types and ordinary failure outcomes to source. Preserve unsupported wire behavior as out of scope.

| Claim or callable | Existing focused evidence on the pinned tree |
| --- | --- |
| `history_digest`, `turn_source_digest`, and source-record invariants | `tests/unit/context_engine/test_checkpoints.py::test_every_protected_fact_is_part_of_the_history_digest`, `::test_every_ordinary_field_is_part_of_the_source_digest`, `::test_malformed_snapshots_are_validation_failures`. The callable implementations provide the narrow same-version determinism statement. |
| `reuse_checkpoint` and `publish_checkpoint` | `tests/unit/context_engine/test_checkpoints.py::test_an_append_only_prefix_is_reused_and_rekeyed_to_the_current_revision`, `::test_a_current_uncancelled_candidate_publishes`, `::test_a_stale_or_cancelled_candidate_never_publishes`. |
| `ContextEngine.prepare_view` and maintenance/view outcomes | `tests/unit/context_engine/test_strategies.py::test_authority_that_cannot_fit_makes_the_view_unavailable_without_any_call`, `::test_authority_is_never_sent_to_maintenance`, `::test_a_result_that_arrives_after_cancellation_is_discarded`. That module calls `ContextEngine.prepare_view` directly. |
| `load_registry` and `validate_registry` | `tests/unit/model_policy/test_registry.py::test_the_fixture_policy_loads_and_orders_by_price_dominance` calls `validate_registry` and checks an empty tuple. `::test_crossed_prices_need_a_declared_role_blend` covers structural findings. `::test_override_maps_combine_by_key_and_lists_replace` and `::test_an_override_is_validated_like_the_defaults` cover loader behavior. |
| In-memory `TelemetryEvent` envelope and discriminator | `tests/unit/telemetry/test_events.py::test_direct_trace_id_is_preserved_and_missing_trace_defaults` covers direct construction. `::test_acp_turn_settlement_rejects_forbidden_payload_keys` supplies a validation negative control only. |

- [ ] Run only the named paths below locally and record command, interpreter, source tree and results. Use locked native Windows and WSL for the import check. Record platform skips. Do not run a local full suite or manually rerun a full workflow. If a future normal commit profile selects a broad run, stop and resolve coverage authority with the operator.

```text
uv run --frozen --no-sync pytest -q tests/unit/docs/test_public_python_api_reference.py tests/unit/docs/test_docs_index.py
uv run --frozen --no-sync pytest -q tests/unit/context_engine/test_boundaries.py tests/unit/context_engine/test_checkpoints.py tests/unit/context_engine/test_strategies.py tests/unit/model_policy/test_registry.py tests/unit/telemetry/test_events.py
uv run --frozen --no-sync ruff check .
```

- [ ] Record a compact per-symbol coverage receipt with canonical path, reference anchor and relevant proof. Independently verify the source diff, reference and focused receipts before requesting the separately authorized publication of Tasks 1–2. Required PR checks and CI on the actual implementation merge are explicit release evidence. Any required full-suite CI needs the operator's release.

## Task 3 · Acceptance and terminal filing

- [ ] Keep the child plan local until separately authorized filing. Use `Master-plan impact: none: #335 delivers the approved public Python reference and docstring coverage without changing the masterplan or filing its child plan.` for the implementation PR with the exact Tasks 1–2 paths. After reviewed implementation and exact main CI are accepted, record the source-bound evidence in #335 and close it as completed only on the operator's release. Confirm the #322 board scope, GitHub sub-issues and linked owners have no other open child obligations. Obtain separate release for the filing PR and #322 closure.
- [ ] In that filing, add `docs/superpowers/plans/archive/hardening-public-api-documentation-implementation.md` with terminal evidence. Update `docs/superpowers/plans/hardening-runtime-quality-masterplan.md` so only the #322 child-plan row becomes Complete and links the archived plan. Preserve all other rows and frozen G6/G7 entries. `docs/README.md` indexes the current public reference, and the board serves as access to the archived plan.
- [ ] Update only the expected board membership in `tests/unit/docs/test_plan_directory_hygiene.py::test_hardening_masterplan_owns_exactly_fifteen_child_plan_statuses`. Add `HARDENING-TRACK-PUBLIC-API-DOCS` to Complete and move the expected Not drafted count from 10 to 9 if that is still the verified baseline. Reconcile any intervening authorized status changes before applying this single-row delta.
- [ ] Check the terminal filing with `uv run --frozen --no-sync pytest -q tests/unit/docs/test_docs_index.py tests/unit/docs/test_plan_directory_hygiene.py tests/unit/tools/test_verify_masterplan_impact.py`. Use `Master-plan impact: updated — HARDENING-TRACK-PUBLIC-API-DOCS` for the filing PR. Verify the actual main filing and applicable required CI, and close #322 as completed with a source-bound receipt. The GitHub issues own work status, and the masterplan owns child-plan projection.

## Terminal filing evidence — 19 November 2026

The reviewed contract above is retained byte for byte as the prefix of this first
repository filing. Its original SHA-256 is
`4254e0cd3b1f5e8fc998cc882aad13af0dc6ea96cf8984208c25c0077533df0d`.
Its unchecked authoring checklist and prerequisite observations are historical;
the verified task dispositions below record the accepted delivery without rewriting
the reviewed contract. This section adds evidence, not implementation scope.

- [x] Tasks 0–2 delivery accepted in [#335's completion record](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/335#issuecomment-7014694399).
  [PR #510](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/510)
  merged reviewed head `e7497b0b57b80de78faa107a9709f8c29be37554` as
  `9d0c3e54a9be113a19cace43a03bcaa33e44e5ce`. The eight delivered paths matched
  the reviewed head byte for byte. The public reference covers 33 canonical import
  pairs, the selected operation and three executable offline examples; only seven
  callable docstrings changed across the five approved source files.
- [x] Implementation evidence accepted: native Windows and WSL each passed 291
  focused tests (15 documentation/reference and 276 contract tests), 33 fresh
  interpreter imports plus the selected callable, and Ruff. The fresh interpreter
  checks were separate evidence commands rather than child launches in the tracked
  reference test. Signature and representative schema comparisons matched, and
  docstring-stripped AST/token comparisons preserved the remaining source. WSL did
  not claim the native Windows process-guard capability. These are #335 delivery
  results, not new runs for this filing.
- [x] [Independent implementation review](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/335#issuecomment-7012907814)
  passed the published head; its requested source confirmations were resolved before
  the completion record. [Required PR guardrails](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/44549341000)
  and [exact implementation-merge guardrails](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/44556372601)
  passed. The latter recorded 13,413 passed, 331 skipped, 394 deselected and two
  warnings, with required coverage floors and same-run validity passed. That CI
  proves the implementation merge, not a later filing merge.
- [x] Task 3 custody checked against refreshed main
  `9d0c3e54a9be113a19cace43a03bcaa33e44e5ce`: #322's only GitHub sub-issue is
  #335, closed as completed; #335's parent is #322. The masterplan acceptance,
  scope and issue-mapping rows assign only `HARDENING-ITEM-PUBLIC-API-DOCSTRINGS`
  to this track. There are no additional open child obligations in that scope.

This filing changes only this archived plan, the masterplan's
`HARDENING-TRACK-PUBLIC-API-DOCS` child-plan row and its exact hygiene-test
expectation. The verified board baseline is four Complete, one Active and ten
Not drafted; this single-row transition makes those five, one and nine.
All other board rows and frozen G6/G7 records remain unchanged. The current
[public Python API reference](../../../public-python-api.md) and its
[documentation index](../../../README.md) remain in place unchanged.

The [#322 issue](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/322)
owns publication and closure evidence. Before closing it, verify this actual filing
on main and its applicable required CI, then post a receipt bound to that merge.
The board records the accepted child-plan delivery; it does not substitute for
GitHub issue state or assert that filing publication has already happened.