# Plan 11.24 v6 — Committed-Prerequisite Applicability and Contract-Repair Amendment

> **Status (authoring):** Proposed forward-only Plan 11.24 amendment. When this file lands in
> `main`, it becomes the sole live Plan 11.24 contract and must land before PR #184's Cursor repair
> round. It authorizes only the offline implementation and verification tasks below. It does not
> authorize Task 13, `acpx`, a TTY approval, a keyring mutation, Zed, Redis, Gateway/provider
> traffic, a paid turn, a commit, a push, or a merge.
>
> **Frozen predecessors:** Leave all five predecessor files byte-identical:
>
> - `docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe.md`, git blob
>   `421f9a9595dda1d55b9895b148839de8163e6556`;
> - `docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe_v2.md`, git blob
>   `85cea53cbec6ca9faf1cee85f5c81e15999321b8`;
> - `docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe_v3.md`, git blob
>   `220000b208059030488c920fef3f15e9f8834e89`;
> - `docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe_v4.md`, corrected
>   PR #180 blob `260ad5dc692e03601d48c6f1713238de4fa5c164`; and
> - `docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe_v5.md`, git blob
>   `f8f239a21dfbbc09591bcaae22eeefa8a3f7eee1`.
>
> **Authoring baseline:** `origin/main` at
> `213710d8d2fce5911f167123590549dd2533721d`. The rejected implementation baseline is PR #184
> head `6f9a7d66896358ff249e2a67100630c9c6c9fb9e`. That head is evidence for the RED baseline, not
> authority to run Task 13 or either Zed lifecycle.
>
> **Required implementation workflow:** Use `superpowers:test-driven-development` for each repair
> task and `superpowers:verification-before-completion` before any completion claim. Read the Plan
> 11.24 reviewer checkpoint Current State before mutation and verify it against the actual branch.

## Goal

Make the committed Task-13 establishing report a durable, reconstructable, fail-closed prerequisite
for Task 14 without requiring the report-producing commit to equal the later execution commit.
Repair the remaining Task-12/13/14 contract gaps at the same time: a genuine erroring
`session/prompt`, same-session correlation, exactly one Lifecycle-A message, complete typed report
facts, a dedicated 24-hour freshness policy, and durable contract-negative tests.

## Architecture

Task 13 binds its completed premise to three independent identity layers:

1. a source commit retained as provenance and required to be an ancestor of the later Task-14 HEAD;
2. a deterministic SHA-256 manifest over raw Git blob content for the explicit execution surface;
3. external/runtime identities for the interpreter, the actual `acpx` JavaScript CLI entry,
   the trust executable, the canonical isolated launcher template, and the deterministically
   patched isolated `spec.py`.

Task 14 recomputes those identities before any approval or Zed launch. A report-only descendant
commit is allowed because its execution-surface manifest is unchanged. A source change, dirty
execution file, uncommitted/dirty report, non-ancestor report, stale/malformed timestamp, or runtime
identity mismatch rejects with `INDETERMINATE / PRECONDITION_UNMET` and `zed_launches: 0`.

## Tech stack

Python 3.14+, `git cat-file`, `git merge-base`, `pytest`, `pytest-asyncio`, `uv run --frozen`, Ruff,
the existing Plan 9.96 persistence-surface verifier, the independently authored `acpx` binary, and
the existing Plan 11.17 relay/verifier. Unit tests stub all live/process/approval boundaries.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| plan/state | `_v5` is present on `main` at blob `f8f239a21dfbbc09591bcaae22eeefa8a3f7eee1`; v1–v5 remain immutable. | yes | Codex + reviewer | n/a |
| code/state | PR #184's Task-12/14 implementation has the accepted v6 authority, premise, report, one-message, and durable-negative repairs. | no | Cursor implements; Codex reviews | genuinely absent; this amendment makes the repair schedulable now. |
| code/state | The repair branch is cut/rebased from `main` only after `_v6` lands; it does not continue against a moving contract. | no | Cursor + operator | merely unauthorized until this plan is reviewed and merged. |
| source/state | Every path in `ESTABLISHING_EXECUTION_GIT_PATHS` is tracked, exists at the source commit, and is clean in index and worktree before Task 13 and Task 14. | unknown | implementing agent + operator | merely unauthorized; Task 15 establishes this offline, and dirty state is a terminal precondition failure rather than implicit cleanup authority. |
| tooling/binaries | Local Git supports `cat-file`, `rev-parse`, and `merge-base --is-ancestor`; `uv run --frozen` uses the committed `pyproject.toml`/`uv.lock`. | yes | implementing agent | n/a; unit tests use temporary Git repositories. |
| tooling/binaries | The real `acpx`, its JavaScript CLI entry, Python interpreter, and trust executable used by Task 13 are resolvable and their version/SHA facts are recordable and recheckable. | unknown | operator | merely unauthorized to execute the establishing drive; the offline implementation records and tests the seams first. |
| services | Offline repair tests start no Zed, Redis, Gateway, Phoenix, provider, or network service. | yes | implementing agent | n/a |
| credentials/authority | Task 13 has a separately recorded one-drive/no-Zed grant and exactly one generated-workspace trust ceremony. | no | operator | merely unauthorized; no authority is implied by this plan or its implementation PR. |
| human interaction | The operator can later complete Task 13's single `y`, mandatory revoke/inspect, and the separately granted two-lifecycle Zed ceremony. | no | operator | merely unauthorized. |
| cost | Task 13 remains no-Gateway/no-provider. Any paid fallback still requires a new provider/model/message/numeric-cost grant. | unknown | operator | merely unauthorized until the no-Gateway premise is established; no fallback is authorized here. |
| live authority | A fresh committed Task-13 report passes the full v6 gate and the reviewer records the exact two-launch grant. | no | operator + reviewer | merely unauthorized; the future gates below define but do not grant it. |

