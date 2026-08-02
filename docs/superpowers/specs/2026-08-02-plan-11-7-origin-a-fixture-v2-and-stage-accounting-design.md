# Plan 11.7 Origin-A Fixture V2 and Stage-Aware Attempt Accounting Design

**Status:** Draft for independent reviewer and operator approval.

**Purpose:** Correct the deterministic origin-A prompt-fixture defect and the attempt-accounting
ambiguity discovered during execution of the approved Plan 11.7 server-side custody feasibility
amendment. This design preserves every original attempt and authorizes a separately approved,
bounded continuation using exactly one additional Zed launch, `origin-a-3`.

**Decision boundary:** This is a narrow execution correction, not a new feasibility theory. It
does not change Optimus production code, the workspace-reference resolver, the correlation
eligibility rules, the three-attempt correlation cap, or the requirement for a real Gateway
round-trip with provider-reported usage and cost. It does not erase either prior attempt. The
associated standalone amendment must receive its own identity + UTC + exact LF-byte SHA-256
approval before execution, and live settings mutation remains a separate approval gate.

## Authority and immutable parent chain

The following inputs are immutable:

- frozen Plan 11.7:
  `docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md`,
  authoritative Git-blob SHA-256
  `F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D`;
- approved server-side custody design:
  `docs/superpowers/specs/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-design.md`,
  LF-byte SHA-256
  `8808E5212DCDB3B44198096D1A0AFE7E20A53E4A9B28438DA5AA23245D339F0E`;
- approved parent amendment:
  `docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md`,
  LF-byte SHA-256
  `79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6`;
- triggering Step 4 discovery disposition:
  `stop_amend_plan_session_load_unreachable`;
- triggering sealed Step 4 evidence-report SHA-256:
  `1579A5B1A84F1AE46C0B09B317F61B93D919E5E03725FFA8BD0F9F6BD32565BF`;
- Zed production target: version 1.13.1 at source commit
  `00bd72e7838f4b875a913cd112b47a0ebe1ca62b`; and
- roadmap owner and reviewer log: `P11-FEAT-ZED-RESUME` and
  `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`.

The approved parent amendment is frozen now that execution has begun. The correction therefore
uses a second standalone amendment rather than editing the parent or frozen Plan 11.7. It allocates
no new Plan 11.x number and changes only the origin-A fixture, evidence classification, attempt
accounting, and pre-run safety gates described here.

Execution remains custody-bound to
`D:\Projects\Development\Python\optimus-cost-agent-wt-cursor` on branch
`agent/cursor/p11-feat-zed-resume`. The private raw evidence remains under the approved Plan 11.7
custody root. Neither the gitignored reviewer log nor private/untracked evidence may be replaced,
copied into a fresh worktree as a substitute, or regenerated from summaries.

## Evidence-bound findings

### The original prompt is not a valid Gateway fixture

The parent fixture used the bare basename `README.md`. In the custody-bound workspace, basename
resolution matches five files and fails deterministically with `AMBIGUOUS_WORKSPACE_REFERENCE`.
Changing the token to `./README.md` selects the root file unambiguously, but that file is 44,191
bytes and exceeds the resolver's 16 KiB file budget, producing
`REQUIRED_WORKSPACE_FILE_TOO_LARGE`. Retrying either form cannot exercise the Gateway.

The existing relative-path resolver already resolves `./pyproject.toml` exactly to the root file.
The target is 2,925 bytes, is within the budget, and contains the project name. The approved
replacement fixture is therefore the exact UTF-8, no-BOM text below with exactly one terminal LF:

```text
Read ./pyproject.toml and answer with one sentence naming this project. Do not modify files.
```

Its raw-byte SHA-256 is
`9195EFEEE3A2180CFB85EDE409FF7785F159F64E36426DCDB369251560E28A50`.
The target `pyproject.toml` raw-byte and Git-blob SHA-256 in the custody-bound workspace is
`AE28C0C3776F6B78DF23E86FC0E88B0088FEBB7241A04650C604D713E23EF697`.

The `./` prefix is load-bearing: a bare `pyproject.toml` is also basename-ambiguous in this
workspace. The fixture correction changes no resolver behavior and authorizes no file under
`src/optimus` or `src/optimus_gateway` to change.

