# Plan 9.96 Operator-Controlled Debug and Launch Trust Evidence

**Status:** Real-dependency evidence verified on 2026-07-23 (Task 9).

**Implementation SHA before report/docs closure:** `031fc651dbc6b1d21cd714a0c8f5db9ea006b028`

This report records content-free evidence only. It does not retain prompts, fixture contents, raw
credentials, provider responses, live workspace logs, approval nonces/handles, URI user information,
or Redis record bodies.

## Approval and Foundation Anchors

| Role | Immutable anchor |
|---|---|
| Frozen security contract SHA-256 | `8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C` |
| Security-contract approval record SHA-256 | `63F2200FE3A4540A4455CF737B42E042D9613648454736B543846A6CB4BD211D` |
| Plan 9.9 foundation commit | `f120a5afde39e3b3a8a405211ae71653b6e75665` |
| Plan 9.96 Tasks 0–8 foundation | `d0c467041015b5f3630c7d4b984c0a2b396a8bb8` (Task 8) via PR #60 |
| Plan 9.98 real-ACPX unblocker | `74d4ff21173a597c3b274cf6e6cbdf8a7eb43697` |
| Plan 9.99 URI canonicalization | `f2b6b21` (merged PR #66) |
| Logging-surface audit manifest SHA-256 | `F887B5F0807C426C02768D995A94D7D142D079A7CCBC8C84081D0F5C442C5592` |
| Launch-policy module SHA-256 (worktree) | `297b4f3abe99d2fa68e376b53116ec5e47ff9b8c227fb809eadc14750ca190b3` |
| Task 9 evidence branch base | `031fc651dbc6b1d21cd714a0c8f5db9ea006b028` |

Task 0 re-verified on this branch after restoring LF blob bytes (Windows `core.autocrlf=true`
checkout had rewritten CRLF, changing the raw SHA-256 without content drift). Git object identity
was unchanged; restored working-tree LF bytes are not staged.

## Claim-to-Evidence Matrix

| Claim | Named evidence |
|---|---|
| Frozen contract + approvals precede closure | Task 0 digest/approval-field/Git-object checks; contract SHA above |
| Unapproved launch stops before mutation | B1 capture exit 2 (`no launch approval`); fixture SHA unchanged `fe63aa7579…dae7c` |
| One-shot succeeds once; replay fails | B4: `one-shot-first-exit 0`, `one-shot-replay-exit 2`, `one-shot-replay-proof-ok` |
| Durable approval supports headless inspect | B2 `appr_1b7e629343046ac70019e7e6` / snapshot prefix `78ad8cca1c589a34`; B3 inspect exit 0 |
| Security-value change invalidates approval | B5 exit 2 — `configuration changed since approval. Re-approve.` |
| Ordinary real ACPX session | C1 retry: nonce `run_f1c06b1e4209de0a01769038`; capture/verify 0; COMPLETED; `[file_reader, write_file]`; elevated comparison absent; cost `0.006738` |
| Elevated real ACPX session | C3/C4: nonce `run_4a501b8acb6f2db56fc12e03`; verify 0; COMPLETED; tools same; elevated comparison present (1 record); tags 0 (valid); cost `0.006765`; outer `agent_child` exact five names; `acpx_client` []; grant state `none` |
| Promotion / secret absence | Tool `verify` exit 0 both modes; content-free pattern scan 15 files / 0 hits; no `attempt-*-transcript.jsonl` |
| Approval cleanup | D revoke — durable absent (`D_durable_present False`); artifacts retained |
| Exact child-key / mode oracles | Outer audit + manifest assertions in C1/C3 summaries and E2E verification nodes |
| Automated quality | Focused then full suite + coverage + Ruff + logging-surface verifier (below) |
| Frozen legacy helpers excluded | `git diff --quiet` on Plan 9.87/9.88 capture helpers |
| Owned FUs only | Closes `P9.85-FU-7` and `P9.9-FU-1`; Plan 9.97 isolation sentence preserved; P9.96-FU-1..7 disclosed to backlog |

## Real Ceremony Outcomes (content-free)

| Step | Result codes / digests |
|---|---|
| B1 unapproved | exit 2; nonce `run_eaa11bbf8977e1db15c7018a` |
| B2 durable | approval id `appr_1b7e629343046ac70019e7e6`; snapshot prefix `78ad8cca1c589a34`; policy `P9.99-v1` |
| B3 inspect | exit 0 |
| B4 one-shot | first 0 / replay 2 / proof-ok |
| B5 invalidation | exit 2 |
| C1 ordinary | capture 0 / verify 0 / nonce `run_f1c06b1e4209de0a01769038` |
| C3 elevated | capture completed / verify 0 / nonce `run_4a501b8acb6f2db56fc12e03` |
| D revoke | durable revoked |

OS credential store backend: `keyring.backends.Windows.WinVaultKeyring`. Independent client:
`acpx` 0.12.0. Agent child keys observed (names only): `OPTIMUS_AGENT_MODEL`, `OPTIMUS_API_KEY`,
`OPTIMUS_GATEWAY_URL`, `OPTIMUS_PRODUCTION_MODE`, `OPTIMUS_REDIS_URL`.

## Immutable Artifact SHA-256 Values

### Ordinary (`C:/tmp/optimus-plan996-artifacts/ordinary`)

| Artifact | SHA-256 |
|---|---|
| `transcript.stdout` | `00a73120b2ff77fe9d6b64520a7f6e25ee4accb2874aca173d5fe6f3faee26c0` |
| `transcript.stderr` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `external-session-evidence.json` | `d4cb7f988667bfee212f4b763a54c27e1507f4d8d8e0da00adca6aa322c90248` |
| `audit-snapshot.ndjson` | `95879c6ee7109d253e8077be9eb17fbf784c7070c1de1feef4993ba755dc6cd2` |
| `debug-snapshot.ndjson` | `129469b99836f2238ee26cb06927f83dc7bb705ba7867cb301067caa9c834154` |
| `sanitizer-manifest.json` | `b9b6cac152a76ea4c32a11ac7a8354fee1ee8cbf9d21c805f968b0af68e442e7` |

### Elevated (`C:/tmp/optimus-plan996-artifacts/elevated`)

| Artifact | SHA-256 |
|---|---|
| `transcript.stdout` | `cc25663aa290dbee0c86f0c8a2ef4ca39b8760e65fd0c218082e134c3353e1d3` |
| `transcript.stderr` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `external-session-evidence.json` | `049c9c243afd9da0b5e3def9fddfec64de7fa2fc155df2d49add336db05287f4` |
| `audit-snapshot.ndjson` | `3b965d72930ab811b9f86ab880b3032afd4f33f43626565ec07c8a8c233bf82d` |
| `debug-snapshot.ndjson` | `b4296df47b525fd196548acdc65ac87a2a5800c6059310d944857fe046f90ce6` |
| `sanitizer-manifest.json` | `5fa4c2ee564e0725e7deb77e29925e4ca29aa6f99dddea175058b2fe2687c002` |

E2E verification nodes (artifact consumers only; no new live session):

```text
tests/e2e/acp/test_plan996_authorized_launch.py::test_plan996_ordinary_session_evidence_verification
tests/e2e/acp/test_plan996_authorized_launch.py::test_plan996_elevated_session_evidence_verification
→ 2 passed
```

## Final Offline Gates

```text
Secret/canary scan:     15 files, 0 hits; 0 legacy raw transcripts
Focused Plan 9.96 paths: intermittent WinError 6 on known flake set; clean after isolation
Full default suite:     1469 passed, 20 skipped, 27 deselected (clean retry after flake; +2 vs pre-Task-9 baseline from the new e2e-marked verification nodes)
Branch coverage:        86.38% (required: 80%)
Ruff:                   All checks passed (`uv run python -m ruff check .`)
Logging-surface audit:  passed
git diff --check:       clean (LF-restored frozen docs remain unstaged)
Frozen 9.87/9.88 helpers: unchanged
```

The first full-suite attempt failed the same 11-test WinError 6/50 set already tracked as
**Backlog: Windows Subprocess Handle-Duplication Flake**. A subsequent clean run (1469 passed)
satisfied the Task 9 gate on this host.

## Limitations and Disclosures (tracked, not fixed in Task 9)

Per the 2026-07-18 scope-conflict ruling, Plan 9.96 closes only `P9.85-FU-7` and `P9.9-FU-1`. The
following are disclosed into the roadmap as tracked-not-yet-scheduled backlog entries (no Plan 9.96
code change):

| ID | Summary |
|---|---|
| `P9.96-FU-1` | `StartupConfigurationError` missing `optimus-agent:` prefix in `acp/__main__.py` |
| `P9.96-FU-2` | Duplicated TOCTOU comment block in `acp/__main__.py` |
| `P9.96-FU-3` | `append_launch_audit_event` docstring says trusted external runtime root but uses `workspace/.optimus` |
| `P9.96-FU-4` | Latent unroutable `DEFAULT_AGENT_MODEL = "glm-5.2"` in `agent/defaults.py` (ACP path injects `claude-haiku`) |
| `P9.96-FU-5` | Frozen dataclass exceptions mask real codes via `@contextmanager` (`FrozenInstanceError`) |
| `P9.96-FU-6` | Frozen plan Task 9 CLI arg-order / PATH assumptions; execution uses `uv run` + `--workspace-root` before subcommand (applied; not a code defect) |
| `P9.96-FU-7` | Approve ceremony writes durable approval with no y/N confirm; bare-shell display rows may be empty when settings are keyring/default-sourced |
| Inner-audit ordering (from Plan 9.98) | Inner `optimus-agent` audit can omit keyring-resolved `OPTIMUS_API_KEY` because audit precedes `apply_local_defaults`; outer post-default audit remains authoritative for child-key evidence |
| Autocrlf hygiene | Windows `core.autocrlf=true` without `.gitattributes` LF pins corrupts raw SHA-256 checks of frozen markdown; recommend separate hygiene commit |

## Custody

Closes **`P9.85-FU-7`** and **`P9.9-FU-1`** only. Plan 9.97 retains its Plan 11 isolation sentence.
Plan 9.98/9.99 remain separately recorded. Frozen security contract and approval record bytes are
unchanged in Git objects.
