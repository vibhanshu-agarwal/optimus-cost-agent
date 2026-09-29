# Senior Architect Review — Plan 5: Permission Engine, Pre-Tool Guard, and Shell Safety

**Plan reviewed:** `docs/superpowers/plans/2026-07-03-permission-engine-pre-tool-guard-shell-safety.md`
**Reviewer role:** Senior Architect / Reviewer
**Date:** 2026-07-03

---

## Re-review (Round 3) — R1/R2 fixes verified — APPROVED

Both residual items from Round 2 are resolved; no new issues introduced.

- **R1 (was blocking) — fixed.** Task 6 now explicitly updates the existing `test_write_file_allowed_after_agent_approval` to pass a `tmp_path`-scoped `PreToolGuard` (plan line 1350), so the approved write validates against a workspace that actually contains the target. Traced end to end: permission `ALLOW` → `validate_write` inside-workspace → file written. No other existing mutation test writes outside `cwd` without a guard, so the suite is clean.
- **R2 (was medium) — fixed properly.** `PreToolGuard` now stores `_workspace_root` (line 1188) and `_sanitize_subject` redacts the real workspace-root prefix generically for both shell commands and file targets (lines 1273–1283); the `/src`-only special case is gone. New test `test_pre_tool_guard_sanitizes_workspace_root_for_file_targets` (line 1055) locks in the general behavior.