### Origin-a-1 was a relay tooling failure

The original `origin-a-1` manifest classifies the attempt as a permanent Zed crash. That statement
is contradicted by the captured evidence:

- the relay index and both byte streams are empty;
- the relay blocked on a full-duplex Windows pipe read and the operator force-terminated the
  process chain; and
- Windows event evidence contains no Zed crash at the attempt time.

The original manifest remains immutable. A new append-only superseding record must classify the
attempt as `invalid_probe_relay_capture_tooling_failure`, record the relay deadlock and forced
termination, cite the raw artifacts by hash, and expressly state that it is not evidence of a Zed
crash or product infeasibility.

The relevant immutable raw hashes are:

| Origin-a-1 artifact | Raw-byte SHA-256 | Bytes |
|---|---:|---:|
| `attempt-manifest.json` | `7D64D5943002B15DCD977B0BC7614FC4234F9DD6D823C1533DA6A0677F9FF446` | 446 |
| `phase-observation.json` | `CE358BD9E715C733766FA7080DD0CFDC26AEAE3368F0AD8AEDDE1DD74432C725` | 219 |
| `zed-to-agent.bin` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 |
| `agent-to-zed.bin` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 |
| `relay-index.ndjson` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 |

### Origin-a-2 spent both an acquisition stage and a prompt stage

The `origin-a-2` manifest still says `observation_pending`, but the raw capture proves three
separate facts:

1. `initialize` and `session/new` completed; the boundary was indexed and the two independent
   records were byte-consistent;
2. the original bare-README prompt was refused before the Gateway with
   `AMBIGUOUS_WORKSPACE_REFERENCE`; and
3. Zed later crashed with `0xc0000409`, and `relay-summary.json` was not produced.

The original files remain immutable. One or more append-only superseding records must finalize all
three facts without collapsing them into one label. The attempt consumes correlation-capture
ordinal 2 because that stage succeeded. It also consumes post-new-prompt ordinal 1 because the
prompt stage ran and failed. The crash remains a real crash; it is neither relabeled transient nor
deleted from the history.

The relevant immutable raw hashes are:

| Origin-a-2 artifact | Raw-byte SHA-256 | Bytes |
|---|---:|---:|
| `attempt-manifest.json` | `083E0953C8D89781C8C3100545BFC2E4524E94CBBAAE7B32574DA4D88F597F63` | 291 |
| `phase-observation.json` | `CCE1FAC316F5961B6E1B3A57463D3DEB5119111FF9856B7A405761B459E47FF1` | 143 |
| `zed-to-agent.bin` | `CD7B2463ACD6DBFF71F9887BDEC5CBC31B3C7B28504B294859DAFDA14B9A53E0` | 932 |
| `agent-to-zed.bin` | `DC1AE7DB33D1AF23D94FF3DA315E4F4DD2400BB12E9E671F279565298F928ECF` | 1950 |
| `relay-index.ndjson` | `6D2E712D4F56C5225A2DBF5E9CE2787529D4F359AAA045B9802FF7CFCEA5F610` | 1755 |
| `relay-summary.json` | absent | - |

## Decisions

### Use append-only supersession

No existing attempt manifest, observation, transcript, relay index, or byte stream may be edited,
renamed, replaced, or deleted. A correction is a new immutable record that includes:

- its own schema and record identity;
- the superseded record locator and raw-byte SHA-256;
- the physical run attempt ID;
- the stage, ordinal, status, failure class, and reason code;
- evidence locators and raw hashes supporting the correction;
- the approving amendment digest; and
- creation identity and UTC.

The verifier must reject a superseding record whose cited original hash does not match, whose
reason lacks the required evidence, or whose chain contains a cycle, fork, duplicate terminal
classification for one stage, or silent replacement. Historical content remains visible in the
sealed chain even when a later record controls the normalized classification.

### Account by stage, not only by launch directory

A physical Zed run can consume two independently bounded stages. The contract therefore needs a
stage record with, at minimum:

