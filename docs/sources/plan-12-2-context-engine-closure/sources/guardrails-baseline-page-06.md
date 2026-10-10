## 2.5 Decision Order

The engine evaluates in a fixed, deterministic order and returns a single PermissionDecision:

| Stage | Result / next step |
|---|---|
| Mode overlay | Reject mutation outside approved Agent mode |
| User deny list | DENY wins and stops evaluation |
| Project allow list | ALLOW only within mode and deny constraints |
| Impact class | HOLD for existing human review when required |
| Reserved borderline classifier | ALLOW or HOLD only after deterministic checks; cannot overturn DENY |

The optional classifier is consulted only for genuinely borderline calls that survive the deterministic stages; it can never overturn a deny. Its decision and rationale are persisted to the audit trail.

Cost. The deterministic stages carry zero LLM cost. The borderline classifier is a cheap, finitely bounded model routed through the Optimus Gateway and invoked only when the rule layers are inconclusive — never on the hot path of an already-allowed or already-denied call.

# 3. Pre-Tool Guard / Hook Layer

Hooks are handlers attached to specific points in the agent's workflow. The one that matters for guardrails is the pre-tool hook: it fires after the agent has assembled a tool call but before that tool actually runs. It is the last inspection point at which a bad command can still be blocked, and it closes the gap between "the model decided to do X" and "X actually happens." (Claude Code names this point PreToolUse; the mechanism is general and harness-agnostic.)

Phase 1 introduces a PreToolGuard component that sits at this junction for every tool class, not only shell. It validates shell commands, file edits, MCP calls, and network / web calls before execution, and returns an allow, block, or hold decision that feeds the same audit trail as the permission engine.

## 3.1 Deterministic First

The guard runs least-glamorous, most-reliable checks first: regular expressions, rule tables, AST inspection, and path-containment checks. These are fast, deterministic, and last-mile. Only when a call survives the deterministic stage and remains genuinely ambiguous is a model classifier consulted, under the same trust, capacity and accounting discipline as §2.5. The order is non-negotiable: rules before model, always.

## 3.2 Hook Surface

| Hook point | Validates | Backed by |
| --- | --- | --- |
| Bash / shell | Destructive, pipe-to-shell, homoglyph, ANSI, transport, egress | CommandSafetyValidator (§4) |
| File edit / write | Path breakout, deny-listed paths, secret-file targets | Path-containment + deny rules (§2.2) |
| MCP tool call | Server trust, tool allowlist, scope, descriptor integrity | MCPTrustRegistry (§5) |
| Web / network | Origin allowlist, transport, provenance of fetched content | Gateway origin policy (LLD §9D) |

The classifier remains dormant until separately qualified and activated; this description preserves its architecture contract.