**Disposition: approved to implement.** The remaining Round 1 design notes (H1 self-review order wording, H2 `\b(env|set)\b` false-positive on `pytest tests/env`, H3 `-f` force-push, H4 `first_time_tool` unreachable via the guard, MCP surface has no `_validate_surface` branch) are non-blocking backlog items, not gating this plan. Recommend tracking them as hardening follow-ups (naturally in Plan 6's guardrail scope).

---

## Re-review (Round 2) — after the author's fixes

**Status: nearly there. One residual blocker, one quality issue; the seven original blockers are resolved.**

I re-read the revised plan end to end and re-traced every affected test, and empirically reproduced the path/sanitizer logic.

**Original blockers — all verified fixed:**

| # | Original issue | Fix in revised plan | Verified |
|---|----------------|---------------------|----------|
| B1 | writes/apply/web fell through to `HOLD` | `_project_allow_decision` now returns `ALLOW` for approved shell / `FILE_READ` / approved `FILE_WRITE`/`SHADOW_APPLY`/`WEB` (lines 437–452) so surfaces reach validation | ✅ |
| B2 | dangerous shell `HOLD`-ed before validators ran | approved shell now `ALLOW`s at permission → `CommandSafetyValidator` runs → `rm -rf` `BLOCK`s; Task 5 + Task 8 traces now pass | ✅ |
| B3 | duplicated `ValidationVerdict` compared with `is` | single `guardrails/validation.py`; path/network/command/pre_tool all import it | ✅ |
| B4 | ANSI test had no real control byte | now `chr(27)+"]0;spoofed"+chr(7)` (real ESC/BEL) | ✅ |
| B5 | `sanitized_subject` expectation unsatisfiable | expectation + sanitizer aligned to `"rm -rf <workspace>/src"` | ✅ (but see R2) |
| B6 | Task 7 `__init__` renamed public attrs, dropped lock | now additive: keeps `gateway_client`/`domain_policy`/`registry`/`ledger` + `_ledger_lock`, adds `_pre_tool_guard` | ✅ |
| B7 | Task 7 missing imports | adds `ToolCallRejected`, `ToolInvocationDecision`, `PolicyDecision`, `ToolPolicySignal`, `EvidenceReasonCode` | ✅ |

**Residual findings:**

- **R1 — Blocking. The untouched existing `test_write_file_allowed_after_agent_approval` still regresses**, now via `path.workspace_escape` instead of a permission hold. The revised `write_file` default is `PreToolGuard.for_workspace(workspace_root=Path.cwd(), …)` (line 1403), but that existing test writes to pytest's `tmp_path`, which is **not** under `cwd`. I reproduced it: `Path("/tmp/.../allowed.txt").resolve().relative_to(Path.cwd())` raises `ValueError` → `PathSafetyValidator.validate_write` returns `BLOCK path.workspace_escape` → `write_file` raises `MutationForbidden`. So Task 6 Step 4 (`pytest tests/unit/tools/test_mutation_tools.py`) and Task 10 Step 3 (`pytest -v`) fail on a pre-existing green test. The B1 fix moved the failure from the permission layer to the path layer; it did not clear it.
  **Fix:** update that existing test to pass a `tmp_path`-scoped guard (exactly as the Task 8 integration tests already do), or split the impact/path outcome so an approved in-tmp write is exercised with a matching workspace_root. The plan should explicitly call out the edit to the existing test rather than leaving it untouched.

- **R2 — Medium (quality). The sanitizer is special-cased to the one test fixture, not a real redactor.** `_sanitize_subject` (lines 1249–1261) only rewrites the last token when it ends with `/src`; I confirmed a generic path (`…/build`) and a `FILE_WRITE` target (`…/allowed.txt`) are logged **verbatim**, absolute path and all. The audit event therefore satisfies the test but does not deliver the "sanitized subjects" property the README/self-review claims. Consider redacting the real `workspace_root` prefix generically (the guard knows it) rather than string-matching `/src`.

**Carryover design notes (non-blocking, unchanged from Round 1 — restating so they aren't lost):** the Self-Review still asserts decision order "…project allow, impact, classifier" while the code evaluates the impact-hold *before* project-allow (H1); `_ENV_ACCESS`'s `\b(env|set)\b` still BLOCKs an allow-listed `pytest tests/env -q` (H2); `deny.git.force_push_main` still misses `-f` (H3); `first_time_tool` is still unreachable through the guard because `PreToolRequest` has no such field (H4); and `ToolSurface.MCP` still has no `_validate_surface` branch or test.

**Bottom line:** fix R1 (and ideally R2) and the suite should go green; everything else from Round 1 is resolved. The rest of this document is the original Round 1 review, retained for traceability.

---
**Method:** Read the full plan (1,829 lines), the Phase 1 roadmap, and Plan 4; then verified every cross-module assumption against the live code in `src/optimus/runtime/*`, `src/optimus/tools/*`, `src/optimus/evidence/*`, and `src/optimus/config/gateway.py`, and hand-traced each proposed test through the proposed implementation.

---

## 1. Verdict

**Request changes.** The plan is well-structured, correctly anchored to the source docs, respects the Plan 2 / Plan 4 boundaries, and follows disciplined TDD. The design intent is sound. However, if executed verbatim it **will not pass its own test suite** and **will regress an existing green test**, because of one central design flaw plus six concrete defects. None are deep — all are fixable with local changes — but they are blocking as written.

Confidence is high: the findings below are traced to specific line numbers in both the plan and the live code, not inferred.

**Blocking-issue summary**

| # | Severity | Issue | Effect if executed as written |
|---|----------|-------|-------------------------------|
| B1 | Blocking | No ALLOW path for `FILE_WRITE`/`SHADOW_APPLY`/`WEB`/non-allowlisted shell → everything falls to `HOLD "classifier.not_configured"` | Regresses existing `test_write_file_allowed_after_agent_approval`; `write_file`/`shadow_apply` can never succeed via the default guard |
| B2 | Blocking | Dangerous shell commands are `HOLD`-ed by the permission layer **before** `CommandSafetyValidator` runs | Plan's own PreToolGuard + integration BLOCK assertions fail (get `HOLD`/`classifier.not_configured`, not `BLOCK`/`shell.destructive.rm_rf`) |
| B3 | Blocking | `ValidationVerdict`/`ValidationResult` defined twice and compared with `is` across modules | Two command-safety network tests fail; insecure-transport `BLOCK` is silently downgraded to `HOLD` inside `PreToolGuard` |
| B4 | Blocking | ANSI test string uses escaped backslashes (`"\\x1b…"`) → no real control byte | `test_ansi_control_sequence_blocks` fails (validator returns `ALLOW`) |
| B5 | Blocking | `sanitized_subject` expected value (`"rm -rf **********"`) is not producible by the implemented sanitizer | Audit assertion in Task 5 fails |
| B6 | Blocking | Task 7 `__init__` rewrite renames public attributes and drops `_ledger_lock` | Breaks existing `search`/`extract`/`_record_ledger_entry` in the evidence service |
| B7 | Blocking | Task 7 uses `ToolCallRejected`, `ToolInvocationDecision`, `PolicyDecision`, `ToolPolicySignal`, `EvidenceReasonCode` without importing them | `NameError` at import/run time |

---

## 2. What the plan gets right

Worth stating, because these should be preserved through the rework:

- **Correct source anchoring and scope discipline.** Guardrails Strategy §2–4, LLD §12A, and Test Strategy §14.1–14.3 are mapped accurately. Out-of-scope items (MCP trust, CI parity, durable audit persistence, retry/gates) are correctly deferred to Plans 6/7/8 with named owners.
- **Boundary respect.** It layers *in front of* `MutationGuard` (Plan 2) and the evidence/tool policy (Plan 4) rather than replacing them, and keeps the borderline classifier injectable, off the hot path, and unable to overturn a deny — matching the Test Strategy requirement.
- **Enum/model shapes are reasonable** and the runtime types it consumes (`ExecutionMode`, `GenerationScope`, `RuntimeContext`, `MutationForbidden`, `MutationKind`, `assert_mutation_allowed`) all exist with the assumed members/signatures. `approved_agent_context()` and `ProbeRunner` already exist in `tests/unit/tools/test_mutation_tools.py`, so the Task 6 appended tests can rely on them.
- **Deny-precedence and mode short-circuit logic is correct where it is exercised** — `test_user_deny_precedes_project_allow…`, `test_plan_mode_short_circuits…`, and `test_classifier_cannot_overturn_user_deny` all trace through to passing.
- **Commit-approval gating** matches the repository norm (no commit/push/branch ops without explicit approval).
- **TDD structure** (red → green → focused verification) is consistent across all ten tasks.

---

## 3. Blocking findings (detail, evidence, fix)

### B1 — The permission policy has no ALLOW path for writes/apply/web; everything defaults to `HOLD "classifier.not_configured"`

`PermissionPolicy.decide` (plan lines 306–352) evaluates, in order: mode → user-deny → impact-hold → project-allow → classifier. The only project-allow rules (`_project_allow_decision`, lines 389–398) are `pytest`, read-only `git`, and *target-less* `FILE_READ`. Every other request — **all** `FILE_WRITE`, `SHADOW_APPLY`, `WEB`, `MCP`, and any shell command that is not `pytest`/read-only-`git` — reaches the final branch, and with no classifier configured returns:

```python
return PermissionDecision(verdict=HOLD, layer=CLASSIFIER, rule_id="classifier.not_configured", …)
```

Consequences, traced:

- **Existing green test regresses.** Task 6 wires a *default* real guard into `write_file` (plan lines 1343, 1359) with `generation_scope=GenerationScope.FILE_MUTATION`. The existing, currently-passing `test_write_file_allowed_after_agent_approval` (`tests/unit/tools/test_mutation_tools.py:71`) calls `write_file(...)` with **no** `guard` argument, so it now hits the default guard → `FILE_WRITE` has no allow rule → `HOLD` → `_assert_pre_tool_allowed` raises `MutationForbidden`. The file is never written and the test fails. Task 10's `pytest -v` will surface this.
- **`write_file` / `shadow_apply` become unusable** through the default guard in production for the same reason.
- **Web guard is unusable too** (see B2/H5): `_assert_pre_tool_web_allowed` on `ToolSurface.WEB` also lands on `classifier.not_configured` → every real web search would `HOLD`.

**Fix (design):** give the policy an explicit disposition for approved, safety-validated surfaces instead of falling through to a classifier hold. Concretely: when no deny applies and the request is already gated by `MutationGuard` approval (`approval_granted` + Agent mode), the permission layer should return `ALLOW` and delegate the *hard* checks to the deterministic validators, reserving `HOLD` for genuinely high-impact/ambiguous cases. The current "unknown ⇒ hold" default is defensible as a philosophy, but then the plan's own allow/BLOCK tests and the existing write test must be updated to match — they currently assume allow/block, not hold.

### B2 — Deterministic BLOCKs are shadowed: dangerous shell commands `HOLD` before `CommandSafetyValidator` runs

`PreToolGuard.check` (plan lines 1122–1152) runs `permission_policy.decide` first and **returns early** on `DENY`/`HOLD`, only calling `_validate_surface` (which invokes `CommandSafetyValidator`) when the permission verdict is neither. But per B1, `("rm","-rf",…)` is not deny-listed and not allow-listed, so `decide` returns `HOLD "classifier.not_configured"` and `check` returns before `CommandSafetyValidator` ever executes.

This directly breaks the plan's own tests:

- Task 5 `test_pre_tool_guard_blocks_shell_command_and_records_audit` (lines 941–960) asserts `verdict is BLOCK`, `rule_id == "shell.destructive.rm_rf"`, and an audit `verdict == "BLOCK"`. Actual: `HOLD` / `classifier.not_configured`. **Fails.**
- Task 8 `test_blocked_shell_command_never_reaches_runner` (lines 1642–1650) asserts `MutationForbidden match="recursive force delete denied"` and audit `rule_id == "shell.destructive.rm_rf"`. Actual message is `"human approval required: borderline call requires human approval"` and `rule_id` is `classifier.not_configured`. **Fails.**

Net effect: the entire `CommandSafetyValidator` (rm -rf, pipe-to-shell, env/credential, ANSI, homoglyph) only ever runs for the **allow-listed** commands (`pytest`, read-only `git`) — i.e. exactly the commands that are already safe — and never for the dangerous inputs it was written to stop. The safety validator is effectively dead code on the guard path.

**Fix (architectural):** run the deterministic **hard-deny** validators (the `BLOCK` rules) either *before* the permission allow/hold decision, or unconditionally with authority to override a `HOLD` down to a `BLOCK`. This also aligns better with the stated "deny-before-allow" and "classifier cannot overturn a deny" invariants: a `CommandSafetyValidator` `BLOCK` is conceptually a deny and should sit at deny precedence, not behind the allow/hold gate. An equivalent option is to fold the command/path/network `BLOCK` predicates into the user-deny layer.

### B3 — Duplicated `ValidationVerdict`/`ValidationResult` compared with `is` across modules

`path_safety.py` (lines 539–553) and `network_safety.py` (lines 678–689) each define their **own** `ValidationVerdict` and `ValidationResult`. `command_safety.py` imports them from `path_safety` (line 832) but embeds a `NetworkSafetyValidator` whose results carry `network_safety`'s enum. The code then compares across the two with `is`:

```python
# command_safety.validate (lines 863–865)
network_result = self._network_result(text)
if network_result is not None and network_result.verdict is not ValidationVerdict.ALLOW:  # path_safety's enum
    return network_result
```

`network_safety.ValidationVerdict.ALLOW is path_safety.ValidationVerdict.ALLOW` is **always `False`** (distinct enum classes, distinct singletons). So:

- `_network_result` returns a value for *any* URL, and `validate` returns the network result for *any* url-bearing command, even an allowed host.
- Task 4 `test_plain_http_fetch_blocks` (line 784) asserts `result.verdict is ValidationVerdict.BLOCK` using `path_safety`'s enum, but `result.verdict` is `network_safety`'s `BLOCK` → `is` is `False` → **test fails**. `test_unexpected_network_host_holds` (line 791) fails identically.
- Worse, in `_pre_tool_result` (lines 1187–1192) the network-origin verdict matches neither `path_safety.ValidationVerdict.ALLOW` nor `.BLOCK` under `is`, so it falls to the `else` → `HOLD`. A `network.insecure_transport` that should be a hard **BLOCK** is silently **downgraded to HOLD** inside `PreToolGuard`. That is a security-relevant weakening, not just a test failure.

**Fix:** define `ValidationVerdict` and `ValidationResult` **once** (e.g. a small `guardrails/results.py`) and import that single type into path/network/command modules. Alternatively compare by value (`==` / `.value`) — but a shared type is the correct fix and removes a whole class of latent `is`-comparison bugs.

### B4 — ANSI/control test contains no control byte

Task 4 `test_ansi_control_sequence_blocks` (lines 774–778):

```python
result = validator(tmp_path).validate(("printf", "\\x1b]0;spoofed\\x07"))
```

In a Python string literal, `"\\x1b"` is a **literal backslash-x-1-b** (four printable chars), not the ESC byte `0x1b`. `_contains_control_sequence` (lines 887–888) only detects real control characters (`ord(char) < 32` / `127`). So the input has no control byte, the check returns `False`, no later rule matches, and `validate` returns `ALLOW`. The test asserts `BLOCK "shell.ansi_control"` → **fails**.

**Fix:** use single backslashes so the bytes are real: `("printf", "\x1b]0;spoofed\x07")` (both `\x1b` ESC and `\x07` BEL are `< 32`). Optionally also decide whether the validator is meant to catch *rendered* escape text (the literal string `\x1b`) — if so, that is a separate detector and needs its own logic and test.

### B5 — `sanitized_subject` assertion is unsatisfiable

Task 5 (line 960): `assert guard.audit_events()[-1].sanitized_subject == "rm -rf **********"`. But `_sanitize_subject` (lines 1195–1201) builds `" ".join(command)` = `"rm -rf /tmp/.../src"` and then only replaces the secret tokens `.env`, `id_rsa`, `id_ed25519`, `token`, `credentials`. None appear, so the path is returned verbatim; it is never masked to `**********`. **The assertion fails**, and it reveals a spec ambiguity: is the sanitizer meant to redact secrets, or to redact argument values generally? Decide and align. (If the goal is to avoid logging absolute paths, the sanitizer needs path-masking logic, which it does not have.)

### B6 — Task 7 `__init__` rewrite breaks the existing evidence service

The live `EvidenceAcquisitionService.__init__` (`src/optimus/evidence/acquisition.py:39–51`) stores **public** attributes `self.gateway_client`, `self.domain_policy`, `self.registry`, `self.ledger` and creates `self._ledger_lock = Lock()`; every method (`search` L60–71, `extract` L123–135, `_record_ledger_entry` L174–177) reads those public names and the lock. The plan's Task 7 replacement (lines 1507–1521) renames them to `self._gateway_client`, `self._domain_policy`, `self._registry`, `self._ledger` and **omits** `_ledger_lock`. Following it verbatim breaks all existing methods (`AttributeError` on `self.gateway_client` / `self._ledger_lock`) and every currently-passing acquisition test.

The plan also changes `registry`/`ledger` from optional-with-defaults to required, a needless compatibility break.

**Fix:** *additive* change only — add `pre_tool_guard: PreToolGuard | None = None` and `self._pre_tool_guard = pre_tool_guard` to the existing `__init__`, leave the other attributes (and the lock) exactly as they are, and have the new helper read `self.gateway_client`/`self.domain_policy`/etc.

### B7 — Task 7 references undefined names (missing imports)

`_assert_pre_tool_web_allowed` and `_rejected_web_decision` (plan lines 1526–1563) use `ToolCallRejected`, `ToolInvocationDecision`, `PolicyDecision`, `ToolClass`, `ToolPolicySignal`, `EvidenceReasonCode`. The live module imports only `from optimus.tools.policy import ToolClass, ToolInvocationRequest`, and the plan's Task 7 import block adds only the guardrail names + `ToolSurface`. Verified locations:

- `ToolCallRejected` lives in `optimus.tools.registry` (`registry.py:23`, `__init__(self, decision)` → `super().__init__(decision.reason)`; so `match=` on the reason works — but it must be imported).
- `ToolInvocationDecision`, `PolicyDecision`, `ToolPolicySignal`, `EvidenceReasonCode` live in `optimus.tools.policy`.

**Fix:** add the missing imports. Without them Task 7 raises `NameError` the moment the block executes.

---

## 4. Design / correctness findings (non-blocking but should be addressed)

- **H1 — Decision order deviates from the spec it cites.** The plan's own Scope (line 29) and the LLD anchor say "mode, user deny, **project allow, impact**, classifier," but `decide` runs **impact-hold before project-allow** (lines 315–326). It fails safe (more holds), so it is not a security hole, but it contradicts the documented order and should either be reordered or the deviation justified in the plan text.

- **H2 — `_ENV_ACCESS` regex over-matches and can block the allow path.** `\b(printenv|env|set)\b` (line 836) matches the word `env` anywhere. `pytest tests/env -q` — a legitimately allow-listed command run against a common `env/` directory — is `ALLOW`-ed by the permission layer, then **BLOCKed** by `shell.env_access` in `_validate_surface`. `set` similarly risks false positives. Tighten to actual env-dump invocations (e.g. bare `env`/`printenv`/`set` as argv[0], `os.environ`, `$env:`, `%VAR%`) rather than substring word-boundary matches inside paths.

- **H3 — `deny.git.force_push_main` is trivially bypassable.** `_user_deny_decision` (line 380) requires the literal substrings `--force`/`--force-with-lease` **and** `" main"`. It misses the `-f` short flag (`git push -f origin main`), the `+refspec` force form (`git push origin +main`), and `refs/heads/main`. These fall through to `HOLD` (safe-ish), but a rule advertised as *denying* force-push-to-main should actually deny the common variants. Normalize the argv (resolve `-f`↔`--force`, detect `+` refspecs, match the `main`/`master` ref regardless of separator).

- **H4 — First-time-tool hold is unreachable through the guard.** `classify_impact` treats `first_time_tool` as HIGH (line 356), and the plan's Scope lists "first-time tools" as a hold trigger, but `PreToolRequest` has no `first_time_tool` field and `PreToolGuard.check` never sets it on the `PermissionRequest` (lines 1123–1135). The path is dead via the guard. Either add and propagate the field or drop the claim from scope.

- **H5 — Real web-guard integration would hold every search** (same root cause as B1). The Task 7 test only proves the *block* path via a fake `BlockingPreToolGuard`; it never exercises a real `PreToolGuard` allowing a legitimate search. Add a positive-path test, which will surface B1 for the WEB surface.

- **M1 — Call-cap consumed before the web guard rejects.** The plan calls the guard *after* `registry.authorize_and_record_call` (which decrements the per-run cap). A blocked/held egress still burns a cap slot. Probably acceptable, but note it — it means a guard-blocked call is indistinguishable from a successful one in cap accounting.

- **M2 — `_rejected_web_decision` hardcodes `policy_signal`/`reason_code`** to `USER_REQUESTED_EXTERNAL_FACT`/`USER_REQUESTED` regardless of the real request, degrading audit fidelity for extract and non-user-initiated searches.

- **M3 — Dead code / unused fields.** `mode.unknown` (line 374) is unreachable given the 3-member `ExecutionMode` enum; `PermissionRequest.network_host` and `metadata` are never read. Harmless, but they cost branch-coverage and imply capabilities that do not exist.

- **M4 — Secret-path matching gaps and false positives.** `_looks_like_secret_path` / `_is_secret_path` match exact path components against `{".env", …, "token", "secrets", "credentials"}`. This misses very common real secrets (`.env.production`, `.env.local`) and can false-positive on ordinary directories literally named `token`/`secrets`/`credentials`. Consider prefix/suffix rules for `.env*` and scoping the generic words.

- **M6 — pipe-to-shell bypass** (`curl … | sudo bash`, `| tee /dev/… ; bash`) is not caught by `_PIPE_TO_SHELL`. Mitigated today only because such commands `HOLD` at the permission layer (B1/B2). Once B2 is fixed so validators actually run, revisit the regex.

---

## 5. Spec-coverage check against the source anchors

| Anchor | Requirement | Plan status |
|--------|-------------|-------------|
| Guardrails §2–4 | deny-before-allow, mode short-circuit, human holds | Modeled; **hold-default swamps allow** (B1) and **hold shadows deny-validators** (B2) |
| Guardrails §2–4 | shell sanitization: destructive, pipe-to-shell, cred/env, ANSI, insecure transport, egress, homoglyph | Logic present in `CommandSafetyValidator`, but unreachable via guard (B2); ANSI test inert (B4); env over-broad (H2) |
| LLD §12A | `PermissionPolicy`, `PermissionDecision`, `PreToolGuard`, `CommandSafetyValidator`, `ToolInvocationAuditEvent` | All named and placed; classifier off hot path and cannot overturn deny ✓ |
| LLD §12A | validators run "after tool-call assembly, before execution" for bash/file/MCP/web | Wired for shell/file/web; **MCP surface declared but never validated** (no `_validate_surface` branch for `ToolSurface.MCP`) |
| Test Strategy §14.1–14.3 | deny precedence, mode short-circuit, impact HOLD, classifier-cannot-overturn-deny, validator blocks before spawn, Cyrillic confusable | Deny/mode/impact/classifier tests trace to passing ✓; **"blocks before spawn" fails** through the guard (B2); homoglyph unit test passes at validator level but the surrounding network tests fail (B3) |

Two coverage gaps to close: **MCP** is in `ToolSurface`/impact/mode logic but has no pre-tool validation branch and no test; and there is **no positive end-to-end "allowed write/apply/search after approval reaches the side effect"** test — precisely the case that exposes B1.

---

## 6. Test-suite risk assessment (what actually happens if you run it)

Hand-tracing each proposed test through the proposed code:

- **Task 1 (permissions):** all 5 pass. ✓
- **Task 2 (path):** all 4 pass. ✓
- **Task 3 (network):** all 3 pass. ✓
- **Task 4 (command):** `rm_rf`, `pipe_to_shell`, `env_dump`, `secret_read`, `homoglyph`, `pytest` pass; **`ansi_control` fails (B4)**; **`plain_http_fetch` and `unexpected_network_host` fail (B3)**.
- **Task 5 (pre-tool):** `holds_high_impact` and `allows_safe_pytest` pass; **`blocks_shell_command_and_records_audit` fails (B2 + B5)**.
- **Task 6 (mutation tools):** the two new DenyGuard tests pass (injected fake); but the **pre-existing** `test_write_file_allowed_after_agent_approval` now **fails (B1)** because Task 6 changes `write_file`'s default path.
- **Task 7 (evidence):** **`NameError` (B7)** and/or **`AttributeError` from the `__init__` rewrite (B6)** before assertions are even reached.
- **Task 8 (integration):** **`test_blocked_shell_command_never_reaches_runner` fails (B2)**; `test_blocked_secret_write_never_creates_file` passes (secret write *is* user-denied, so it correctly BLOCKs).
- **Task 10 coverage gate (`--cov-fail-under=80`, branch):** unreachable until the above are fixed; and once fixed, the dead branches (M3) plus untested branches (MCP, `set-acl`/chmod deny, `remove-item -recurse`, `format`/`diskpart`, path-read-outside-workspace HOLD, `network.missing_host`) put the 80% *branch* target at real risk without ~6–8 more targeted tests.

So: **≥6 of the plan's own new/affected tests fail, and 1 existing green test regresses**, all from the seven blocking items.

---

## 7. Prioritized recommendations

1. **Fix the layering (B1 + B2) first — it is the linchpin.** Decide the model explicitly:
   - Run deterministic **BLOCK** validators (command/path/network hard-denies) at *deny precedence*, ahead of or overriding the allow/hold gate, so a dangerous command BLOCKs rather than HOLDs; **and**
   - Give approved, mutation-gated surfaces (`FILE_WRITE`, `SHADOW_APPLY`, and validated `WEB`) a real `ALLOW` disposition instead of `classifier.not_configured` HOLD.
   Then reconcile every test's expected verdict with the chosen model, and add the missing positive-path tests (write-after-approval, search-after-approval).
2. **Unify `ValidationVerdict`/`ValidationResult` into one shared type (B3)** and purge cross-module `is` comparisons.
3. **Correct the two test-data/oracle bugs (B4 ANSI bytes, B5 sanitizer expectation).**
4. **Make Task 7 additive (B6) and add the missing imports (B7).**
5. **Tighten detectors (H2 env, H3 force-push, M4 secret paths)** and either implement or drop the `MCP`/`first_time_tool` claims (H4, §5 gap).
6. **Add branch-coverage tests** for the currently-untested safety branches before relying on the 80% gate.

Once items 1–4 are done, the suite should go green and the guardrail will actually enforce what the plan describes. The plan's bones are good; it mainly needs the permission/validator ordering corrected and a handful of precise fixes.

---

## Appendix — Evidence index (verified against live code)

- `src/optimus/runtime/modes.py` — `ExecutionMode{PLAN,CHAT,AGENT}`, `GenerationScope{INLINE_SNIPPET,PATCH_PROPOSAL,FILE_MUTATION,MULTI_FILE_CHANGESET}`. Matches plan usage.
- `src/optimus/runtime/mutation.py` — `MutationForbidden(message, code)` frozen dataclass; `__str__` returns `message` (so `pytest.raises(match=…)` works). `MutationKind`, `assert_mutation_allowed` present.
- `src/optimus/runtime/state.py` — `RuntimeContext(execution_mode, state, approval_granted, user_approval_id, …)`. Matches plan usage.
- `src/optimus/tools/mutation_tools.py` — current `write_file`/`shell_exec`/`shadow_apply` have **no** `guard` param; `test_write_file_allowed_after_agent_approval` (test file L71) calls `write_file` with no guard → hit by B1.
- `src/optimus/evidence/acquisition.py` — public attrs `self.gateway_client/domain_policy/registry/ledger` + `self._ledger_lock`; `registry`/`ledger` optional-with-defaults. Basis for B6.
- `src/optimus/tools/policy.py` — `PolicyDecision`, `ToolClass`, `ToolPolicySignal`, `EvidenceReasonCode`, `ToolInvocationDecision` (fields: decision, reason, tool_class, policy_signal, reason_code). Basis for B7.
- `src/optimus/tools/registry.py` — `ToolCallRejected(RuntimeError).__init__(decision)` → `super().__init__(decision.reason)`. Confirms `match=` works but import is required (B7).
- `src/optimus/evidence/models.py` — `EvidenceRequest` fields match the Task 7 test constructor.
- `src/optimus/config/gateway.py` — `LOCAL_PROVIDER_KEY_NAMES` exists; the Task 10 provider-key check is valid.