An `unknown` prerequisite is resolved by its named early gate before dependent work. No failed
precondition authorizes a retry, source cleanup, report rewrite, paid fallback, or Zed launch.

## Settled rulings

- Do not delay committing the Task-13 report until after Task 14. The prerequisite must be durable
  and reviewable before live authority is considered.
- Do not drop source binding in favor of `acpx` plus launcher identities. That would leave the probe
  orchestration, parser, relay, verifier, sanitizer, agent runtime, and trust implementation unbound.
- `Source-Commit` is provenance, not an equality predicate. Task 14 requires
  `git merge-base --is-ancestor <source-commit> HEAD` and a matching applicability manifest.
- Do not use `normal_source_sha256`, the 948-file workspace digest, a `tools/**` category, or raw
  working-tree bytes as the cross-task authority identity. The current whole-workspace set includes
  203 report files and recreates the report-commit paradox.
- The applicability digest reads raw Git blob bytes. `core.autocrlf`, `.gitattributes`, and worktree
  normalization must not change its value. The report's own bytes are outside the list.
- Dirty index or worktree state on any execution-surface path rejects both Task 13 and Task 14. The
  report path may be newly written after a successful Task-13 run because it is not execution code,
  but Task 14 accepts only a clean report blob already present at `HEAD`.
- Use the neutral constant `ESTABLISHING_REPORT_MAX_AGE_SECONDS = 86_400`. Do not prefix it with a
  plan number and do not reuse `MAX_ZED_LAUNCH_TIMEOUT_SECONDS`.
- Freshness is measured from successful post-revocation/post-cleanup report completion. Accept only
  RFC 3339 timestamps ending in `Z` or `+00:00`, normalize persisted output to `Z`, and require
  `0 <= now_utc - completed_at_utc <= 86_400`; reject `-00:00`, naive, nonzero-offset, malformed,
  future, or stale timestamps.
- The 900-second total Zed deadline is independent and unchanged.
- A raw generated launcher SHA is per-run audit evidence only. The generator embeds a temporary
  source path, so raw Task-13/Task-14 launcher equality is impossible. Cross-task comparison uses a
  canonical path-placeholder launcher digest; each run still records and validates its raw digest.
- The Windows `acpx.cmd` SHA is audit-only because npm reuses the generic shim across upgrades.
  Cross-task `acpx` authority requires both `acpx --version` and the SHA-256 of the installed
  `node_modules/acpx/dist/cli.js`, following the existing Plan 11.7 target-identity precedent.
- The unnumbered post-11.x probe-harness refactor in the deferred-work backlog is explicitly out of
  scope. Do not assign it `P11-FU-nn`, schedule it in 11.x, or use this repair to refactor the CLI.

## Explicit applicability surface

The implementation exposes the following immutable tuple exactly as
`ESTABLISHING_EXECUTION_GIT_PATHS`. It is the static in-repository import closure of the probe,
relay, verifier, isolated agent entry point, and trust CLI at the rejected PR baseline, plus the two
frozen dependency-definition files. It is a literal list, not a directory glob or prose category.

