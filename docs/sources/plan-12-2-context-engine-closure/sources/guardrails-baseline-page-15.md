## 11.1 Guardrail & Workflow Traceability

| Control | Contract | Test category |
| --- | --- | --- |
| Permission decision order (§2) | PermissionPolicy | Permission policy tests |
| Shell sanitization (§4) | CommandSafetyValidator | Shell validator tests |
| Homoglyph / confusable (§4.2) | CommandSafetyValidator | Unicode / homoglyph tests |
| Injection defense (§5) | ConfigTrustScanner | Prompt-injection fixture tests |
| MCP auto-load denial (§5.2) | MCPTrustRegistry | MCP autoload denial tests |
| Local vs CI parity (§6) | pre-commit + CI config | Pre-commit / CI parity tests |
| Bounded loop stop conditions (§7) | GoalLoopController | Loop control tests |
| Skill match & trust (§8) | SkillRegistry / SkillTrustPolicy | Skill loading & trust tests |

## 11.2 Required Test Cases

- Permission — deny precedence over allow; mode short-circuit; impact-class hold; classifier cannot

overturn a deny.

- Shell validator — destructive, pipe-to-shell, env-access, ANSI, insecure-transport, and egress patterns

all BLOCK before subprocess spawn.

- Unicode / homoglyph — Cyrillic-vs-Latin confusables in host and path are detected and held/blocked.

- Prompt-injection fixtures — poisoned config and poisoned tool metadata are caught on ingest.

- MCP — server bundled in a cloned repo does not auto-load; manifest-hash change forces re-approval;

allowed-tools enforced.

- Pre-commit / CI parity — the same rule set fails identically locally and in a clean CI checkout.

- Bypass tests — --no-verify, force-push to main, unsafe .env reads, and unsafe network commands

are all blocked.

- Loop control — stops on completion, on max_iterations, on wall-clock exhaustion and repeated-failure detection; never bypasses §2/§3.

- Skills — a skill loads only on match; an untrusted/draft skill is blocked; declared allowed-tools are

enforced; a skill cannot override project/user deny rules.

# 12. References

External sources consulted for alignment of the controls above: Claude Code's hook lifecycle and the PreToolUse model; the OWASP LLM Top 10 risk catalogue; pre-commit behavior and Ruff's pre-commit