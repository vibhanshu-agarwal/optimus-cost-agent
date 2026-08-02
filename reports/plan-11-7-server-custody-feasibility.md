# Plan 11.7 server-side custody feasibility

Immutable history and correction accounting for the Plan 11.7 Zed server-side custody
feasibility probe. This document records evidence history only. It does **not** claim a
feasible production disposition. Corrected origin-A under the fixture-v2 amendment ended as a
**process-invalid sealed stop** (Option B); feasibility remains undecided and returns to the
operator. A clean DoD-qualifying relaunch requires a separate budget-expansion amendment.

## Parent probe context

- Frozen Plan 11.7 Tasks 0 Steps 5-7 and Tasks 1-11 remain blocked.
- Parent feasibility amendment digest:
  `79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6`.
- Origin-A fixture v2 amendment digest:
  `5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D`.
- Execution tip at live launch: `400825c3291103b3d13d8da044ca86d3692d77db`.
- Restore-fallback fix tip (post-launch tooling): `e0ca15b8530425d4958ceeefab2dd175deed82c0`.
- Seal package commit: `0f3136abc53a6e2237e3aceb450a4e1afdf97441`.

## V1 attempt history (immutable originals)

Private custody root:
`D:\Projects\Development\Python\optimus-evidence-custody\plan117-task4-private`.

### origin-a-1 (correlation capture 1)

Original attempt-manifest classified the run as a permanent Zed crash. Raw evidence
contradicts that label:

| artifact | SHA-256 | bytes |
|---|---|---|
| attempts/origin-a-1/attempt-manifest.json | `7D64D5943002B15DCD977B0BC7614FC4234F9DD6D823C1533DA6A0677F9FF446` | 446 |
| attempts/origin-a-1/phase-observation.json | `CE358BD9E715C733766FA7080DD0CFDC26AEAE3368F0AD8AEDDE1DD74432C725` | 219 |
| origin-a-1/zed-to-agent.bin | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 |
| origin-a-1/agent-to-zed.bin | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 |
| origin-a-1/relay-index.ndjson | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 |

Empty duplex streams / relay deadlock tooling failure. No prompt stage started.

### origin-a-2 (correlation capture 2 + post-new prompt 1)

| artifact | SHA-256 | bytes |
|---|---|---|
| attempts/origin-a-2/attempt-manifest.json | `083E0953C8D89781C8C3100545BFC2E4524E94CBBAAE7B32574DA4D88F597F63` | 291 |
| attempts/origin-a-2/phase-observation.json | `CCE1FAC316F5961B6E1B3A57463D3DEB5119111FF9856B7A405761B459E47FF1` | 143 |
| origin-a-2/zed-to-agent.bin | `CD7B2463ACD6DBFF71F9887BDEC5CBC31B3C7B28504B294859DAFDA14B9A53E0` | 932 |
| origin-a-2/agent-to-zed.bin | `DC1AE7DB33D1AF23D94FF3DA315E4F4DD2400BB12E9E671F279565298F928ECF` | 1950 |
| origin-a-2/relay-index.ndjson | `6D2E712D4F56C5225A2DBF5E9CE2787529D4F359AAA045B9802FF7CFCEA5F610` | 1755 |
| origin-a-2/relay-summary.json | absent | - |

Correlation succeeded; prompt failed permanently (`AMBIGUOUS_WORKSPACE_REFERENCE`); later Zed
crash `0xc0000409` is supplemental only.

## V2 correction accounting (append-only)

### Task 3 historical supersessions

| record | stage / fact | ordinal | status | reason |
|---|---|---|---|---|
| origin-a-1-correlation | correlation_capture | 1 | failed (permanent) | `invalid_probe_relay_capture_tooling_failure` |
| origin-a-2-correlation | correlation_capture | 2 | succeeded | none |
| origin-a-2-prompt | post_new_prompt | 1 | failed (permanent) | `AMBIGUOUS_WORKSPACE_REFERENCE` |
| origin-a-2-client | supplemental `zed_client_crash` | n/a | fact only | `stop_probe_zed_client_crashed` |

### origin-a-3 live attempt (Option B seal)

One authorized Zed launch under tip `400825c`. Settings restored to pre-image
`DA99A0CDC4381092E4927A21CEC5217D0249D214969515F1022228DBA1D3A1F5`.

| record | stage / fact | ordinal | status | reason |
|---|---|---|---|---|
| origin-a-3-correlation | correlation_capture | 3 | succeeded | none |
| origin-a-3-prompt-2 | post_new_prompt | 2 | failed (transient) | `transient_capture` (`PLANNING_UNPARSEABLE_RESPONSE`) |
| origin-a-3-ungated-reprompt | supplemental `out_of_band_same_session_reprompt` | n/a | fact only | `invalid_probe_stage_accounting` |

Wire facts (both real Gateway-backed; see `origin-a-3-exchange-facts.json`):

1. `ada61949…` — cost `$0.008273`, planning-unparseable, no file reads.
2. `dcacf89a…` — cost `$0.007565`, correct `optimus-cost-agent` answer after approve — **unauthorized**
   same-session re-prompt; does **not** consume prompt ordinal 3.

Derived ledger ordinals after seal: `next_correlation_ordinal=4`, `next_prompt_ordinal=3`.
Correlation budget under this amendment is exhausted. Prompt ordinal 3 remains unclaimed by design
(Option B: no third gated prompt after context contamination).

Seal artifact: `…/origin-a-fixture-v2/origin-a-3-seal-b.json`
(`corrected_origin_a_dod_success=false`, `feasibility_disposition_claimed=false`).

## Collector / redaction

- Scenario: `tests/fixtures/evidence/scenarios/plan117-server-custody.toml`
- Promotable root: `D:\Projects\Development\Python\optimus-evidence-custody\plan117-task4-promotable`
- Run id: `1883d81419cc4a00af152e7ffc41395d`
- Collector outcome: `indeterminate` (probe-specific ending remains process-invalid Option B)
- Evidence report: `reports/plan-11-7-server-custody-artifacts/evidence-report.json`
- Raw private ACP bytes and settings pre-image remain private; promoted set is digest/classification JSON only.

## Explicit non-claims

This package does **not** claim:

- production server-side custody feasibility;
- ACP conformance;
- `session/load` / resume affordance success;
- corrected origin-A DoD success;
- authorization to start frozen Plan 11.7 implementation Tasks 0.5–11;
- that the ungated second prompt satisfies `assert_prompt_retry_preflight`.

## Operator return

Feasibility remains **undecided**. Corrected origin-A under fixture-v2 is a sealed invalid ending.
A clean DoD-qualifying observation requires a **budget-expansion amendment** (and Zed re-hash /
re-pin at the next launch if the installed binary has changed). Parent amendment Task 5
(`restart-b` / later phases) is **not** unblocked by this result.