```text
pyproject.toml
src/optimus/__init__.py
src/optimus/acp/__init__.py
src/optimus/acp/__main__.py
src/optimus/acp/bootstrap.py
src/optimus/acp/debug_trace.py
src/optimus/acp/dispatcher.py
src/optimus/acp/errors.py
src/optimus/acp/framing.py
src/optimus/acp/launch_approval_cli.py
src/optimus/acp/launch_approvals.py
src/optimus/acp/launch_audit.py
src/optimus/acp/launch_gate.py
src/optimus/acp/launch_policy.py
src/optimus/acp/local_gateway_secrets.py
src/optimus/acp/local_infra.py
src/optimus/acp/operator_paths.py
src/optimus/acp/preflight.py
src/optimus/acp/request_ids.py
src/optimus/acp/server.py
src/optimus/acp/shapes.py
src/optimus/acp/spec.py
src/optimus/acp/trusted_paths.py
src/optimus/agent/__init__.py
src/optimus/agent/defaults.py
src/optimus/agent/directives.py
src/optimus/agent/golden.py
src/optimus/agent/models.py
src/optimus/agent/planning_loop.py
src/optimus/agent/prompts.py
src/optimus/agent/runner.py
src/optimus/agent/state_store.py
src/optimus/agent/tools.py
src/optimus/agent/workspace_context.py
src/optimus/config/__init__.py
src/optimus/config/gateway.py
src/optimus/evidence/__init__.py
src/optimus/evidence/acquisition.py
src/optimus/evidence/domain_policy.py
src/optimus/evidence/gateway_io.py
src/optimus/evidence/ledger.py
src/optimus/evidence/models.py
src/optimus/evidence/package_advisory.py
src/optimus/gates/__init__.py
src/optimus/gates/exceptions.py
src/optimus/gates/fitness.py
src/optimus/gates/mutation_flow.py
src/optimus/gates/shadow_workspace.py
src/optimus/gateway/__init__.py
src/optimus/gateway/client.py
src/optimus/gateway/errors.py
src/optimus/gateway/models.py
src/optimus/gateway/tool_models.py
src/optimus/golden/__init__.py
src/optimus/golden/json_harness.py
src/optimus/golden/runner.py
src/optimus/golden/tasks.py
src/optimus/guardrails/__init__.py
src/optimus/guardrails/audit.py
src/optimus/guardrails/command_safety.py
src/optimus/guardrails/mcp_trust.py
src/optimus/guardrails/network_safety.py
src/optimus/guardrails/path_safety.py
src/optimus/guardrails/permissions.py
src/optimus/guardrails/pre_tool.py
src/optimus/guardrails/prompt_injection.py
src/optimus/guardrails/unicode_confusables.py
src/optimus/guardrails/validation.py
src/optimus/loops/__init__.py
src/optimus/loops/completion.py
src/optimus/loops/controller.py
src/optimus/loops/ledger.py
src/optimus/loops/models.py
src/optimus/loops/tools.py
src/optimus/mcp/__init__.py
src/optimus/mcp/client_catalog.py
src/optimus/mcp/client_config.py
src/optimus/mcp/client_disposition.py
src/optimus/mcp/client_sdk.py
src/optimus/mcp/client_supervisor.py
src/optimus/mcp/client_trust.py
src/optimus/mcp/local_ipc.py
src/optimus/mcp/runtime.py
src/optimus/net/__init__.py
src/optimus/net/https.py
src/optimus/redis/__init__.py
src/optimus/redis/async_bridge.py
src/optimus/redis/runtime.py
src/optimus/release/__init__.py
src/optimus/release/credentials.py
src/optimus/release/defaults.py
src/optimus/release/runner.py
src/optimus/retry/__init__.py
src/optimus/retry/gated_run.py
src/optimus/retry/policy.py
src/optimus/runtime/__init__.py
src/optimus/runtime/modes.py
src/optimus/runtime/mutation.py
src/optimus/runtime/state.py
src/optimus/skills/__init__.py
src/optimus/skills/invocation.py
src/optimus/skills/models.py
src/optimus/skills/registry.py
src/optimus/telemetry/__init__.py
src/optimus/telemetry/events.py
src/optimus/telemetry/fanout.py
src/optimus/telemetry/jsonl.py
src/optimus/telemetry/observability.py
src/optimus/telemetry/redaction.py
src/optimus/telemetry/redis_adapter.py
src/optimus/telemetry/redis_sink.py
src/optimus/telemetry/serialization.py
src/optimus/telemetry/subjects.py
src/optimus/tools/__init__.py
src/optimus/tools/mutation_tools.py
src/optimus/tools/policy.py
src/optimus/tools/registry.py
src/optimus/usage/__init__.py
src/optimus/usage/accounting.py
src/optimus/usage/errors.py
src/optimus/usage/ledger.py
src/optimus/usage/models.py
src/optimus_security/__init__.py
src/optimus_security/launch_manifest.py
src/optimus_security/sanitization.py
tools/plan117_custody_contract.py
tools/plan117_custody_relay.py
tools/probe_p11_zed_session_load.py
tools/verify_plan1119_zed_reprobe_evidence.py
uv.lock
```

The static root modules are exactly:

```text
optimus.acp.__main__
optimus.acp.launch_approval_cli
tools.plan117_custody_contract
tools.plan117_custody_relay
tools.probe_p11_zed_session_load
tools.verify_plan1119_zed_reprobe_evidence
```

The AST closure walker must parse every discovered module, including the bodies of package
`__init__.py` files. Parent package initializers enter the traversal stack before closure is declared
complete; merely adding their paths after walking child modules is invalid. The walker handles
absolute and relative in-repository imports plus imports nested in functions. Its result must equal
the 128 `.py` entries in the literal tuple; `pyproject.toml` and `uv.lock` are the two non-module
dependency entries. It rejects an in-repository import not present in that module subset. It also
rejects a new dynamic importer (`__import__`, `importlib.import_module`, or loader execution) unless
a future plan amendment names the exact target path. `importlib.metadata` version lookup is an
external-package query, not a dynamic project import.

Third-party packages are not silently included under “runtime dependencies.” Their cross-task
identity is the raw Git blobs of `pyproject.toml` and `uv.lock`, execution through
`uv run --frozen`, and the recorded Python executable SHA-256/version. The external `acpx` records
its version, audit-only command-shim SHA-256, and authorizing JavaScript CLI-entry SHA-256; the trust
executable records its own SHA-256. The Zed
executable/help identity remains part of the later Zed-specific grant because Task 13 does not run
Zed.

## Applicability-manifest algorithm

Use schema name `optimus-establishing-applicability-v1` and these rules:

1. Require a full 40-lowercase-hex source commit that resolves locally.
2. For each sorted, unique POSIX path above, run Git in binary mode equivalent to
   `git cat-file blob <commit>:<path>`. Hash the exact returned blob bytes with SHA-256. Do not use
   `Path.read_bytes()`, `git show` text mode, newline conversion, or a worktree file for this digest.
3. Canonicalize only
   `{"schema":"optimus-establishing-applicability-v1","files":[{"path":...,"blob_sha256":...}]}`
   as UTF-8 JSON with `sort_keys=True`, `ensure_ascii=False`, and separators `(",", ":")`.
4. `applicability_manifest_sha256` is SHA-256 of those canonical bytes. Do not include source commit,
   time, worktree path, executable path, report bytes, or run root in the digest.
5. Before Task 13 and again before Task 14, require empty output from
   `git status --porcelain=v1 -z --untracked-files=all -- <all-listed-paths>`, covering staged,
   unstaged, deleted, renamed, conflicted, and type-changed state. Also run the AST closure check
   against Git blobs at current HEAD. A failure is
   `PRECONDITION_UNMET` with zero live actions.
