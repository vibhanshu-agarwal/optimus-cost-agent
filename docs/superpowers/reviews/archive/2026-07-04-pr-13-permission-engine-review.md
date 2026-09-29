# Review: PR #13 "Add Phase 1 permission engine and pre-tool guardrails"

**Reviewer lens:** senior architect + network security
**Against:** `docs/superpowers/plans/2026-07-03-permission-engine-pre-tool-guard-shell-safety.md` (Plan 5) and `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
**Method:** read both plan docs in full, pulled the actual PR diff (21 files, +1678/-58, 11 commits) from GitHub, and independently re-ran the test suite and coverage in a fresh clone (Python 3.14 wasn't available in the sandbox, so I ran it on 3.10 with two narrow stdlib shims — `enum.StrEnum` and `datetime.UTC`, both added in 3.11 — purely to execute the existing code; no test or source logic was touched).

## Bottom line

The PR is faithful to Plan 5. All 10 tasks are implemented, the file structure matches almost exactly, and every verification claim in the PR description checks out against an independent run:

- Focused guardrail tests: **63/63 passed** (confirmed)
- Full suite: **202/202 passed** (confirmed)
- Coverage: **90.35%** aggregate, matches the claimed 90.4% (confirmed)
- Provider-key check: `FOUND=` empty (confirmed)
- `git diff --check`: clean (confirmed)

The two places it deviates from the plan's literal text are both cases where the plan document itself had a latent bug and the implementation correctly fixed it rather than copying it blindly. The more consequential findings are gaps that neither the plan nor the PR description surfaces: the audit trail isn't actually wired to persist in the one real production call site, and test coverage is uneven across the three "guarded" tool wrappers.

## Deviations from the plan (both judged as correct fixes, not defects)

**1. `command_safety.py` check ordering.** The plan's own code listing runs the `_ENV_ACCESS` regex check before `_credential_read`. The PR swaps that order. I verified why: the regex `\b(printenv|env|set)\b` matches "env" as a bare word wherever it's bounded by non-word characters — which includes inside a path like `.env`, since `.` and `/` are non-word characters. Run literally in the plan's order, `cat /tmp/.env` would hit `shell.env_access` (BLOCK) before ever reaching the credential-path check, contradicting the plan's own test, which asserts `rule_id == "shell.credential_read"`. I confirmed this directly by running the plan's exact regex against `.env`-containing paths. The PR's reordering is a genuine bug fix, not drift — but it isn't called out anywhere in the PR description, which it should be, given this is safety-critical matching logic.

**2. Integration test expectation change.** The plan's Task 8 test expects a blocked secret-file write to surface `rule_id == "path.secret.write"` (the `PathSafetyValidator`'s rule). The PR's actual test expects `rule_id == "deny.path.secret"` (the `PermissionPolicy`'s user-deny rule) instead. Tracing `PreToolGuard.check()`, `PermissionPolicy.decide()` runs first and its `_user_deny_decision` already denies any secret-looking `target_path` before `PathSafetyValidator` ever gets invoked — so the path-level rule is provably unreachable for this scenario. The PR's assertion matches actual behavior; the plan's did not. Same pattern as #1: a correct fix to a plan inconsistency, undocumented as such.

Both deviations are consistent with the plan's stated intent (deny-before-allow, deny precedes allow) — the plan's design was right, its literal test/code snippets were internally inconsistent, and the implementer resolved that correctly. I'd flag this to whoever maintains the plan docs so the checked-in plan text gets corrected too, since it will mislead the next person who copies it literally.

## Gaps (found by tracing control flow and reproducing behavior directly, independent of what either document claims)

**A. The audit trail didn't actually persist anywhere in the one real call site. — RESOLVED.** Landed as commit `a8659d73` on the PR branch. `JsonRpcDispatcher.__init__` now builds one `PreToolGuard` for the dispatcher's lifetime and threads it into every `write_file` call, with a `dispatcher.audit_events()` accessor to retrieve the accumulated trail. Covered by two new tests in `tests/unit/acp/test_dispatcher.py`. Independently re-verified against the pushed commit: diff matches byte-for-byte, 204/204 suite passing, coverage unaffected elsewhere.

**B. `workspace_root=Path.cwd()` was a fragile security boundary. — PARTIALLY RESOLVED (same commit as A).** The dispatcher now takes an explicit `workspace_root` constructor argument, so the containment boundary is a caller-supplied value at the composition root rather than an implicit `Path.cwd()` buried in a leaf function. It still *defaults* to `Path.cwd()` if the caller doesn't supply one — closing this fully requires whatever process actually starts the ACP server (no such startup/bootstrap module exists yet in this codebase) to pass a real, validated project root through to the dispatcher. This piece is **deferred by agreement**, not forgotten, until that bootstrap exists.

Items C–H below are now all resolved as of commit `c2ace2c` (with H resolved as a documentation note, per its own recommendation). The punch list is kept in place, unedited, as the historical record of what was asked for; closure notes and independent verification for each item are in the "Closure verification" section that follows it.

## Punch list — remaining items for hand-off

Each item lists the affected file(s), the exact function/class involved, what's missing, and concrete test names/assertions a follow-up PR could use directly.

### C. `shadow_apply()` guard wiring has zero test coverage

- **Source:** `src/optimus/tools/mutation_tools.py`, `shadow_apply()` (the guard-check block added in this PR, roughly lines 95–110).
- **Tests:** `tests/unit/tools/test_mutation_tools.py`.
- **What's missing:** the only existing call to `shadow_apply` (`test_shadow_apply_checks_guard_before_applier_call`) uses a Plan/Chat-mode context, so `assert_mutation_allowed` raises before the new `PreToolGuard` code is ever reached. Confirmed uncovered directly via `--cov-report=term-missing`. `write_file` and `shell_exec` both got a "guard blocks before side effect" test; `shadow_apply` didn't.
- **Note:** the ACP dispatcher doesn't expose a `shadowApply` RPC method yet, so there's no live production path today — but the gap should close before one is added.
- **Suggested tests to add:**
  - `test_shadow_apply_allowed_after_agent_approval()` — mirror `test_write_file_allowed_after_agent_approval`: build an approved AGENT-mode context, a `PreToolGuard.for_workspace(workspace_root=tmp_path, ...)`, a `ProbeApplier`, call `shadow_apply(patch_text, context=..., applier=probe, guard=guard)`, assert `probe.called is True` and the returned `PatchResult`.
  - `test_shadow_apply_checks_pre_tool_guard_before_applier_call()` — mirror `test_shell_exec_checks_pre_tool_guard_before_runner_call`: use the existing `DenyGuard` test double, assert `pytest.raises(MutationForbidden, match="blocked by test guard")`, `applier.called is False`, and `guard.requests[-1].action == "shadow_apply"`.

### D. `EvidenceAcquisitionService.extract()` guard call and the HOLD branch are untested

- **Source:** `src/optimus/evidence/acquisition.py`, `extract()` and the shared `_assert_pre_tool_web_allowed()` helper (the HOLD branch, roughly lines 224–225).
- **Tests:** `tests/unit/evidence/test_acquisition.py`.
- **What's missing:** the one new test (`test_search_pre_tool_guard_blocks_before_gateway_transport`) only exercises `search()`'s BLOCK path. Nothing proves `extract()` — which resolves an actual, potentially attacker-supplied URL — calls the guard at all, and nothing anywhere (`search()` or `extract()`) exercises the HOLD branch of `_assert_pre_tool_web_allowed`.
- **Suggested tests to add:**
  - `test_extract_pre_tool_guard_blocks_before_gateway_transport()` — mirror the existing search test but call `service.extract(request, execution_mode=ExecutionMode.AGENT)` with a `BlockingPreToolGuard`; assert `pytest.raises(ToolCallRejected, match="blocked network egress")` and `gateway.calls == []`.
  - A `HoldingPreToolGuard` test double returning `PreToolResult(PreToolVerdict.HOLD, "network.unexpected_egress", "unexpected network egress requires approval")`, used in:
    - `test_search_pre_tool_guard_hold_rejects_before_gateway_transport()` — assert `pytest.raises(ToolCallRejected, match="human approval required: unexpected network egress requires approval")`, `gateway.calls == []`.
    - `test_extract_pre_tool_guard_hold_rejects_before_gateway_transport()` — same assertion shape for `extract()`.

### E. Unicode confusable/spoofing detection misses bidi and zero-width characters

- **Source:** `src/optimus/guardrails/command_safety.py` — `_CONFUSABLES` frozenset and `_contains_control_sequence()` / `_contains_confusable()`.
- **Tests:** `tests/unit/guardrails/test_command_safety.py`.
- **What's missing:** `_CONFUSABLES` covers 12 fixed Cyrillic/fullwidth code points; `_contains_control_sequence` only catches C0 controls and DEL (`ord < 32` or `== 127`). Verified directly that an RTL-override character (U+202E) and a zero-width space (U+200B) — standard techniques for disguising a filename or command — pass both checks and fall into the generic `shell.unclassified_command` HOLD bucket instead of being flagged as a confusable/spoofing attempt. Still fails safe (HOLD, not ALLOW), but gives a reviewer working the hold queue no signal about *why*.
- **Suggested fix:** add a check using `unicodedata.category(char) in {"Cf"}` (or an explicit set: U+200B, U+200C, U+200D, U+2060, U+FEFF, U+202A–U+202E) and route matches to their own rule, e.g. `shell.unicode_bidi_control` (BLOCK), parallel to `shell.unicode_confusable`.
- **Suggested tests to add:**
  - `test_rtl_override_in_argument_blocks(tmp_path)` — command containing `"‮"` → `BLOCK`, new rule_id.
  - `test_zero_width_space_obfuscation_blocks(tmp_path)` — command with a keyword split by `"​"` → `BLOCK`, new rule_id.

### F. No test exercises the "destructive, needs review" branch

- **Source:** `src/optimus/guardrails/command_safety.py` — `_is_destructive_command()`.
- **Tests:** `tests/unit/guardrails/test_command_safety.py`.
- **What's missing:** `dd`, `shred`, `find -delete`, `git reset --hard`, and `git clean -fdx` are all correctly implemented and correctly resolve to `shell.destructive.review` (HOLD) — verified directly by running all five — but none is asserted in the test file. This gap originates in the plan's own test file and was faithfully carried into the PR.
- **Suggested tests to add** (one per command family, all asserting `HOLD` / `rule_id == "shell.destructive.review"`):
  - `test_dd_command_holds_for_review(tmp_path)` — `("dd", "if=/dev/zero", "of=/dev/sda")`.
  - `test_shred_command_holds_for_review(tmp_path)` — `("shred", "-u", "secret.txt")`.
  - `test_find_delete_holds_for_review(tmp_path)` — `("find", ".", "-delete")`.
  - `test_git_reset_hard_holds_for_review(tmp_path)` — `("git", "reset", "--hard")`.
  - `test_git_clean_fdx_holds_for_review(tmp_path)` — `("git", "clean", "-fdx")`.

### G. No DNS/SSRF pinning in `NetworkSafetyValidator`

- **Source:** `src/optimus/guardrails/network_safety.py` — `NetworkSafetyValidator.validate_url()`.
- **Tests:** `tests/unit/guardrails/test_network_safety.py`.
- **What's missing:** the allowlist matches on hostname string only. A literal private/loopback/link-local/cloud-metadata IP target (e.g. `169.254.169.254`, `127.0.0.1`) that isn't on the allowlist currently just falls into `HOLD` ("needs approval") like any other unrecognized host — acceptable, but not distinguished from an ordinary unknown domain, and there's no protection at all against DNS rebinding on an *allowed* hostname (the validator never sees a resolved IP).
- **Suggested fix:** add a dedicated check that `BLOCK`s (not `HOLD`s) when the literal hostname is a private/loopback/link-local/metadata-range IP, since those should never be approvable via the generic "unexpected egress" path.
- **Suggested tests to add:**
  - `test_literal_private_ip_target_is_blocked()` — `validate_url("https://169.254.169.254/latest/meta-data/")` → `BLOCK`, new rule_id (e.g. `network.private_ip_target`).
  - `test_literal_loopback_target_is_blocked()` — `validate_url("https://127.0.0.1/admin")` → `BLOCK`.
- **Note:** true DNS-rebinding protection (checking the *resolved* IP at connect time, not just the string hostname) is a bigger architectural item that belongs in the real HTTP/gateway transport layer, not this validator. Worth a design discussion, not just a unit test.

### H. TOCTOU on path containment

- **Source:** `src/optimus/guardrails/path_safety.py` — `PathSafetyValidator._inside_workspace()` (resolves symlinks at validation time) and `src/optimus/tools/mutation_tools.py` — `write_file()` (the actual `Path(path).write_text()` happens afterward).
- **What's missing:** a symlink swapped in the window between validation and the real write would bypass containment. Low severity for a single-user local agent today; not really unit-testable as a race, so the recommended action is a documentation addition rather than a test.
- **Suggested action:** add an explicit "accepted risk" note to the plan's Security Boundary Notes section (or open a design discussion if the team wants to close it, e.g. by opening with `O_NOFOLLOW`-equivalent semantics and re-checking the resolved path immediately before writing).

## Closure verification (commits `5d7efa4`, `c2ace2c`)

Independently re-verified against the pushed commits (fresh `git fetch` + `reset --hard` in the review clone, then re-run):

- **C, F** (commit `5d7efa4`): diff matched claimed byte-for-byte (3 files, +156/-0, test-only). 44/44 targeted tests and 214/214 full suite confirmed. Confirmed the two new `extract()` tests in D actually reach the new guard call rather than being rejected earlier for an unrelated reason — they pre-seed `registry.record_search_results(...)` so Plan 4's provenance check passes, and the `match=` assertions use reason strings (`"blocked network egress"`, `"human approval required: unexpected network egress requires approval"`) that are unique to the test-double guards and don't appear anywhere else `ToolCallRejected` is raised in this service.
- **D**: covered above; `acquisition.py` coverage 93%, confirmed.
- **E, G** (commit `c2ace2c`): diff matched claimed byte-for-byte (5 files, +63/-0). 28/28 targeted, 218/218 full suite confirmed. Independently probed edge cases beyond the checked-in tests: `0.0.0.0`, bracketed IPv6 loopback `[::1]`, IPv6 link-local `[fe80::1]`, and an IPv4-mapped-IPv6 metadata address (`::ffff:169.254.169.254`, a known SSRF bypass trick) are all correctly `BLOCK`ed — the fix generalizes beyond the two literal test cases because it delegates to stdlib `ipaddress` rather than string-matching. One residual, minor gap found: RFC 6598 carrier-grade-NAT space (`100.64.0.0/10`) is not covered by Python's `ipaddress.is_private`/`is_link_local`/`is_reserved` on this interpreter, so it falls through to the ordinary `HOLD` path rather than a hard `BLOCK`. Low severity (still fail-safe, just approvable rather than not) — flagging for awareness, not as a new must-fix item.
- **H**: the Security Boundary Notes addition in the plan doc accurately describes the risk and correctly scopes the fix to follow-up hardening rather than claiming it's closed.
- **B remainder**: confirmed still open and correctly left alone, as agreed.

## What's solid

The core design — deny-before-allow, mode short-circuiting before allow-list evaluation, HOLD-by-default for anything unclassified or ambiguous, MCP held pending Plan 6's trust registry, and blocking before any runner/writer/applier/transport call — is implemented exactly as specified and is properly fail-closed everywhere I probed it. The three "hot" modules (`permissions.py`, `command_safety.py`, `pre_tool.py`) that the plan calls out as safety-critical do carry the heaviest test weight. The self-review section in the plan doc is accurate about what's *not* covered (durable audit persistence, replay-resistant approvals, MCP trust, CI parity) — those are correctly deferred to Plans 6/7, not silently dropped.

## Status summary

| Item | Status | Commit |
|---|---|---|
| A — dispatcher default guard / ephemeral audit sink | Resolved | `a8659d73` |
| B — `Path.cwd()` workspace boundary | Partially resolved; remainder deferred by agreement pending ACP server bootstrap | `a8659d73` |
| C — `shadow_apply` guard test coverage | Resolved | `5d7efa4` |
| D — `extract()` guard + HOLD branch coverage | Resolved | `5d7efa4` |
| E — Unicode bidi/zero-width detection | Resolved | `c2ace2c` |
| F — destructive-command HOLD test coverage | Resolved | `5d7efa4` |
| G — DNS/SSRF pinning (literal IP targets) | Resolved (literal-IP scope only; DNS rebinding at connect time remains a transport-layer follow-up, by design) | `c2ace2c` |
| H — TOCTOU on path containment | Resolved (documentation note, as recommended) | `c2ace2c` |
| Plan doc's `command_safety.py`/Task 8 inconsistencies | Resolved | `a8659d73` |
| Residual — RFC 6598 CGNAT range not hard-blocked in G | New, minor, informational only | — |
