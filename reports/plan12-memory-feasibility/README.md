# Plan 12.7 memory feasibility evidence (M0a-3, #391)

Sanitized, synthetic-only results of the Plan 12.7 probes. Plan SHA-256 `8b8d56447d95b23403b7c750c64e7384b88dc8d899ec65c29d274faa8c774540`; design spec v4 SHA-256
`708e0e7831f6d4c56b5f6442cd37c4e02eecffd2659db04f3e6a6b1c54506ff9`. Digests in the JSON records are written `hex:<digest>`. Two records were rendered from originals
kept in the review kit; each names its original's SHA-256 in `rendered_from_sha256`.

| Probe | Outcome | Summary |
|---|---|---|
| P1 packages/parsers | PASS (attempts 1 and 2 retained) | Ten distributions hash-bound and smoke-tested on Windows CPython 3.14.4 |
| P2 embeddings/worker | PASS | bge-small-en-v1.5 offline; cancel/resume and owner-exit/restart reproduce the output hash |
| P3 Redis K2 | PASS (attempt 1 ERROR, retained) | 18 of 18 predeclared bounds on a dedicated synthetic instance; topology provisional |
| P4 Postgres | PASS | Driver readiness only; no ledger claim |
| P5 ACP/Zed | UNRUN, handed off | The Zed GUI grant was declined; P5-a to P5-d go to M1/M3 with their fallbacks |

- `probe-config.json`: the predeclared config and Redis targets.
- `qualification.json`: per-probe results, retained attempts, caveats and what is not proven.
- `handoffs.json`: owners, reasons, next proofs and fallbacks.
- `execution-context.json`: the command, checkout, branch, exit status and retained-log digest of every run and selection control.
- `manifest.json`: SHA-256 of every file here.
- `attempts/`: one write-once record per attempt.

No paid calls were made. Administrative closure is not an all-probes PASS, and nothing here qualifies a production capability.