6. Task 13 records the full per-file array and manifest digest. Task 14 recomputes the array from
   current HEAD and requires exact canonical equality, after proving the recorded source commit is
   an ancestor of current HEAD.

The old whole-workspace before/after digest may remain as within-one-run non-mutation evidence. It
must not be copied into, substituted for, or compared as the v6 cross-task authority manifest.

## Committed Task-13 report read gate

Define
`ESTABLISHING_REPORT_GIT_PATH = "reports/plan-11-24-agent-protocol-persistence-establishing-drive.md"`.
Task 13 may create this path only after its successful drive, custody cleanup, and completion-time
capture. Task 14 must not authorize from that worktree file. Before any approval or Zed launch it:

1. requires empty output from
   `git status --porcelain=v1 -z --untracked-files=all -- <ESTABLISHING_REPORT_GIT_PATH>`;
2. requires `git cat-file -t HEAD:<ESTABLISHING_REPORT_GIT_PATH>` to return exactly `blob`;
3. reads the report only with binary `git cat-file blob HEAD:<ESTABLISHING_REPORT_GIT_PATH>`;
4. decodes that committed blob as strict UTF-8, rejects CRLF and malformed/duplicate typed-record
   blocks, and parses the single canonical JSON object; and
5. never falls back to `Path.read_text()`, loose prose markers, an untracked report, a dirty tracked
   report, the index, or another revision.

The report blob is deliberately outside `ESTABLISHING_EXECUTION_GIT_PATHS`, so its own commit may
advance HEAD without changing the execution manifest. Being outside that manifest does not make it
optional: absence from `HEAD`, any worktree/index delta at the report path, or blob-read failure is
`PRECONDITION_UNMET` with `zed_launches: 0`.

## Canonical isolated identities

- Refactor launcher generation into one pure renderer. Rendering with the reserved source token
  `<ISOLATED_SOURCE_ROOT>` produces `isolated_launcher_canonical_sha256`; rendering with the actual
  resolved run root produces the launcher file and its per-run `isolated_launcher_raw_sha256`.
- Before invoking the launcher, require its bytes to equal the pure renderer's actual-path bytes and
  require canonicalization through the renderer to equal the fixed canonical digest. Do not perform
  an unrestricted string replacement over the written file.
- Compute `isolated_patched_spec_sha256` by loading the source `src/optimus/acp/spec.py` Git blob and
  applying only `DEFAULT_PROBE_PATCH_PLAN` as byte-exact, single-occurrence replacements in memory.
  Write the result with `Path.write_bytes(expected_patched_spec_bytes)` and no text/newline layer;
  `Path.write_text()` is forbidden for this patch. Require the isolated on-disk bytes to equal the
  expected bytes before either drive proceeds. This keeps the Git blob's LF bytes unchanged on
  Windows instead of translating them to CRLF.
- Compare the canonical launcher digest and patched-spec digest across Tasks 13 and 14. Record both
  raw launcher digests for audit, but never compare raw Task-13 and Task-14 launcher digests.

## Task-13 committed report schema

`reports/plan-11-24-agent-protocol-persistence-establishing-drive.md` contains fixed prose plus one
machine-readable canonical JSON object under `## Typed reconstruction record`. The guard parses the
JSON object, never loose prose labels. It uses schema
`plan-11-24-agent-protocol-establishing-v2` and contains at least:

```text
schema: Literal["plan-11-24-agent-protocol-establishing-v2"]
establishing_disposition: Literal["NO_GATEWAY_PATH_ESTABLISHED"]
completed_at_utc: AwareUtcIso8601ZOrPlus00
authority:
  source_commit: LowercaseHex40
  source_commit_execution_surface_clean: Literal[true]
  applicability:
    schema: Literal["optimus-establishing-applicability-v1"]
    files: list[{path: one of ESTABLISHING_EXECUTION_GIT_PATHS, blob_sha256: LowercaseSha256}]
    manifest_sha256: LowercaseSha256
  python_version: NonEmptyNormalizedString
  python_executable_sha256: LowercaseSha256
  acpx_version: NonEmptyNormalizedString
  acpx_command_sha256: LowercaseSha256AuditOnly
  acpx_cli_js_sha256: LowercaseSha256
  trust_executable_sha256: LowercaseSha256
  isolated_launcher_canonical_sha256: LowercaseSha256
  isolated_launcher_raw_sha256: LowercaseSha256
  isolated_patched_spec_sha256: LowercaseSha256
counts:
  zed_launches: Literal[0]
  origin_a_launches: Literal[0]
sequence:
  session_new:
    request_id: SafeScalar
    session_id: SafeNonEmptyString
  session_prompt:
    request_id: SafeScalar
    session_id: SameSessionId
    request_count: Literal[1]
    message_sha256: Sha256OfExactFixedMessage
    outcome: Literal["error"]
    response_id_matches: Literal[true]
    error_code: SafeScalar
  session_load:
    request_id: SafeScalar
    session_id: SameSessionId
    response_id_matches: Literal[true]
    result: Literal[{}]
traffic:
  gateway_attempted: Literal[false]
  provider_attempted: Literal[false]
  model_call_attempted: Literal[false]
custody:
  approval_created: Literal[true]
  approval_revoked: Literal[true]
  post_revoke_inspect_exit_code: Literal[1]
cleanup:
  throwaway_root_removed: Literal[true]
```

