# Plan 6 Security Review — Round 2 (post-revision)

**Reviewer role:** Senior Architect / Network Security
**Plan:** `docs/superpowers/plans/2026-07-04-prompt-injection-mcp-trust-ci-guardrail-parity.md`
**Prior review:** `docs/superpowers/reviews/2026-07-04-plan-6-security-review.md`
**Verdict:** The blocker is fixed and 9 of 12 substantive findings are properly resolved. Three fixes, however, introduced new gaps — two of which recreate the exact "control present but not protecting" problem the revision set out to remove. None is a hard blocker; all are cheap to close.

---

## Confirmed resolved

- **B1 (parity blocker):** `GuardrailRuleSet.phase1()` now lists 7 checks and both `.pre-commit-config.yaml` and the CI workflow name all 7. `expected <= actual` and the intersection test both pass. ✅
- **H2 (planner exposure):** `MCPDescriptorExposureGuard` + `trusted_descriptors_for_planner()` route each descriptor through `validate_tool_call`, so a poisoned descriptor yields an empty exposed set. ✅
- **H4 (env/launch params):** `manifest_hash()` now covers `command`, `launch_args`, `cwd`, and `env` (values as SHA-256 digests); `descriptor_text()` redacts env values. The reapproval-on-env-change test asserts the secret value never appears in descriptor text. ✅
- **H5 (TOCTOU):** Explicitly documented as a transitional in-process contract with a stated constraint on the future loader. ✅
- **M1 (dead confusable check):** Confusable/punycode now run on `raw_text` before NFKC in both `prompt_injection.py` and `command_safety.py`, with fullwidth/punycode tests. ✅
- **M2 (CLI fail-open):** `scan_paths` now emits `injection.unscannable_path` BLOCK for non-files and decodes with `errors="replace"` instead of skipping. ✅
- **M3 (config globs):** Broadened to nested `**/AGENTS.md`/`**/CLAUDE.md`, `.mcp.json`, `.vscode/mcp.json`, `.cursor/**/*.mdc`, windsurf/cline rules, with a coverage test. ✅
- **M6 (audit integrity):** `check()` records `failed_checks=()` on an allowed pre-tool validation; test asserts it for the MCP allow. ✅
- **M7 naming:** Split into `config-trust-scan` (injection scanner) and a separate `secret-scan` — but see N1, the secret scan is a no-op as configured.
- **H3 (scope enforcement):** Now enforced via `_scope_allows` — but see N2, it trusts an attacker-authored field.

---

## New / residual findings (introduced by the fixes)

### N1 — HIGH: the `.secrets.baseline` disables the secret scanner (M7 only half-fixed)

`.secrets.baseline` is hand-authored with `"plugins_used": []` and `"filters_used": []`. `detect-secrets-hook` runs the plugins recorded in the baseline; with an empty `plugins_used` array, **zero detectors run**, so the hook passes on everything and detects no committed secrets — both in pre-commit and in the CI `detect-secrets-hook ... $(git ls-files)` step. This recreates the false-assurance problem M7 was meant to close: a `secret-scan` check that is green because it inspects nothing.

**Fix:** generate the baseline with `detect-secrets scan > .secrets.baseline` so `plugins_used` is populated with the default detector set (and keep `results: {}` for "no accepted secrets"). Add a parity/sanity test that fails if `plugins_used` is empty. Optionally quote `"$@"`/use `xargs` instead of unquoted `$(git ls-files)` in CI to survive paths with spaces.

### N2 — HIGH/MEDIUM: scope enforcement trusts a manifest-declared `side_effect_class`

`_scope_allows(record.permission_scope, tool.side_effect_class)` decides read-vs-write from `MCPToolDescriptor.side_effect_class`, a field supplied by the **untrusted manifest**. A descriptor that writes but labels itself `side_effect_class="read"` passes scope enforcement. Hash pinning does close the post-approval tampering path (the field is in `manifest_hash()`, so changing it forces reapproval), so the real residual is at **approval time**: a maintainer can approve a mislabeled manifest, and nothing surfaces or independently derives the side-effect class. The trust model scans the descriptor *text* as untrusted but then trusts a *structured field* from that same text to make the security decision.

