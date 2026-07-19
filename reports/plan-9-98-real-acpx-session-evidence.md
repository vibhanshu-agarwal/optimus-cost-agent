# Plan 9.98 Real ACPX Session Evidence

**Status:** Implemented and real-dependency evidence verified on 2026-07-19.

**Final implementation SHA:** `74d4ff21173a597c3b274cf6e6cbdf8a7eb43697`

This report records content-free evidence only. It does not retain prompts, fixture contents, raw
credentials, provider responses, live workspace logs, or Redis records.

## Approval and Foundation Anchors

| Role | Immutable anchor |
|---|---|
| Plan 9.96 foundation | `d0c467041015b5f3630c7d4b984c0a2b396a8bb8` |
| Plan 9.98 pristine v1 planning commit | `424940ebc62155cfc2422da008efe89457d9ee37` |
| Historical v1 approved plan digest | `3C2C2F0D4521C251748886BB3810BEF1191F6CF75A759FDDA7C55FBA16F7AA0A` |
| V5 bounded-final-state amendment | `5f7dcb379e1a76a0950eccd0f3ba5c99cddf4c64` |
| V5 approved plan digest | `E38F4985E3D213547123A62EC663881F9E5B15704C460397E17F6F94179CC8E2` |
| Controlling v6 amendment | `2ab3bcb8b4e870e9896174e342cf485a20080068` |
| Controlling v6 approved plan digest | `D6D3E563655D8BDDB1FA852995DD9465DB8169273E82916C7AE4158C0AEF605B` |
| Final implementation | `74d4ff21173a597c3b274cf6e6cbdf8a7eb43697` |

The adjacent v1 and v6 approval records contain separate reviewer-agent and operator approvals for
the exact digest-pinned bytes. V2-v5 remain immutable historical records; v6 is the controlling
approved contract for the implemented environment boundary.

## Task 1 Empirical Rulings

- The outer evidence tool must not consume the diagnostic grant. The inner `optimus-agent` consumes
  it exactly once. Direct store probes found the already-consumed grant absent, while current-run
  debug evidence distinguished the modes: zero `launch_authorization_comparison` records for an
  outer-consumes-first/downgraded run and exactly one for an inner-consumes/elevated run. The final
  elevated outer audit independently confirmed `diagnostic_grant_state == "none"`.
- Record presence, not tag-array cardinality, is the elevated oracle. A real elevated record can
  legitimately contain `correlation_tags: []` when credentials are resolved from keyring or the
  sanctioned gateway credential source. Any present tags must have allowlisted SECRET-tier field
  names and 32-character lowercase hexadecimal tag values.
- `acpx --agent` accepts one raw command string. The pinned inner invocation is
  `optimus-agent --workspace-root <workspace> --launch-session-id <session> --debug-trace` plus
  `--diagnostic-grant-id <grant>` only for elevated mode. Windows paths inside that string require
  forward slashes because ACPX treats backslashes as escapes.
- ACPX permission handling is the real client's `--approve-all` mechanism. The outer process still
  uses `shell=False`, an argument list, and `stdin=subprocess.DEVNULL`; no project-authored ACP
  client sends protocol requests.
- Real `acpx --format json` output is the underlying ACP JSON-RPC record stream, not a flattened
  ACPX schema. Session identity comes from `result.sessionId`; the prompt request ID comes from the
  `session/prompt` request; terminal reason comes from `result.stopReason`; tool events are
  `session/update` notifications whose `params.update.sessionUpdate` is `tool_call`, with the tool
  name at `params.update.title`.
- ACP has no cost field. The transcript-derived run ID (`<sessionId>:<prompt-request-id>`) selects
  exactly one real `RedisAgentStateStore.latest_plan_for_run` record; only its positive
  `AgentPlanRecord.cost_usd` is reduced into `external-session-evidence.json`.
- No distinct persisted or transcribed final-state field exists. For this fixed normal ACP path only,
  `final_agent_state == "COMPLETED"` is a bounded inference requiring all three observed predicates:
  `stop_reason == "end_turn"`, `tool_call_count > 0`, and `"write_file" in tool_names`. `end_turn`
  alone is insufficient. The field is omitted when the conjunction does not hold, and this rule does
  not generalize to completion-condition runs or other fixtures.
- The first, outer audit record is the exact child-key evidence source. It contains the effective
  five-name `agent_child` mapping. V6 additively records `acpx_client`, which must contain no
  classified launch-setting names.

## Claim-to-Evidence Matrix