All three session ids must be equal. Request/response ids must correlate within their exchanges.
The applicability `files` array has exactly 130 entries in the literal order above, with no missing,
duplicate, or extra path. Every symbolic type in the shape is validated before authorization:
`LowercaseSha256` is exactly 64 lowercase hex characters, `SafeScalar` is a sanitized string or
integer JSON scalar, and `AwareUtcIso8601ZOrPlus00` accepts only `Z` or `+00:00` input and
canonicalizes persisted output to `Z`. `LowercaseSha256AuditOnly` is recorded but cannot satisfy an
authority comparison without the matching `acpx_cli_js_sha256` and `acpx_version`.
The prompt error must be a captured protocol response; a nonzero `acpx` process exit, missing
response, fabricated sentinel, successful prompt, or result-plus-error object is insufficient. The
fixed message itself, raw stdout/stderr, absolute paths, session content, approval identifiers, and
credentials never enter the report. Only the message SHA-256 is persisted.

Set `completed_at_utc` after approval revoke/inspect and throwaway cleanup succeed, immediately
before atomic publication. A failed disposition may write a sanitized diagnostic sidecar, but it
must not publish an authorizing v2 report.

## File map

| Path | Required change |
|---|---|
| `tools/probe_p11_zed_session_load.py` | Add the neutral freshness constant, 130-path Git-blob applicability/clean-tree/ancestor gate, committed-report blob reader, `acpx` CLI-JS identity, canonical launcher, byte-exact patched-spec identity/writer, strict Task-12 sequence predicate, typed Task-13 report writer/parser, and enforced Lifecycle-A message seam. Keep helpers capability-named; add no new plan-numbered utility module. |
| `tests/unit/tools/test_probe_p11_zed_session_load.py` | Add genuine RED tests for each absent repair plus durable parameterized authority, premise, report, timestamp, identity, dirty-tree, and message-seam negatives using temporary Git repositories and stubbed process boundaries. |
| `tools/verify_plan1119_zed_reprobe_evidence.py` | Preserve legacy/v3/v4 acceptance; make v5 verification require the enforced message/correlation facts and exact conditional v5 file/launch/profile/capture contract. |
| `tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py` | Add the durable v5 negative matrix, including one/three launches, changed profile, missing/wrong ids, missing/malformed responses, unverified capture, and message-seam failure. |
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | Update only exact changed/new persistence surfaces with named final tests and schema-limited sanitized-field rationales. |
| `reports/plan-11-24-agent-protocol-persistence-establishing-drive.md` | Future-only Task-13 committed report in the exact v2 typed schema. Do not create it in this offline repair. |
| `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v6.md` | Sole live checkbox/status contract after merge. Predecessor plans remain byte-identical. |
| `docs/superpowers/reviews/plan-11-24-review-checkpoints.md` | Reviewer-owned, gitignored continuity log; never stage it. |

## Task 15: Implement the Git-blob authority and freshness gate

**Owner:** Cursor implements; Codex reviews.

**Scope classification:** Offline harness/test patch. No real binary, trust ceremony, keyring, Zed,
service, network, or report publication occurs.

- [ ] **Step 1: Rebase only after `_v6` lands.** Start from current `main`, read this file and the
  checkpoint, then rebase/cherry-pick the PR #184 implementation intentionally. Record exact base,
  head, and the pre-repair `6f9a7d6` comparison. Do not edit v1–v5.

- [ ] **Step 2: Write genuine RED authority tests first.** Add tests named:

  - `test_establishing_applicability_hashes_git_blobs_not_worktree_bytes` using a temporary Git repo
    whose blob is LF and worktree representation is deliberately different;
  - `test_establishing_applicability_rejects_dirty_execution_surface` parameterized over staged,
    unstaged, deleted, renamed/type-changed, and conflicted states;
  - `test_establishing_import_closure_equals_explicit_module_path_subset`,
    `test_establishing_import_closure_traverses_package_init_reexports`, and
    `test_establishing_import_closure_rejects_unlisted_new_project_module`;
  - `test_establishing_authority_allows_report_only_descendant_commit`;
  - `test_establishing_authority_rejects_untracked_authorizing_report` and
    `test_establishing_authority_rejects_dirty_tracked_authorizing_report`;
  - `test_establishing_authority_reads_committed_report_blob_not_worktree_bytes`;
  - `test_establishing_authority_rejects_nonancestor_or_surface_drift`;
  - `test_canonical_launcher_identity_ignores_only_run_root` and
    `test_raw_launcher_sha_is_audit_only_not_cross_run_authority`;
  - `test_isolated_probe_patch_writes_exact_git_blob_bytes_on_windows`;
  - `test_acpx_identity_binds_cli_js_not_generic_npm_shim`;
  - `test_establishing_report_freshness_uses_completion_time_and_dedicated_bound`; and
  - `test_establishing_report_freshness_accepts_z_and_plus_zero_and_serializes_z` and
    `test_establishing_report_freshness_rejects_stale_future_naive_minus_zero_and_non_utc`.

  Tests use real temporary Git commits/blob reads and injected clock/process seams. They assert
  `zed_launches == 0` on every reject. Do not satisfy them with a worktree digest, mocked commit
  equality, or a raw-launcher equality bypass.

  The committed-report negatives are explicit contract rows, not incidental setup failures:

  | Report state at Task 14 | Required rejection |
  |---|---|
  | report exists only as an untracked worktree file and is absent from `HEAD` | `PRECONDITION_UNMET`; `zed_launches == 0` |
  | report is tracked at `HEAD` but its index or worktree bytes are dirty | `PRECONDITION_UNMET`; `zed_launches == 0` |

