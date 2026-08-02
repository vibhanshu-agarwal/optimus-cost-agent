# Plan 11.7 server-side custody feasibility

Immutable history and correction accounting for the Plan 11.7 Zed server-side custody
feasibility probe. This document records evidence history only. It does **not** claim a
feasible or infeasible production disposition from corrected origin-A records alone.

## Parent probe context

- Frozen Plan 11.7 Tasks 0 Steps 5-7 and Tasks 1-11 remain blocked pending a reviewed
  corrected origin-A observation.
- Parent feasibility amendment digest:
  `79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6`.
- Origin-A fixture v2 amendment digest:
  `5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D`.

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

Empty duplex streams, forced termination after full-duplex relay deadlock, and
event-facts origin-a-1 window zeros (no Zed fault / no `0xc0000409`) are preserved as
immutable parents. No prompt stage started.

### origin-a-2 (correlation capture 2 + post-new prompt 1)

| artifact | SHA-256 | bytes |
|---|---|---|
| attempts/origin-a-2/attempt-manifest.json | `083E0953C8D89781C8C3100545BFC2E4524E94CBBAAE7B32574DA4D88F597F63` | 291 |
| attempts/origin-a-2/phase-observation.json | `CCE1FAC316F5961B6E1B3A57463D3DEB5119111FF9856B7A405761B459E47FF1` | 143 |
| origin-a-2/zed-to-agent.bin | `CD7B2463ACD6DBFF71F9887BDEC5CBC31B3C7B28504B294859DAFDA14B9A53E0` | 932 |
| origin-a-2/agent-to-zed.bin | `DC1AE7DB33D1AF23D94FF3DA315E4F4DD2400BB12E9E671F279565298F928ECF` | 1950 |
| origin-a-2/relay-index.ndjson | `6D2E712D4F56C5225A2DBF5E9CE2787529D4F359AAA045B9802FF7CFCEA5F610` | 1755 |
| origin-a-2/relay-summary.json | absent | - |

Raw capture shows three separate facts: successful `initialize`/`session/new` correlation,
pre-Gateway `AMBIGUOUS_WORKSPACE_REFERENCE` prompt refusal, and a later Zed crash
`0xc0000409` with absent relay-summary.

## V2 correction accounting (append-only; Task 3)

Promoted supersessions under
`reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/supersessions/`:

| record | stage / fact | ordinal | status | reason |
|---|---|---|---|---|
| origin-a-1-correlation | correlation_capture | 1 | failed (permanent) | `invalid_probe_relay_capture_tooling_failure` |
| origin-a-2-correlation | correlation_capture | 2 | succeeded | none |
| origin-a-2-prompt | post_new_prompt | 1 | failed (permanent) | `AMBIGUOUS_WORKSPACE_REFERENCE` |
| origin-a-2-client | supplemental `zed_client_crash` | n/a | fact only | `stop_probe_zed_client_crashed` |

Stage ledger
(`.../amendments/origin-a-fixture-v2/stage-ledger.json`) includes only the three terminal
stage records. Derived next ordinals:

- `next_correlation_ordinal` = **3**
- `next_prompt_ordinal` = **2**

The supplemental crash fact does not change correlation success or prompt failure and is
not a stage row.

## Disposition boundary

Task 3 seals corrected historical accounting only. No feasible / infeasible production
disposition is inferred from these records. `origin-a-3` remains the sole authorized next
correlation capture under the amendment budget.
