Cost. The guard is pure validation logic — zero LLM cost on the deterministic path; the optional classifier is finitely bounded and rare. Pairing the guard with sandboxing (it is the inspection layer, not a replacement for isolation) keeps the agent moving
without constant hand-holding.

# 4. Shell Command Sanitization

Shell access is the highest-leverage and highest-risk tool surface. Phase 1 defines a local CommandSafetyValidator interface invoked by the pre-tool guard (§3) on every Bash call. The validator is deterministic, runs in-process, and blocks before the command reaches a subprocess.

## 4.1 Required Checks

- Destructive commands — recursive force deletes, disk/format operations, and unsafe overwrites outside the workspace root.

- Pipe-to-shell — any pattern that fetches and executes in one step (curl … | sh, … | bash, process-substitution variants).

- Credential / environment access — reads of .env, key stores, or attempts to exfiltrate environment variables.

- Unicode homoglyph / confusable characters — see §4.2.

- ANSI / control characters — terminal-injection sequences embedded in commands or tool output.

- Insecure transport — plain-HTTP fetches and downgraded TLS where a secure channel is expected.

- Unexpected network egress — outbound connections to hosts outside the gateway-managed allowlist.

## 4.2 The Homoglyph Problem

The nastiest case is a command that looks completely normal. Two strings can be visually identical yet differ at the code-point level: the Latin "i" is ASCII code point 105, while the Cyrillic "і" is Unicode code point 1110. To the eye they are the same character; to the shell they are different, and the shell runs whatever is actually on the other end. The validator normalizes and inspects code points so a confusable hostname or path cannot smuggle execution past a human reviewer.

```python
class CommandSafetyValidator(Protocol):
    def validate(self, command: str, ctx: ToolContext) -> ValidationResult: ...
# ValidationResult.verdict in {ALLOW, BLOCK, HOLD}
# Checks: destructive | pipe_to_shell | env_access | homoglyph
#         | ansi_control | insecure_transport | network_egress
```

## 4.3 Implementation Posture

Tirith is a validator built for exactly this class of check — hostname and path homoglyphs, insecure transport, ANSI injection, pipe-to-shell patterns, and environment manipulation — and is a credible candidate implementation. The design does not depend on Tirith: the contract is CommandSafetyValidator, satisfied by Tirith or an equivalent validator. Whatever the backing