- [ ] **Step 3: Run and record RED.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "establishing_applicability or establishing_import_closure or establishing_authority or canonical_launcher or isolated_probe_patch or acpx_identity or report_freshness" -q
  ```

  At least one test for each absent behavior must fail against the test-only patch on the repair
  baseline. Record test node and behavioral failure in the reviewer checkpoint. A case already
  rejected at `6f9a7d6` is a preservation case, not “genuine RED”; label it baseline-green rather
  than manufacturing a failure.

- [ ] **Step 4: Implement the minimum gate.** Add small typed records and pure helpers in the probe
  file; do not create a generic hashing/refactor module. Read blobs in binary mode, canonicalize the
  manifest exactly, traverse package initializer bodies, enforce the literal AST closure and clean
  status, read the authorizing report only from the clean `HEAD` blob, use the ancestor relation,
  bind `acpx` to version plus CLI-JS SHA, write the patched spec as exact bytes, compare canonical
  launcher/patched-spec/runtime identities, and validate the explicit UTC lexical forms and
  completion-time freshness with `ESTABLISHING_REPORT_MAX_AGE_SECONDS`.

  The entire gate runs before trust approval and `_launch_zed_once`. Discovery and isolated
  preparation may remain no-launch setup, but any failure must clean its throwaway roots, retain no
  authority, materialize no v5 bundle, and return zero launches.

- [ ] **Step 5: Prove focused GREEN.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "establishing_applicability or establishing_import_closure or establishing_authority or canonical_launcher or isolated_probe_patch or acpx_identity or report_freshness" -q
  uv run --frozen --all-extras python -m ruff check tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  ```

## Task 16: Repair the Task-12 premise and Task-13 reconstruction record

**Owner:** Cursor implements; Codex reviews. The operator does not execute Task 13 in this task.

**Scope classification:** Offline harness/report-schema tests. All `acpx`, approval, filesystem,
clock, and process calls are stubbed; no real report is published.

- [ ] **Step 1: Write the strict sequence predicate and report-schema RED tests.** Add
  `test_agent_protocol_drive_requires_real_erroring_prompt_on_new_session`,
  `test_agent_protocol_drive_requires_same_session_new_prompt_and_load`, and
  `test_agent_protocol_report_v2_reconstructs_authority_sequence_traffic_custody_and_cleanup`.
  The happy fixture contains one real client-produced prompt request and a correlated error response,
  not just a nonzero process exit. Assert the report parser can reconstruct every exact JSON field
  defined above without consulting the sidecar.

- [ ] **Step 2: Add a durable parameterized establishing-negative table.** It includes at least:

  | Case | Required rejection |
  |---|---|
  | missing `session/new` response or session id | `PRECONDITION_UNMET` |
  | no `session/prompt` request | `PRECONDITION_UNMET` |
  | two prompt requests | `PRECONDITION_UNMET` |
  | prompt content not exactly one fixed text block | `PRECONDITION_UNMET` |
  | prompt session id differs from `session/new` | `PRECONDITION_UNMET` |
  | prompt response missing or response id mismatched | `PRECONDITION_UNMET` |
  | prompt succeeds | `PRECONDITION_UNMET` |
  | prompt response has both `result` and `error` | `PRECONDITION_UNMET` |
  | reload request/response missing | `PRECONDITION_UNMET` |
  | reload session id differs from `session/new` | `PRECONDITION_UNMET` |
  | reload response is not exactly `{}` | `PRECONDITION_UNMET` |
  | Gateway marker present | `PRECONDITION_UNMET` |
  | provider or model-call marker present | `PRECONDITION_UNMET` |
  | approval not created/revoked or inspect exit is not 1 | no authorizing report |
  | cleanup false | no authorizing report |

  Every row asserts zero Zed/origin-A launches and absence of the committed report. Rows exposing a
  missing behavior at the repair baseline require genuine RED before production changes; already
  correct rows remain durable baseline-green regressions.

- [ ] **Step 3: Run RED.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "agent_protocol_drive or agent_protocol_report_v2 or establishing_negative" -q
  ```

  Expected absent-behavior failures: the current implementation treats nonzero `acpx exec` as
  enough, does not require the captured erroring prompt/same-session response chain, and writes only
  sparse provenance labels rather than the typed reconstruction record.

- [ ] **Step 4: Implement the minimum strict predicate and report writer/parser.** Parse only
  sanitized records emitted by `acpx`. Correlate request/response ids, enforce one exact prompt and
  one shared session id, distinguish protocol error from process exit, and reject malformed
  result-plus-error objects. Build the canonical typed record only after revoke/inspect and cleanup;
  publish atomically. Keep raw command streams and fixed message text out of persistence.

- [ ] **Step 5: Prove focused GREEN and surface classification.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "agent_protocol_drive or agent_protocol_report_v2 or establishing_negative or raw_acpx_agent_command" -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
  uv run --frozen --all-extras python -m ruff check tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  ```

## Task 17: Enforce the Lifecycle-A message seam and durable v5 negatives

**Owner:** Cursor implements; Codex reviews.

**Scope classification:** Offline harness/verifier/test patch. GUI/process launches, approval,
clocks, and roots are stubbed. No live profile or evidence bundle is created.

- [ ] **Step 1: Write genuine RED seam tests.** Add
  `test_two_lifecycle_run_requires_exactly_one_fixed_lifecycle_a_prompt`,
  `test_two_lifecycle_run_rejects_prompt_with_extra_content_or_wrong_session`, and
  `test_two_lifecycle_failure_cannot_materialize_v5_bundle`. Feed zero, two, wrong-text,
  multi-block, wrong-session, missing-response, and mismatched-response-id prompt captures. Each
  must end `INDETERMINATE / PRECONDITION_UNMET`, clean/revoke once, produce no bundle, and never
  promote a ledger observation into an unenforced boolean.