**Fix (pick one):** derive side-effect class independently (tool-name/verb heuristics or schema inspection) rather than trusting the label; and/or have `register()` surface each tool's declared `side_effect_class` to the approver and reject a manifest whose declared classes exceed `permission_scope` at registration time (fail early, not just at call time). At minimum, document that approvers must verify the declared side-effect classes.

### N3 — MEDIUM: git-bypass detectors match only the literal `git` at argv[0]

`_is_git_no_verify_bypass`, `_is_git_hooks_path_bypass`, and `_git_subcommand` all key off `tokens[0] == "git"` / `lowered[:1] == ("git",)`. The rest of `command_safety.py` normalizes the executable with `Path(command[0]).name.lower()` (see `_is_recursive_force_delete`). Because these new helpers don't, `("/usr/bin/git", "commit", "--no-verify", ...)` or `("./git", "commit", "-n")` evade **both** new controls — the exact bypass Task 4 exists to prevent. Inconsistent and weaker than the surrounding code.

**Fix:** normalize with `Path(command[0]).name.lower() == "git"` in the three helpers and add a `/usr/bin/git commit --no-verify` test.

### N4 — MEDIUM: `MCPConfigIngestionGuard.ingest_manifest_path` scan/allow branch is unreachable

`evaluate_autoload_path()` returns `allowed=False` on **both** branches (`outside_workspace` and `cloned_repo_denied`), so in `ingest_manifest_path` the guard `if not autoload.allowed: return autoload` always fires. The subsequent `read_text` + `scan_text` + `MCPTrustDecision(True, "mcp.config_ingested", ...)` is **dead, untested code**, and `mcp.config_ingested` can never be emitted. Consequently this API does **not** deliver the "poisoned config caught on ingest" guarantee (Test Strategy 14.4) — that scanning only actually happens in `register()` (descriptors) and the CLI `scan_paths` (config files). The dead lines will also read as uncovered against the `--cov-fail-under=80` focused gate for `mcp_trust.py`.

**Fix:** decide the intended semantics. Either (a) drop the unreachable scan/allow path and rename the type to reflect that it is a pure autoload denier, or (b) if scan-on-ingest is wanted for an explicitly-approved external manifest, restructure so the scan runs before/independently of the autoload denial and there is a reachable allowed outcome, with a test exercising it.

### N5 — LOW: `git push -n` (dry-run) is mislabeled as a no-verify bypass

`_is_git_no_verify_bypass` treats `-n` as `--no-verify` for both `commit` and `push`, but for `git push`, `-n` means `--dry-run` (harmless). Blocking it is fail-closed and low-harm, but the `shell.git_no_verify` rule id is a misclassification. Consider scoping `-n` to the `commit` subcommand only.

### N6 — LOW: `_scope_allows` hard-codes two scope strings

Any `permission_scope` other than `read_only_metadata` or `network_read` makes `_scope_allows` return `False` for every tool, silently bricking the server at call time. Fail-closed, but undocumented and surprising. Enumerate the allowed scopes (ideally an enum) and validate `permission_scope` at `register()`.

### N7 — LOW: `pytest-coverage` as a pre-commit hook is heavy

The local `optimus-pytest-coverage` hook runs the full suite with coverage on every commit. That is slow enough to push developers toward `--no-verify` (blocked for the agent, but not for humans). It's fine for satisfying name-parity, but consider making the local hook manual-stage (`stages: [manual]`) or a lighter fast subset, and let CI own the full coverage gate.

---

## Recommendation

Ship-blocking to fix before execution: **N1** (secret scan is currently a no-op) and **N3** (path-qualified git bypass). **N2** and **N4** should be resolved or explicitly deferred with a tracked ticket, since both are cases where a control reads as present but does not fully protect. N5–N7 are polish. Everything from Round 1 that was claimed fixed, I verified as actually fixed in the plan text.
