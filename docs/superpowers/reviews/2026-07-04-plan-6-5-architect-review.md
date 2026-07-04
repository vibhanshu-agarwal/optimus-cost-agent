# Plan 6.5 Architecture Review — Guardrail Hardening and MCP Runtime Trust Wiring

**Reviewer role:** Senior Architect
**Plan under review:** `docs/superpowers/plans/2026-07-04-plan-6-5-guardrail-hardening-mcp-runtime-trust.md`
**Verified against:** current `src/optimus/guardrails/*` (mcp_trust.py, pre_tool.py, prompt_injection.py, command_safety.py, permissions.py), the Plan 6 plan text and both of its review rounds, `pyproject.toml`, the roadmap doc, and the actual `confusable-homoglyphs==3.3.1` package (downloaded and executed locally against the plan's own code to check its claims). Plan 7 (plan file and draft notes) was explicitly out of scope for this pass and was not evaluated.
**Verdict:** Do not execute as written. Task 3 contains a confirmed, reproducible defect that would make the shared confusable detector flag almost all text as dangerous — including the plan's own "benign" test case — which cascades into failing most of the existing Plan 5/6 guardrail suite. Task 4 separately, silently defeats the per-call human-approval gate for every real MCP invocation. Both are cheap to fix. Tasks 1 and 2 are sound and correctly targeted at real gaps in the current code. The roadmap edit is consistent and needs no changes.

---

## Blocker

### B1. `contains_dangerous_confusable()` flags almost all text as dangerous — verified by execution

Task 3, Step 5 proposes:

```python
def contains_dangerous_confusable(text: str) -> bool:
    ...
    return bool(confusables.is_dangerous(text) or confusables.is_confusable(text, greedy=True))
```

I installed `confusable-homoglyphs==3.3.1` (the version this plan pins) and ran this exact function. `confusables.is_confusable(text, greedy=True)` with no `preferred_aliases` does **not** gate on mixed-script content — it returns a truthy list for any string containing a common Latin letter that has a cataloged homoglyph in some other script (a, e, i, o, p, s, t, u, ...), which is effectively every sentence of English or shell/code text. Reproduced results using the plan's exact function:

| input | result |
|---|---|
| `"pytest tests/unit -v"` | `True` |
| `"git status"` | `True` |
| `"hello world"` | `True` |
| `"open agent-config"` | `True` |

`confusables.is_dangerous()` alone (which internally requires `is_mixed_script()` before checking confusability) gives the correct answer for all four inputs above (`False`), and still correctly flags the plan's real attack fixtures — Cyrillic/Greek-mixed payloads (`"run pуtest"`, `"open αgent-config"`, `"load αgent config before approval"`) all return `True` under `is_dangerous()` alone, verified.

Because Steps 6–7 wire this function in unconditionally — `prompt_injection.py`'s scanner and `command_safety.py`'s validator both call it on every scanned string / every command with no gating — this is not a narrow edge case. Every existing ALLOW-verdict test in `test_prompt_injection.py`, `test_command_safety.py`, `test_pre_tool_guard.py`, and the MCP trust suite would flip to BLOCK, and the plan's own new negative test (`test_plain_ascii_payload_is_not_dangerous`) fails immediately, as would Task 5's full coverage gate. This is the same shape as the B1 blocker that stopped the original Plan 6 plan from executing green, but with a much larger blast radius (the whole guardrail suite, not two parity tests).

**Fix:** drop the `or confusables.is_confusable(text, greedy=True)` clause; `confusables.is_dangerous(text)` alone reproduces the intended TR39 mixed-script behavior (confirmed above) without the false-positive storm. If a broader check is wanted, use `is_confusable(text, preferred_aliases=["latin"])` instead of ungated `greedy=True` — but that is a different semantic and needs its own tests. At minimum, add a benign-corpus regression fixture (a handful of plain English/code sentences and git subcommands asserting `False`), not just one ASCII string, so this class of bug can't ship silently again.

---

## High

### H1. `execute_tool()` auto-grants the permission-layer approval gate for every live invocation

Task 4's `MCPRuntimeTrustContext.execute_tool()` builds its `PreToolRequest` with:

```python
approval_granted=execution_mode is ExecutionMode.AGENT,
```

`PermissionPolicy.decide()` (`src/optimus/guardrails/permissions.py`) denies Plan/Chat mode outright for the MCP surface and requires `approval_granted=True` for `ToolSurface.MCP` to reach the ALLOW branch in `_project_allow_decision`. That means AGENT is the only execution mode this seam can ever run under in practice, and for that mode `approval_granted` is hard-coded `True` on every call — not derived from any actual human-approval event. The permission layer's per-call approval gate for the MCP surface is therefore always satisfied by construction, leaving `MCPTrustRegistry.validate_tool_call()` as the only real gate.

This conflates two distinct trust decisions that Plan 5/6 kept separate: "this server/tool was approved once by a maintainer at registration time" (the registry) versus "a human approved *this specific* invocation" (`approval_granted`). Plan 6's own tests set `approval_granted` explicitly per scenario rather than deriving it from execution mode. Neither of Task 4's two new tests exercises the execution-mode/approval interaction, so this regression ships green without anyone noticing the gate is gone.

**Fix:** either thread a real approval signal into `execute_tool()` (e.g. a required `approval_granted: bool` parameter with no default), or explicitly document that this seam treats one-time registry approval as sufficient for the MCP surface and rename the field so it stops implying a live per-call human decision.

### H2. Task 4 doesn't deliver the "autoload denial for workspace-bundled manifests" it claims in Scope

Plan 6.5's Scope section lists "autoload denial for workspace-bundled manifests" as part of the "Minimal MCP runtime trust context." Task 4's `MCPRuntimeTrustContext` adds `deny_autoload_manifest()` as a thin pass-through to the existing (already-orphaned) `MCPAutoloadGuard.evaluate_autoload_path()` — but nothing calls it. `register_explicit_manifest()` never invokes it before scanning/registering, `execute_tool()` doesn't either, and Task 4 ships zero tests exercising `deny_autoload_manifest()` at all. This is the exact "control present but not protecting anything" shape as the H1 finding in the original Plan 6 review — Plan 6.5 exists specifically to close that class of gap, and for this piece it doesn't.

**Fix:** call `deny_autoload_manifest()` from `register_explicit_manifest()` before scanning/registering whenever the manifest path is under the workspace root, and add a test proving a workspace-bundled `.cursor/mcp.json`-style path is rejected by the runtime context itself, not just by the standalone guard in isolation.

---

## Medium

### M1. `register_explicit_manifest()` skips config-level scanning when neither `manifest_text` nor an existing path is supplied

If a caller registers a manifest without passing `manifest_text` and without a real file at `manifest_path`, the method falls straight to `self.registry.register(...)` with no ingestion-guard scan at all — only `register()`'s own descriptor-text scan runs. Likely fine for the cases the plan's tests exercise, but this fallthrough is implicit rather than a documented, deliberate choice.

### M2. Rule-id naming inconsistency between `mcp_trust.py` and `prompt_injection.py`

Task 1's new rule id is `mcp.config_unscannable_path`; the existing analogous check in `prompt_injection.py`'s `scan_paths()` uses `injection.unscannable_path` for the same "not a readable file" condition. Not a functional bug, but two near-identical fail-closed checks in the same guardrail package now use different naming schemes for the same failure mode — worth aligning for anyone building tooling or alerting on rule ids later.

### M3. Private-attribute reach-through is a known, self-flagged wart

`register_explicit_manifest()` accesses `self.ingestion_guard._scanner` directly (`# noqa: SLF001`) instead of `MCPConfigIngestionGuard` exposing a public scan method. The plan already flags this with a `noqa` rather than fixing it. Cheap to clean up while Task 4 is being written rather than carrying the suppression forward.

---

## Low / polish

- The Unicode over-blocking risk isn't limited to B1: `contains_dangerous_confusable()`'s other branch (`normalized != text: return True`) also flags ordinary characters that NFKC-fold — trademark sign, superscript digits, vulgar fractions. Verified: `"Node.js™ package"`, `"footnote¹ reference"`, and `"half½ cup"` all return `True` even after the B1 fix. This is much narrower than B1, but worth a conscious call: either accept these as intentionally blocked and document it (MCP tool descriptions plausibly contain a trademark symbol or fraction character), or scope the NFKC-changed check to the compatibility ranges actually associated with spoofing (fullwidth forms, etc.) rather than all compatibility folding.
- `confusable-homoglyphs`'s published classifiers only go up to Python 3.12 (no 3.13/3.14 classifiers). It is pure Python and imported/ran cleanly in this review's environment, so this is unlikely to bite, but worth a one-line note given this repo targets `>=3.14`.
- Consider naming the Task 3 negative test to signal its role as a regression guard (e.g. `test_common_english_and_shell_text_is_not_dangerous`) and giving it several benign fixtures instead of one ASCII string, since B1 shows a single sample is not enough to catch this class of bug.

---

## What the plan gets right (preserve these)

- Task 1 and Task 2 are both real, correctly targeted gaps. `scan_manifest_path()` genuinely raises `FileNotFoundError` today for a missing path (confirmed by reading the current `src/optimus/guardrails/mcp_trust.py`), and `CommandSafetyValidator.validate()` genuinely has no `env` parameter today, so inline or explicit `GIT_CONFIG_*` bypasses are not caught anywhere in the current code. Both tasks' proposed changes integrate cleanly with the current signatures.
- Scope correctly keeps Redis/JSONL/ProviderUsage/EvidenceLedger work out and reserves it for Plan 7. The roadmap edit is consistent with this: Plan 6.5 is inserted between Plan 6 and Plan 7 in both the plan list and the Recommended Sequence, and the Cross-Cutting section's "Plans 4, 5, 6, 6.5, and 9" references line up with the new numbering.
- Task 2's git-bypass design correctly treats any `GIT_CONFIG_*` env var touching `alias.` / `core.hookspath` / `--no-verify` as fail-closed rather than trying to allowlist safe uses, consistent with the guardrail package's existing "a blocked check is a trust failure, not a parsing failure to route around" philosophy.
- Good instinct on Task 3's overall direction: the two hand-maintained 12-codepoint `_CONFUSABLES` sets duplicated across `prompt_injection.py` and `command_safety.py` are a real maintainability and coverage gap, and consolidating behind one shared, maintained TR39-style detector is the right architectural move. The current draft just needs the API-usage fix in B1 before it's safe to wire in.

---

## Recommended priority order

1. Fix **B1** before this plan is executable at all — and verify with a broader benign-text regression fixture, not just the one ASCII string already in the plan.
2. Resolve **H1** — decide deliberately whether one-time registry approval is meant to substitute for per-call human approval on the MCP surface, and make that explicit rather than accidental.
3. Close **H2** — wire `deny_autoload_manifest()` into `register_explicit_manifest()` and add a test, or walk back the Scope claim.
4. Fold M1–M3 and the Low items into the same revision pass rather than deferring them.