- [ ] **Step 2: Add verifier preservation and negative matrices.** Keep all historical manifests
  valid. Parameterize v5 rejects for one launch, three launches, changed shared profile/workspace,
  missing Lifecycle-A session id, wrong Lifecycle-B load id, missing B response, result-plus-error,
  missing lifecycle file/digest, extra file, unverified raw capture, and failed message seam. Assert
  exact reason paths where the verifier exposes them.

- [ ] **Step 3: Run RED.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -k "lifecycle_a_prompt or two_lifecycle_failure or v5_negative or v5_manifest" -q
  ```

  Expected absent-behavior failure: PR #184 records prompt counts/text-match observations but does
  not gate classification or materialization on them. Record genuine RED per missing seam; label
  preexisting verifier rejections as baseline-green preservation evidence.

- [ ] **Step 4: Implement only the missing predicate.** Validate the verified raw Lifecycle-A
  request/response pair before reconstruction: one prompt request total, prompt array length one,
  one text item equal to the fixed constant, same session id as the captured `session/new`, and a
  correlated error response. Make that predicate a prerequisite for classification and
  materialization. Preserve the two-run shared deadline, relay opacity, cleanup, and legacy verifier
  branch.

- [ ] **Step 5: Prove focused GREEN.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -k "lifecycle_a_prompt or two_lifecycle or resume_classifier or v5_negative or v5_manifest" -q
  uv run --frozen --all-extras python -m ruff check tools/probe_p11_zed_session_load.py tools/verify_plan1119_zed_reprobe_evidence.py tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py
  ```

## Task 18: Verify and publish the offline repair only

**Owner:** Cursor prepares; Codex reviews; operator alone merges.