| Claim | Named evidence |
|---|---|
| Independent ACP client drives the real protocol | `test_capture_tool_does_not_import_or_instantiate_project_acp_client`; `test_spawn_authorized_capture_uses_devnull_stdin`; real ACPX ordinary and elevated nodes |
| No mutation occurs before approval | `test_unapproved_capture_leaves_fixture_unmutated`: a fresh workspace had no durable record, capture returned exit 2 with the no-approval remediation, and the fixture's pre/post SHA-256 values were equal |
| Ordinary mode is real and has no elevated oracle | `test_ordinary_session_evidence`; ordinary manifest and run-scoped debug snapshot contain zero comparison records and `elevated_comparison_record_present == false` |
| Elevated mode is real and uses the inner grant topology | Operator TTY ceremony plus `test_elevated_session_evidence_verification`; exactly one comparison record, zero-or-more sanitized tags, and outer `diagnostic_grant_state == "none"` |
| Tool, cost, terminal state, and mutation evidence are run-bound | HMAC-covered transcript, external-session, audit, and debug snapshots; nonce freshness; transcript-derived run ID equals the Redis collector's run ID |
| V6 prevents the nested snapshot mismatch | Mandatory v6 real run completed with empty stderr, no `SNAPSHOT_MISMATCH`, a positive Redis-derived cost, the exact five-name `agent_child`, and empty `acpx_client` |
| Evidence remains sanitized and tamper-evident | Tool `verify` exited 0 for ordinary and elevated manifests; every snapshot digest matched; joined scans reported no hit; logging-surface verifier passed |
| Full regression quality held | 1,432 default tests passed; aggregate branch coverage 86.11%; full Ruff and `git diff --check` passed |
| Frozen ownership boundaries held | Every Plan 9.96 frozen/core path and every Plan 9.98 v1-v6 approval record was byte-unchanged before the implementation commit |

## Real E2E Commands and Results

The ordinary workspace has this one-time, operator-authored durable-approval prerequisite:

```bash
uv run optimus-trust --workspace-root C:/tmp/optimus-plan998-evidence approve --mode durable
```

The tests never author that durable approval or an elevated diagnostic grant.

### Unapproved mutation proof

```bash
uv run pytest "tests/e2e/acp/test_plan996_authorized_launch.py::test_unapproved_capture_leaves_fixture_unmutated" -m e2e -q
```

Result: `1 passed in 0.91s`. The real OS approval store returned no durable record for the fresh
workspace; the capture failed closed with exit 2; the fixture digest was unchanged.

### Ordinary session

```bash
uv run pytest "tests/e2e/acp/test_plan996_authorized_launch.py::test_ordinary_session_evidence" -m e2e -q
```

The first execution exposed a real Windows persistence defect: existing CRLF input was written as
CR-CR-LF. A focused RED regression reproduced the byte mismatch; opening the shared sanitized
destination with `newline=""` fixed every snapshot writer call site. The unit file then passed 121
tests, Ruff and diff checks passed, and the fresh ordinary rerun produced `1 passed in 7.38s`.

### Elevated session

Stage A reset the fixture and wrote nonce `run_bd39db4e5e61f221fd1a9362`. The operator then ran the
approved PowerShell TTY ceremony with literal, single-quoted `{approval_id}`,
`{launch_session_id}`, and `{diagnostic_grant_id}` substitution tokens. Stage C ran only:

```bash
uv run pytest "tests/e2e/acp/test_plan996_authorized_launch.py::test_elevated_session_evidence_verification" -m e2e -q
```

Result: `1 passed in 0.76s`. The Stage C node consumed existing operator-produced artifacts; it did
not author or consume a grant and did not start another live session.

## Real Session Outcomes

| Field | Ordinary | Elevated |
|---|---|---|
| Evidence nonce | `run_5398bb6294855d51811ffee3` | `run_bd39db4e5e61f221fd1a9362` |
| Session mode | `ordinary` | `elevated` |
| Run ID | `session-afc4b98435664847b007a310a69e5339:2` | `session-d756712efb664bedb121fac97162a873:2` |
| Tool names | `file_reader`, `write_file` | `file_reader`, `write_file` |
| Tool-call count | 2 | 2 |
| Total cost USD | `0.006879` | `0.006835` |
| Stop reason | `end_turn` | `end_turn` |
| Bounded final state | `COMPLETED` | `COMPLETED` |
| Comparison records | 0 | 1 |
| Correlation tags | 0 | 0 |
| Manifest comparison flag | `false` | `true` |
| Outer `agent_child` | `OPTIMUS_AGENT_MODEL`, `OPTIMUS_API_KEY`, `OPTIMUS_GATEWAY_URL`, `OPTIMUS_PRODUCTION_MODE`, `OPTIMUS_REDIS_URL` | same exact five names |
| Outer `acpx_client` | empty | empty |
| Outer diagnostic-grant state | `none` | `none` |
| Manifest HMAC/digest verification | exit 0 | exit 0 |

Both `COMPLETED` entries are reported only because each row independently satisfies the three
bounded-inference predicates. Both costs are positive and below the default `0.25` USD live cap.

## Immutable Artifact SHA-256 Values

### Ordinary capture

