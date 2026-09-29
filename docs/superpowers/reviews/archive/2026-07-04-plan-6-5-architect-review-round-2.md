# Plan 6.5 Architecture Review — Round 2 (post-revision)

**Reviewer role:** Senior Architect
**Plan:** `docs/superpowers/plans/2026-07-04-plan-6-5-guardrail-hardening-mcp-runtime-trust.md`
**Prior review:** `docs/superpowers/reviews/2026-07-04-plan-6-5-architect-review.md`
**Verdict:** All findings from round 1 are resolved and independently verified — the blocker by re-executing the exact revised function against the same `confusable-homoglyphs==3.3.1` package used in round 1, the two High findings and three Medium findings by tracing the revised code against `PermissionPolicy`, `MCPAutoloadGuard`, and the new test fixtures. Plan 6.5 is ready for execution.

---

## Confirmed resolved

- **B1 (blocker — confusable detector flags all text):** The revised `contains_dangerous_confusable()` drops the ungated `confusables.is_confusable(text, greedy=True)` call and now uses `confusables.is_dangerous(text)` plus a narrow, name-based fullwidth/halfwidth check instead of "any NFKC change." I re-ran the exact revised function from the plan against every attack fixture (Cyrillic, Greek, fullwidth, punycode) and every benign fixture from both new test functions (`pytest tests/unit -v`, `git status`, `hello world`, `open agent-config`, plus the trademark/superscript/fraction NFKC-compatibility cases) — attacks all return `True`, benign cases all return `False`. This is a real fix, not a narrowed re-statement of the same bug. ✅
- **H1 (approval inferred from execution mode):** `execute_tool()` now takes a required `approval_granted: bool` keyword argument with no default, independent of `execution_mode`. Traced through `PermissionPolicy.decide()`: with `approval_granted=False` the call correctly HOLDs at `classifier.not_configured` before the MCP trust registry is ever consulted (new test `test_runtime_registered_mcp_call_requires_per_call_approval` exercises exactly this and asserts the runner is never called); with `approval_granted=True` and a registered server it correctly reaches the registry and runner (`test_runtime_registered_mcp_call_runs_after_explicit_per_call_approval`). The per-call approval gate is real again. ✅
- **H2 (autoload denial not wired into registration):** `register_explicit_manifest()` now calls `self.ingestion_guard.deny_autoload_path(path)` and raises `MCPRuntimeBlocked` when the decision is `mcp.autoload.cloned_repo_denied`, before any scanning/registration happens. The new test `test_runtime_rejects_workspace_bundled_manifest_registration` proves a workspace-bundled `.cursor/mcp.json` path is rejected by the runtime context itself. The happy-path test was correctly restructured (`workspace_root` is a subdirectory, manifest paths are siblings of it) so genuinely external, explicitly-approved manifests still register — that distinction matches the original "cloned-repo servers never auto-load, external manifests require explicit approval" design intent rather than over-blocking it. ✅

## Confirmed resolved (bonus — not explicitly called out as fixed, but verified)

- **M1 (silent scan skip when neither `manifest_text` nor an existing path given):** `register_explicit_manifest()` no longer has an `elif path.exists()` fallthrough; when `manifest_text` is absent it unconditionally calls `scan_manifest_path()`, which now fails closed on a missing path. New test `test_runtime_rejects_missing_manifest_input` confirms this raises rather than silently skipping. ✅
- **M2 (rule-id naming inconsistency):** Task 1's fail-closed rule id was renamed from `mcp.config_unscannable_path` to `injection.unscannable_path`, matching the existing config-scanner convention, and this id is threaded consistently through Task 4's runtime tests. ✅
- **M3 (private-attribute reach-through):** `MCPConfigIngestionGuard` gained a public `scan_manifest_text()` method; `register_explicit_manifest()` calls it instead of reaching into `self.ingestion_guard._scanner`. The `# noqa: SLF001` suppression is gone. ✅

## Residual notes (non-blocking)

- The narrowed fullwidth/halfwidth check uses `unicodedata.name(char, "")` substring matching. This is correctly scoped for the attack class this plan cares about (fullwidth Latin/digit lookalikes) and was verified against all of round 1's false-positive examples, but it's a name-string heuristic rather than a codepoint-range table — fine for this plan's scope, worth remembering if a future plan needs stricter guarantees.
- The plan added a one-line note flagging that `confusable-homoglyphs` doesn't publish 3.13/3.14 classifiers and wrapped it behind `unicode_confusables.py` for replaceability. That's an adequate, proportionate response to a low-severity packaging note — no further action needed here.

## Recommendation

No remaining blockers or high-severity findings. Plan 6.5 is sound and ready to execute task-by-task as written.
