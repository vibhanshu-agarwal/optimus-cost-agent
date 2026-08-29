# Plan 6 Security & Architecture Review — Prompt-Injection, MCP Trust, CI Guardrail Parity

**Reviewer role:** Senior Architect / Network Security
**Plan under review:** `docs/superpowers/plans/2026-07-04-prompt-injection-mcp-trust-ci-guardrail-parity.md`
**Verified against:** current `src/optimus/guardrails/*` (Plan 5), roadmap Plan 6 deliverables.
**Verdict:** Solid deterministic foundation and correct fail-closed defaults, but there is **one blocking internal contradiction** (the parity tests cannot pass with the artifacts the plan ships) and **several security gaps** where a control is recorded/tested but not actually enforced in any runtime path.

---

## Blocker (plan is internally inconsistent as written)

### B1. Task 5 parity tests will FAIL against the plan's own config

`GuardrailRuleSet.phase1()` declares six checks including `pytest-coverage`. The parity tests assert that name appears in **both** `.pre-commit-config.yaml` **and** the CI workflow:

- `test_pre_commit_uses_guardrail_rule_set` → `assert expected <= actual`
- `test_pre_commit_and_ci_name_the_same_guardrail_checks` → `assert pre_commit & expected == ci & expected == expected`

But the `.pre-commit-config.yaml` the plan provides has **no `optimus-check: pytest-coverage` hook** (coverage runs only in CI). So `load_pre_commit_check_names()` returns 5 of 6 names, `expected <= actual` is False, and two of the three parity tests fail. This directly contradicts Task 5 Step 6 ("Expected: PASS") and the Self-Review's "local hooks and CI run the same named guardrail checks."

**Fix:** either add a local `pytest-coverage` hook (or a no-op named marker) to `.pre-commit-config.yaml`, or split the rule set into `local_checks` vs `ci_checks` so `pytest-coverage` is CI-only and the parity assertion compares the intersection intentionally. Decide deliberately — do not just delete the assertion.

---

## High (security controls that don't actually protect anything yet)

### H1. `MCPAutoloadGuard` is never invoked — cloned-repo denial is not enforced

I searched `src/` for any autoload/MCP-loader/planner-exposure call path: there is none. The guard is constructed and asserted only inside `test_mcp_trust.py`. A control that no runtime code calls provides zero protection; the "cloned repo MCP servers never auto-load" property holds only inside a unit test. The roadmap asks for tests, but a security review must note that until a real ingestion/discovery component calls `evaluate_autoload_path()` **and refuses to proceed on `allowed is False`**, poisoned `.cursor/mcp.json` / `.mcp.json` in a cloned repo is not blocked by anything in the running system. Add an explicit integration point (or an out-of-scope note naming the exact future component and plan that will wire it) rather than leaving it implied.

### H2. Scope claims "before planner exposure" but only the execution path is guarded

Scope and Source Anchors say descriptors are inspected "before planner descriptor exposure." The plan only wires the registry into `PreToolGuard` (tool-execution time). Nothing scans or gates descriptors before they are rendered into the planner/LLM context. Prompt injection via a tool *description* does its damage the moment the planner reads it — i.e., before any tool call. Either add a planner-exposure scanning hook or explicitly downgrade the scope wording; as written the plan overclaims coverage of the primary injection vector.

### H3. `permission_scope` is recorded but never enforced

`MCPServerTrustRecord.permission_scope` (e.g. `read_only_metadata`) is captured at registration and then ignored. `validate_tool_call()` checks server registration, approval, hash, allowed-tools, and re-scans the descriptor — but never compares the requested operation against the declared scope. A tool approved as read-only can do anything its schema permits. Scope is currently decorative. Either enforce it (map scope → permitted side-effect classes and check at call time) or document that scope is advisory-only in Plan 6 and name the plan that enforces it.

### H4. Manifest hash/scan omits `env`, args, and launch parameters

`MCPServerManifest` = `server_id`, `command`, `tools`. There is no `env`/`cwd`/extra-args field. Real MCP server definitions carry environment variables — a classic secret-exfiltration channel (secrets handed to the server process) and a silent behavior switch. Because `env` isn't in the hash, changing it does **not** force reapproval, and because it isn't in `descriptor_text()`, it is never scanned. Add all security-relevant launch parameters (especially `env`) to both `manifest_hash()` and `descriptor_text()`, or state explicitly why they're excluded.

### H5. TOCTOU — the guard trusts a caller-supplied manifest object

`validate_tool_call(manifest=...)` and `PreToolRequest.mcp_manifest` accept the manifest as data. Nothing binds the bytes that were hashed/scanned to the bytes actually used to launch or invoke the server. If the component that presents the manifest to the guard differs from the one that executes, an attacker can show a benign manifest to the guard and run a poisoned one. For Plan 6 (no real execution) this is latent, but the design should require the guard to be the **authoritative** fetch/hash point at execution time. Add this as an explicit constraint for the Plan 7/8 wiring so it isn't lost.

---

## Medium

### M1. Confusable detection is partly dead code (NFKC folds it away)

`ConfigTrustScanner.scan_text()` normalizes with NFKC, then checks `_CONFUSABLES` against the **normalized** text. NFKC folds the fullwidth entries (`ａ`, `ｅ`, `ｉ`, `ｏ`) to ASCII, so those entries can never match — only the Cyrillic homoglyphs survive. No test exercises the confusable rule, so this would ship unnoticed. Run confusable/punycode detection on the **raw** input (before normalization). The identical latent bug already exists in `command_safety.py` (`_contains_confusable` after line-34 NFKC) — fix both.

### M2. CLI config scanner fails OPEN on unreadable/binary files