| Field | Meaning |
|---|---|
| `run_attempt_id` | Stable physical-run identity such as `origin-a-2` |
| `stage` | `correlation_capture` or `post_new_prompt` |
| `ordinal` | Monotonic ordinal within that stage's independent budget |
| `status` | `not_started`, `succeeded`, `failed`, or `superseded` |
| `failure_class` | `none`, `transient`, or `permanent` |
| `reason_code` | Stable safe code consistent with the evidence |
| `evidence` | Immutable locators, hashes, and independent-corroboration references |
| `supersedes` | Optional prior stage-record identity and hash |

The normalized ledger derives the next ordinal from terminal stage records, not merely from
directory names allocated before an outcome is known. One physical run may have a successful
correlation record followed by a failed prompt record. A prompt retry in an already-live session
spends only the prompt budget; it must not allocate another correlation attempt.

The fixed accounting before any new launch is:

| Physical run | Correlation stage | Prompt stage |
|---|---|---|
| `origin-a-1` | ordinal 1, failed tooling capture | not started |
| `origin-a-2` | ordinal 2, succeeded | ordinal 1, failed pre-Gateway fixture |
| `origin-a-3` | ordinal 3, final authorized capture | ordinal 2 if correlation succeeds |

No lineage or budget resets. `origin-a-3` is the third and final correlation-capture slot. If its
correlation stage succeeds and its prompt stage suffers an evidence-backed transient failure while
the same Zed session remains alive and valid, one prompt-only retry may consume prompt ordinal 3.
That retry must reuse the same live session and must not relaunch Zed. A fourth correlation launch
requires a new explicit budget-expansion amendment and operator approval.

### Permit one corrected-stimulus exception after the origin-a-2 crash

The parent amendment normally makes `stop_probe_zed_client_crashed` terminal. This correction
creates one narrow exception: after preserving the real origin-a-2 crash and proving that the
prompt stimulus independently failed before the Gateway for a deterministic fixture defect, the
operator may approve one corrected-stimulus launch, `origin-a-3`.

The exception does not classify the crash as transient, weaken crash precedence for the new run,
or authorize further retries. Any Zed crash during `origin-a-3` stops the probe. Settings restore
failure, target/approval mismatch, relay/debug divergence, non-Zed traffic, or permanent prompt
failure also stops without another launch.

### Keep the Gateway requirement hard

Task 4 is not satisfied by a local refusal, zero tool calls, or zero cost. A successful origin-A
prompt stage must include a real Optimus Gateway round-trip and provider-reported usage and cost
fields tied to the Zed-originated session, request, response, run, and debug evidence. Missing or
estimated fields fail the prompt stage. Only an evidence-backed transient Gateway/model failure may
use the remaining prompt-only slot, and only while the same session remains alive.

## Pre-run safety gates

### JSONC settings parser correction

The settings mutation path falls back to a JSONC stripper. Its trailing-comma pass does not track
string state, so a commented settings file can silently change string values such as `"a, ]"` to
`"a ]"` before the entire file is reserialized. Exact pre-image restoration prevents lasting data
loss but does not make in-window corruption acceptable.

This is a tooling safety defect, not evidence supporting or refuting the fixture conclusion. Before
`origin-a-3`, the correction must be implemented test-first, committed, and independently reviewed.
Tests must cover comments, escaped quotes, backslashes, `,}` and `,]` inside strings, actual
trailing commas outside strings, fallback-only invocation, parse failure, and exact settings
pre-image restoration. The live run may not proceed on an uncommitted or unreviewed parser fix.

### Relay read correction

The Windows relay must use the reviewed non-blocking/partial-read-safe path that resolves the
origin-a-1 full-duplex deadlock. That change and its byte equality, ordering, EOF, error, and live
debug-corroboration tests must be committed and independently reviewed before `origin-a-3`. The
evidence manifest pins the exact execution commit and relay-tool Git-blob SHA-256; transient working
tree code is not an acceptable evidence dependency.

### Exact execution identity and external approval

Immediately before the live launch, the worker must prove:

- the custody-bound worktree and expected branch;
- a clean, committed execution tree for all probe tools, tests, fixture, and scenario files;
- exact Git commit and Git-blob hashes for every execution tool and fixture;
- unchanged `src/optimus` and `src/optimus_gateway` relative to the approved baseline;
- full unit-suite, Ruff, logging-surface audit, offline verifier, and targeted platform-shaped tests;
- re-hashed Zed binary, launcher, source commit, workspace, `pyproject.toml`, Gateway/Redis
  preconditions, and durable launch approval;