- [ ] **Step 1: Run the complete offline gates.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe/manifest.json
  uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe-v3/manifest.json
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen --all-extras python -m ruff check .
  git diff --check
  ```

- [ ] **Step 2: Recheck immutable and absent artifacts.** Confirm v1–v5 blob ids above, no new
  `reports/plan-11-24-agent-protocol-persistence-establishing-drive.md`, no
  `reports/plan-11-24-zed-guided-session-load-probe-v5/`, no changed historical bundle, and no diff
  in the deferred backlog/roadmap/README. The offline repair may update only the file map above.

- [ ] **Step 3: Audit every current-state document.** The reviewer checks the open-work pool,
  roadmap, README, Plan 11.24 live pointer, and any other document whose current-state claim could
  be changed by the offline repair. Record why each is already current or identify a forward-only
  documentation repair; do not ask Cursor to opportunistically close or reschedule the backlog.

- [ ] **Step 4: Review exact-head CI and land before Task 13.** PR review binds exact base/head,
  changed files, test totals, Ruff, sink audit, historical bundles, and all CI steps. If GitHub
  rejects `REQUEST_CHANGES` with 403, post the same blocking findings as a non-approval review or
  issue comment and record the API limitation; never convert a blocker to approval. Operator alone
  merges. Task 13 remains dormant until the repaired implementation itself is in `main`.

## Future Task-13 gate — definition only, not authorization

After the repaired implementation merges, a reviewer may record one exact no-Zed establishing
grant.

- [ ] **Step 1: Record the separate grant and recheck authority.** Before the operator answers `y`,
  require:

  - current HEAD is the recorded source commit;
  - every explicit execution path is clean and the AST closure equals the frozen list;
  - the Git-blob manifest, Python, `acpx` version/CLI-JS/trust identities, audit-only npm-shim SHA,
    canonical launcher digest, and patched-spec digest are recorded;
  - no Zed, Redis, Gateway, provider, or paid path will start; and
  - the future v5 Zed report directory is absent.

- [ ] **Step 2: Execute the parser-derived drive once.** Use the existing `_v5` Task-13 command
  without retyping or adding flags:

  ```powershell
  $probeParent = Join-Path $env:LOCALAPPDATA 'Optimus\p11-24-agent-protocol-persistence'
  New-Item -ItemType Directory -Force -Path $probeParent | Out-Null
  uv run --frozen python tools/probe_p11_zed_session_load.py --mode agent-protocol $probeParent
  ```

  Approve only the generated workspace. Require the exact typed sequence and all custody/cleanup
  facts. Do not repeat the command.

- [ ] **Step 3: Publish and verify the prerequisite record.** Publish only after successful
  cleanup, set completion time then, run Task 18's offline gates, and commit the report under a
  separately authorized Git operation. The report commit is expected to advance HEAD; that is the
  scenario the ancestor-plus-manifest contract exists to permit.

A stale/failed run grants no retry. A new establishing drive requires a new reviewer-checked
operator grant. A paid fallback remains separately scoped and must name provider, model, fixed
message, and numeric maximum cost.

## Future Task-14/two-Zed gate — definition only, not authorization

Before seeking the two-launch grant, the reviewer checks the committed report against current HEAD:

1. the report path is clean, exists as a blob at `HEAD`, and is parsed only from that committed
   blob rather than worktree, index, or another revision bytes;
2. source commit exists and is an ancestor, not necessarily equal;
3. current explicit Git-blob manifest equals the report manifest;
4. current execution surface is clean and its AST closure is complete;
5. completion time has an accepted `Z`/`+00:00` aware-UTC lexical form, is not future, and is at most
   86,400 seconds old;
6. Python, `acpx` version/CLI-JS, trust executable, canonical launcher, and patched-spec identities
   match; the npm-shim SHA remains audit-only;
7. the full typed sequence/traffic/custody/cleanup record is valid; and
8. every failure path returns zero launches before any trust approval.

- [ ] **Step 1: Record the v6 report-gate result.** Bind exact current HEAD, ancestor result,
  manifest/closure/cleanliness result, report age, all executable identities, and zero-launch
  outcome in the checkpoint. A failed row stops here.

- [ ] **Step 2: Record the separate two-Zed grant.** Only after Step 1 passes may the reviewer
  record the exact existing v5 two-launch grant: one shared profile, two
  relay run ids, one fixed Lifecycle-A message, one 900-second total deadline, no retry, no third
  launch, and no paid call unless separately granted. The live result consequences and historical
  bundle preservation remain exactly as `_v5` defines them.

- [ ] **Step 3: Execute the parser-derived command once and verify.** Use the `_v5` command and GUI
  sequence exactly; do not split it into manual launches or rerun it:

  ```powershell
  $probeParent = Join-Path $env:LOCALAPPDATA 'Optimus\p11-24-zed-resume-v5'
  $reportDir = 'reports/plan-11-24-zed-guided-session-load-probe-v5'
  New-Item -ItemType Directory -Force -Path $probeParent | Out-Null
  if (Test-Path -LiteralPath $reportDir) { throw "Fresh v5 report directory already exists" }
  uv run --frozen python tools/probe_p11_zed_session_load.py --mode real-zed-resume --zed-launch-timeout-seconds 900 --report-dir $reportDir $probeParent
  ```

  Then run the frozen-bundle, new-bundle, focused-suite, surface-audit, hygiene, Ruff, and diff gates
  already enumerated in `_v5` Future Gate 6. State only the evidence consequence; do not close or
  implement `P11-FEAT-ZED-RESUME` automatically.

## Definition of Done

| Claim | Required evidence |
|---|---|
| The report-commit paradox is removed without weakening source binding. | Temporary-Git test proves a report-only descendant is allowed; non-ancestor and changed execution blob reject; no HEAD equality or whole-workspace equality remains. |
| Applicability is stable across line-ending policy. | Blob-vs-worktree test hashes `git cat-file` bytes and remains stable when worktree bytes differ. |
| False provenance from dirty source is impossible. | Parameterized staged/unstaged/deleted/renamed/conflicted execution-path tests reject before approval/launch. |
| Import coverage cannot silently erode. | Runtime/test AST closure parses package-initializer bodies, exactly equals the explicit 128-file module subset, and a synthetic new in-repo import fails until the literal list is amended by plan. |
| Task 14 cannot authorize from mutable report bytes. | Temporary-Git tests prove an untracked report and a dirty tracked report reject, while the accepted parser reads only the clean `HEAD:<report-path>` blob. |
| Launcher identity is comparable across runs. | Different temporary roots have equal canonical SHA and unequal raw SHA; only canonical equality authorizes while both raw values remain audit facts. |
| Isolated patch identity is byte-exact on Windows. | A CRLF-configured temporary checkout still writes the in-memory Git-blob patch with `write_bytes`; on-disk bytes equal expected LF bytes exactly. |
| `acpx` identity binds executable behavior rather than the generic npm shim. | Version plus installed `node_modules/acpx/dist/cli.js` SHA equality authorizes; the command-shim SHA is recorded but cannot authorize. |
| Freshness is semantically independent. | Dedicated 86,400-second constant; `Z` and `+00:00` accept and serialize to `Z`; stale/future/naive/`-00:00`/nonzero-offset reject with zero launches; 900-second launch deadline unchanged. |
| Task 12 proves the real premise. | One actual client-produced erroring prompt request/response is correlated to the same `session/new` and `session/load {}` id; process exit alone cannot establish. |
| Task 13 is reconstructable from the committed artifact. | The v2 JSON record alone reconstructs source/applicability/executable identities, sequence, zero counts, no traffic, custody, and cleanup; sidecar is unnecessary. |
| Lifecycle A enforces one message. | Zero/two/wrong/extra/wrong-session/missing-response cases cannot classify or materialize; exact one-message erroring seam passes. |
| Contract negatives are durable and honestly evidenced. | Named parameter tables cover every v5/v6 negative; absent behaviors have genuine pre-fix RED; already-correct cases are labeled baseline-green and remain regression tests. |
| Existing safety/evidence remains intact. | Full focused suite, both frozen bundle verifiers, Plan 9.96 sink audit, pool hygiene, repository Ruff, and `git diff --check` pass; v1–v5 blobs match. |
| Scope remains narrow. | No Task 13, Zed, live service, report bundle, paid call, backlog refactor, plan renumbering, commit, push, or merge occurs under the offline repair authority. |

## Explicit exclusions and custody

- The deferred probe-harness CLI/refactor work remains owned by the unnumbered MEDIUM post-11.x
  entry already placed in the consolidated deferred-followups backlog. This plan neither implements
  nor reschedules it.
- Durable session design after a future `REACHABLE` result remains owned by
  `P11-FEAT-ZED-RESUME`; this plan does not close or implement that roadmap item.
- A future `UNREACHABLE` or `INDETERMINATE` result changes only the evidence consequence defined by
  `_v5`; it grants no automatic retry or follow-up implementation.
- Historical reports, manifests, relay captures, frozen plan versions, and root-cause evidence are
  read-only.

## Required sequence

1. Review and merge this `_v6` plan amendment from its dedicated branch.
2. Rebase the Cursor repair onto that exact `main`; implement Tasks 15–18 with genuine RED first.
3. Codex reviews exact head and operator alone merges the offline repair.
4. Separately authorize and execute Task 13; commit its typed report.
5. Re-review the committed report under the 24-hour v6 authority gate.
6. Only then consider the separate two-lifecycle Zed grant defined by `_v5` and refined here.