`scan_paths()` silently `continue`s on `UnicodeDecodeError` and on non-files. That is the exact "parsing failure worked around" the Security Boundary Notes forbid ("a blocked config file is a trust failure, not a parsing failure to work around"). A payload hidden behind deliberately invalid UTF-8, or a mixed-encoding file, is skipped rather than blocked, and the `--no-verify`-style bypass isn't even needed. Fail closed: read bytes with `errors="replace"` and scan, or report unscannable files as a block.

### M3. Default config-scan globs miss high-value poisoning surfaces

`_DEFAULT_AGENT_CONFIG_GLOBS` covers root `AGENTS.md`/`CLAUDE.md`, `.agents`, `.claude`, `.codex/*.toml`, `.cursor/*.json`. It misses, among others: `.mcp.json` (Claude Code root MCP config), `.vscode/mcp.json`, Cursor rule files `.cursor/**/*.mdc`, `.github/copilot-instructions.md`, `.windsurfrules` / `.clinerules`, and **nested** (non-root) `AGENTS.md`/`CLAUDE.md` in monorepos (the bare `AGENTS.md` glob only matches root). The mandate is "treat repo config as untrusted input"; the default set is narrower than the mandate. Broaden the globs and add a fixture asserting a nested/`.mcp.json` payload is caught.

### M4. Injection regexes are narrow and order/gap-dependent

The text rules require specific verbs and word order within `.{0,80..120}` windows. Trivial evasions: synonyms not in the alternation ("disregard", "prior", "forget everything above"), or padding past the bounded gap. This is inherent to deterministic scanning and acceptable **as defense-in-depth**, but the plan/README should frame it that way rather than implying reliable blocking. Consider widening the `ignore_previous` alternation and removing/loosening some length bounds.

### M5. `--no-verify` block is bypassable — misses `-n`, hooksPath, and pre-subcommand options

`_is_git_no_verify_bypass()` only matches when `command[1] in {"commit","push"}` and the literal `"--no-verify"` token is present. It misses:
- `git commit -n ...` (`-n` is the documented short form of `--no-verify`),
- `git -c core.hooksPath=/dev/null commit ...` (disables hooks with no `--no-verify` at all),
- any global option before the subcommand (`git -c ... commit` shifts the subcommand off index 1),
- env-based bypass context (`HUSKY=0`, `GIT_CONFIG`).

This is the specific control Task 4 adds, so the false-negatives matter. At minimum add `-n`, detect `core.hooksPath` overrides, and locate the subcommand by scanning tokens rather than assuming index 1.

### M6. Allowed MCP calls corrupt the audit record

In `check()`, other surfaces return `None` from `_validate_surface()` on allow, so the final allow is audited with `failed_checks=()` and the permission layer. The plan's MCP branch instead returns a **non-None** `ALLOW` `PreToolResult`, so `check()` audits it with `layer="pre_tool"` and `failed_checks=("mcp.trusted_tool_allowed",)` — labeling a passing trust check as a failed check, on the highest-risk surface. Return `None` on MCP allow (and let `check()` emit the standard allow), or special-case the allow in `check()`.

### M7. No real committed-secret scanner despite the threat model

The hook named `secret-scan` runs the prompt-injection config scanner, not a secret detector. There is no gitleaks/detect-secrets stage anywhere, yet the whole plan is about secret access/exfiltration. The name invites false assurance. Rename the hook to reflect what it does (`config-trust-scan`) and consider adding a genuine committed-secret scan to the rule set.

---

## Low / polish

- **Parity is nominal, not behavioral.** `load_*_check_names` just substring-matches `optimus-check: <name>` anywhere in the file — a disabled hook with a leftover comment still "passes," and identical names don't prove identical config/severity between local and CI. Consider parsing structure and asserting the invoking command too.
- **AST-grep rule set is a single `eval(...)` deny.** Misses `exec`, `os.system`, `subprocess(..., shell=True)`, `pickle.loads`, `__import__`, `compile`. Fine if intentionally minimal; note it as such.
- **`cloned_repo_denied` returns `requires_human_approval=True`.** Reasonable as an explicit escape hatch, but slightly at odds with the "never auto-load" wording — clarify that human approval, not auto-load, is the only path.
- **Tests assert `findings[0].rule_id`** (order-dependent). Prefer `any(f.rule_id == ...)` for resilience, as the other tests already do.
- **Redundancy:** Ruff `select` includes `S` (flake8-bandit) while Bandit also runs. Harmless, but note it.

---

## What the plan gets right (preserve these)

- Fail-closed default: no registry → `HOLD mcp.requires_plan6_trust_registry`; existing Plan 5 MCP-hold test stays green.
- Deny-before-allow ordering preserved: permission policy runs first, registry HOLD/BLOCK still overrides an approval.
- Manifest-hash change forces reapproval; descriptor is **re-scanned on every call**, not just at registration.
- Registration rejects `allowed_tools` not declared by the manifest (no phantom-tool approval).
- CI uses `pull_request` (not the dangerous `pull_request_target`) and a clean checkout as the enforcement layer for skipped local hooks.

---

## Recommended priority order

1. Fix **B1** (parity test contradiction) — plan cannot execute green otherwise.
2. Address **H1/H2** — wire the autoload guard and/or planner-exposure scan, or tighten scope wording so the plan does not claim unenforced protection.
3. Close **H4/H5** and **M5** — env coverage in the hash/scan, and the real `--no-verify`/hooksPath bypasses.
4. Fix **M1/M2** — dead confusable check and fail-open CLI, both of which silently weaken detection.
5. Decide **H3** (scope enforcement) explicitly — enforce or document as advisory.