- no exported `OPTIMUS_PLAN117_*` variables before the production launch gate runs; and
- independent reviewer approval of the tooling and append-only classifications.

After those exact values are known, obtain a fresh operator approval for the one `origin-a-3`
settings mutation. The approval records identity, UTC, settings path and pre-image identity, exact
changed paths, exact execution commit/tool digests, launch command, backup path, and restoration
command. Prior settings approval does not carry forward across the tool and fixture changes.

## Evidence and reducer contract

The live and offline evidence must preserve the parent amendment's controls:

- Zed is the only ACP client; no UI injection, project-authored client, profile rewriting,
  session-ID rewriting, old-session return from `session/new`, or timestamp-only correlation;
- direct and relay-mediated launches consume the same durable production approval record;
- the relay is byte-opaque and environment-transparent, while ancestry-derived observations remain
  non-production-representative;
- the relay record is cross-corroborated against Optimus's independent `debug-acp.ndjson`;
- raw evidence remains private and promoted evidence is produced only through subprocess invocation
  of `tools/evidence_gather.py redact`, with no plan-specific sanitizer and no imports from
  `tools.evidence_gather_support`;
- the exact settings pre-image existence and bytes are restored on every exit; restore failure
  outranks all other results; and
- all model usage and cost values are provider-reported through the real Gateway.

For `origin-a-3`, reducer precedence is:

1. invalid trigger, amendment approval, execution identity, or target identity;
2. settings restoration failure;
3. relay environment/byte/debug, process-custody, non-Zed-traffic, or transcript failure;
4. Zed crash;
5. invalid stage ledger, budget overrun, supersession chain, or fixture/target identity;
6. permanent prompt or dependency failure;
7. evidence-backed transient prompt failure eligible for same-session prompt-only retry; and
8. successful real-Gateway origin-A evidence.

No lower result is reachable while a higher predicate is true. If the same live session cannot be
proven after a transient prompt failure, the retry is unavailable because a new launch would be a
fourth correlation attempt.

## Rejected alternatives

- **Retry the original fixture:** rejected because basename ambiguity is deterministic.
- **Use `./README.md`:** rejected because the exact root file exceeds the resolver budget.
- **Change the resolver to prefer root files:** rejected as an out-of-scope product safety-policy
  change.
- **Accept the pre-Gateway refusal as Task 4 success:** rejected because it does not test Gateway
  custody or produce the required usage/cost evidence.
- **Reset the attempt lineage after changing the fixture:** rejected because origin-a-2 genuinely
  completed correlation capture ordinal 2 and ran prompt ordinal 1.
- **Restore a consumed correlation slot:** rejected as a false evidence claim.
- **Overwrite the old manifests:** rejected because sealed evidence is append-only.
- **Launch origin-a-4 under the existing approval:** rejected because the correlation budget is
  three and any expansion requires a separate amendment.
- **Run with uncommitted relay or parser fixes:** rejected because the live evidence must identify
  reproducible, reviewed execution bytes.

## Acceptance criteria for the standalone amendment

The amendment implementing this design is ready for approval only when it:

1. pins this design by exact LF-byte SHA-256 and pins the approved parent amendment digest;
2. names the v2 prompt and target hashes exactly;
3. requires append-only superseding records for origin-a-1 and origin-a-2 and the raw hashes above;
4. defines stage-aware accounting with no lineage reset and exactly one new Zed launch;
5. keeps the Gateway usage/cost requirement hard;
6. makes the committed/reviewed JSONC and relay fixes hard pre-run gates while keeping their
   conclusions separate from fixture feasibility;
7. requires a clean exact execution commit and fresh settings-mutation approval;
8. preserves every parent custody, redaction, restoration, reviewer, and production-source guard;
9. defines fail-closed stop conditions with no fourth correlation launch; and
10. returns the sealed result to the existing Plan 11.7 reviewer log and operator gate before the
    parent amendment proceeds beyond corrected origin A.

Approval of the design or amendment never authorizes production server-side custody. It authorizes
only the bounded correction and, after the separate settings gate, one `origin-a-3` launch.