| Artifact | SHA-256 |
|---|---|
| `transcript.stdout` | `ce9d0264d52c1353df31be37c7f98b4a38e52c6635501a433b170a37a49420fe` |
| `transcript.stderr` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `external-session-evidence.json` | `36c0d9f6ed98eb313d080850e76f6d6df5bdee8dbe8446d672d775b742e188bd` |
| `audit-snapshot.ndjson` | `930181b3c3c77e3978bc80b5bad1fd1e54fb0b1133fd9f6095c24185f24cf9f6` |
| `debug-snapshot.ndjson` | `3c78f9df3004ac0db378c49e600a0b0b80d5003a160cc68e43ceee9cf1c8bec8` |
| `sanitizer-manifest.json` | `232887d6a8a4feb64abda3f95b05342e717106094388a1acb6c83f6b356a159a` |

### Elevated capture

| Artifact | SHA-256 |
|---|---|
| `transcript.stdout` | `6f131494d8026f66dc803ea62fb6d72a19822c775b1b28908d12d6f15adfe5c9` |
| `transcript.stderr` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `external-session-evidence.json` | `98b82c20a8c9af538cd739093de86b56a7b57ad3d3f44c22e91a10e73767ddea` |
| `audit-snapshot.ndjson` | `f84209df37c91066e22b4e75004c87bbf105cfc71ade20b87b7599dfdbc174f5` |
| `debug-snapshot.ndjson` | `bebbee16e0fcd3e11319c9115760caa3055dbfffef2dd0bb0bbac1d57e7e9bd2` |
| `sanitizer-manifest.json` | `8ad36d711d39425db9712b6c54fd114b429f2b6caa0b2d6c3e6cacf40ac155d6` |

For both captures, the tool's own `verify --manifest ... --artifact-dir ...` command returned exit 0
with `optimus-agent: evidence manifest verified`. Independent reviewer runs recomputed the external
snapshot hashes, checked comparison cardinality and tag structure, and obtained the same result.

## V6 Environment-Boundary Regression Proof

Before final Task 5 capture, the mandatory v6 real session used
`C:/tmp/optimus-plan998-artifacts/v6-run_1453b5fb369c3abd1c07f0af/`. It completed with empty
`transcript.stderr`, zero `SNAPSHOT_MISMATCH` occurrences, `stopReason == "end_turn"`, a real
`write_file` event, and positive cost `0.004288`. Its external-session snapshot SHA-256 was
`dcb18943bed5c89ffb4f1ac3bd7b32e681cc5d09ab5fe1ce858b27cd7923c28f`, matching its manifest.
The tool verifier returned exit 0. Its outer audit retained the exact five-name `agent_child` role
and additively recorded empty `acpx_client`, proving the nested environment redesign fixed the prior
failure without changing Plan 9.96 core digest/default logic.

## Final Offline Gates

```text
Targeted non-E2E gate: 658 passed, 12 skipped, 3 deselected
Full default suite:     1432 passed, 13 skipped, 25 deselected
Branch coverage:        86.11% (required: 80%)
Ruff:                   All checks passed
Logging-surface audit:  passed
git diff --check:       clean
```

The independent reviewer reran the full suite and measured 86.08% coverage; both runs were clearly
above the required threshold. The sole pytest warning was the pre-existing `runpy` module-entrypoint
warning from `tests/unit/acp/test_entrypoint.py`.

## Plan 9.96 Task 9 Dependency

Plan 9.96 Task 9 Steps 2, 3, and 5 depend on this plan's implementation commit
`74d4ff21173a597c3b274cf6e6cbdf8a7eb43697` and were blocked until it landed. Plan 9.96 Task 9 may
now run its own Step 2 commands using `tools/run_plan996_acpx_security_evidence.py capture ...
--drive-session`.

This report does not modify Plan 9.96's frozen plan or close its remaining Task 9 work.

## Inner Audit Ordering Observation

The inner `optimus-agent` audit is written before `apply_local_defaults`, so its `agent_child` list
can omit the keyring-resolved `OPTIMUS_API_KEY` even though the effective child environment later
contains that setting. Plan 9.98 does not change the frozen `src/optimus/acp/__main__.py` ordering;
its outer post-default audit is the authoritative five-name evidence source for this capture.

Custody remains with **Plan 9.96 Task 9 Steps 5-6 (limitations disclosure and tracked-roadmap
assignment)**. The parent plan must assign this observation a named tracked roadmap entry before it
closes; Plan 9.98 neither fixes nor silently drops it.

## Separate Plan 9.99 Prerequisite

The v6 audit found a distinct Plan 9.96 conformance defect: SECURITY-tier URI values are folded into
the security snapshot after URI-userinfo masking, so a change confined to userinfo can leave the
security digest unchanged even though the parent contract requires a URI-userinfo HMAC. In addition,
literal display of `OPTIMUS_GATEWAY_URL` can expose URI userinfo during approval.

Ownership is **Plan 9.99 (Tracked, Not Yet Scheduled): Credential URI Security-Snapshot
Canonicalization**. Plan 9.99 requires separate reviewed security-contract and implementation work
before Plan 9.96 may close. It is not implemented, reinterpreted, or waived by Plan 9.98. No real URI,
username, password, or credential value is included here.
