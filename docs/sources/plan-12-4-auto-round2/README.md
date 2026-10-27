# Plan 12.4 round 2: evidence

This bundle holds the content-free evidence for Plan 12.4's round 2 (v9 Design 5, Task 6): a challenger round on a fresh, sealed split, with H, the judge Auto ships, as an arm. It ran on 2026-10-27 under the pre-registered rule with the operator's approved deviations R4 (no Luna arms), N6 (the turn-size source) and N7 (one reused round-1 row), and with D3's JSON fallback off. **H stays** (Checkpoint R2): Codex round 72 accepted the result, and the operator accepted it (CR2, source S15). Plan 12.4 v10, the closing record, is in `docs/superpowers/plans/archive/`.

**No prompt text is filed here.** The sealed requests and labels stay in the local review kit beside the worktrees (`optimus-handoff\sandbox-review-kit\plan12-4-auto\task6\sealed\`). This bundle was built from them by a separate context that reported only counts, hashes and aggregates.

## Files

| File | What it is |
|---|---|
| [evidence-report.md](evidence-report.md) | The evidence report: the arms, the run, the results, what they do not establish, spend and custody |
| [evidence-tables.md](evidence-tables.md) | Every view's full metrics table, with the B/H interval and calibration (ECE) |
| [extra-facts.txt](extra-facts.txt) | Confusion matrices, under-routes by kind, the 2× and 5× sensitivity, the B/H interval, H's rule share and route-up rate |
| [frozen2.json](frozen2.json) | The settings frozen on the tuning items before any test call (`freeze-2`), without its identities block (below) |
| [manifest.ndjson](manifest.ndjson) | The per-item manifest, 150 entries keyed by round-2 item ID: source facts, both raters' labels, the merged label, the context flag, and each arm's three final tiers and first-repeat row |
| [tools/recompute.py](tools/recompute.py) | Recomputes every view's outcome and metrics from `manifest.ndjson` alone, with `tools/metrics.py`, and adds the B/H interval and ECE |
| [tools/metrics.py](tools/metrics.py) | Round 1's metrics and rule helpers, byte-identical to the pilot bundle's copy |

## The manifest

- **Content-free, as the pilot's (N5, option (ii)):** item IDs, tiers, confidences, costs, latencies and fixed source facts only. It carries no prompt, excerpt, path, digest or rater ID. A check run in the review kit confirmed that no 24-character window of any prompt, no item digest, no group value (other than hand-written items' own IDs) and no rater ID occurs in its bytes.
- **The recompute check:** `tools/recompute.py` reproduces every view, winner, reason and summary metric of the review kit's `evidence2.json` exactly (6 views, 641 values, 0 mismatches). ECE is new: `evidence2.json` holds it as null because its report passed no confidences.
- **Kept in the review kit** (`task6\runs\test-2\`): `evidence2.json`, SHA-256 `d4d4530d65aef6e48d292997b580e6e95547e599608dccb6260d76975d1086e8`; the raw `predictions.jsonl` and `outcome.json`; and the build scripts (`task6\repo-bundle-scripts\`).

## The frozen settings and their identities

The review kit's `freeze-2\frozen2.json` (SHA-256 `80ad1d99894bf03a681d656e933f0cc6c2b79a681cb8203467364d75d3725837`, 3,718 bytes) binds the frozen inputs in an identities block of quoted SHA-256 digests, which trip the repository's secret scan. The filed copy omits only that block (SHA-256 `1a5cd4b2707e50325c3431c7d80fef6b186232d6fc632251920b5e1cdb8ec019`, 984 bytes); the identities are:

| Identity | SHA-256 |
|---|---|
| `frozen_1` | `0a16c2ef0ddd44484799bf5e38d2ce6791395ec0167b3b7747b7e3ef8c81b80a` |
| `d_program` | `d9ec7a21ea1719b410d24de1909a359105c50dd99694a3c77a15988d52e9356b` |
| `turn_sizes` | `9db52161aedccee10dfdaa4594dc6a805af4294c7717db372bcb1e25fb86e32a` |
| `auto_facts` | `da2564aa3221ad9302a14f3a9038952e880a6414e9a4749dc049b7175226cd00` |
| `arms` | `db1b3476777852d41ddad5274a09eaf1725cdf759bfef3f59796771e978fb007` |
| harness `task3/arm_dspy.py` | `60b76b9bf5a156f808f8fe2909abf461e521b7483db82ca6092fd4baa553fa93` |
| harness `task3/arms.py` | `5a8c7765df9700e2305a671d9da299f967baaa7e5b693a9d55aa4207a1bcc038` |
| harness `task3/combo_explore.py` | `e992961500d6f51d5532fe84e65a295dc4602e2065dfb0c9a62f030c28a18f7e` |
| harness `task3/dump_auto_facts.py` | `9eb3ffee9dbbe4ddee4b4af81a6d1a465a3525d4b5bbd925664704ab2701860c` |
| harness `task3/dump_snapshot.py` | `72766b13e15a47201e181386b452d25c32c23da950cb446f3e06b179db215a28` |
| harness `task3/extra_facts.py` | `5a93d1dc6c811be805341c8325824963e79a0a23f3b11cde2fdc4b0e6aedbe7b` |
| harness `task3/metrics.py` | `bbf0b4d214f64e159075c264b5fee97a6016c933e39fb5b09cd8c44e74edd129` |
| harness `task3/pilot.py` | `7907ab41cf35a280a8084e50e7be144f96d9e00e9f8bb16986c7c841f57cb633` |
| harness `task3/pilot_gateway.py` | `4b3e82d1431b70fbd4f788c90ef33ffda807df8163555025bb6682ebf0bf053c` |
| harness `task3/probe_jev.py` | `031bd5c8ffc8fd1e444860ab974397d2f5ec6267a9e0e3d5dd2c328dcde66c7f` |
| harness `task3/render_report.py` | `bb3164a7f3483b426e762fbea7442e055260c06da2d402015ed40e381507c2cb` |
| harness `task3/repo_manifest.py` | `5152c996aa9b97f29635866cbcf6da4b7925233751a0ad6b2c8ed693e324c151` |
| harness `task3/resolve_bearer.py` | `4ccc5a29de3a7a2cf61ffa51ed3db8178b4e6188bbb4c113804afc876ce79f66` |
| harness `task3/run_pilot.py` | `b1b73d2799cac6ac02676e2fe98248a9133166636602a88645cf72a9e43d8af2` |
| harness `task3/selfcheck_gateway.py` | `2f5eac0478915f36006ebd188d8176e13f6533ae1bf6849f8c0a27205ee84773` |
| harness `task3/selfcheck_pilot.py` | `6a241154be44ffbe1001863528af7a890158f365aaac8f2813d39c9caca71ac8` |
| harness `task3/selfcheck_runner.py` | `8042a1e6c10d67f64fbf257daed8dc886b203ac0ef22e0ca4fb1c8711458827b` |
| harness `task3/validate_auto.py` | `241c204ffd3d44e791e207a3a5a0e02517e412f43f3ea8681f6d29546a7a3475` |
| harness `task6/round2.py` | `7f385ea6448d690768ecbdba79ff7b1856f35b19b1dce9d039f0b8f485b83c7e` |
| harness `task6/selfcheck_round2.py` | `a6c507979f076dc79b139090d196a3874b3a70f19edee7de20b81a2580bfc2cf` |
| sealed `set/items.jsonl` | `64ba85dcbacbb44f3869d20f60237707faa8af360bf84e60880b8a8684af82e0` |
| sealed `set/labels.jsonl` | `097adfd085bc2b023d9d9a197d372235182d94189886a747875de76698726ce9` |

## Recompute

```bash
python -I docs/sources/plan-12-4-auto-round2/tools/recompute.py
```

Standard library only, with `metrics.py` beside it. It prints each view's rule outcome, each arm's main metrics, the B/H interval and ECE, matching `evidence-tables.md`.

## Review

Codex CLI round 72 (gpt-6.1-sol, high), posted verbatim on #395 (comment 6446442920), accepted the result and asked the evidence bundle to publish two things `evidence2.json` lacked: the B/H tie interval and a calibration metric. Both are in `evidence-tables.md` and printed by `tools/recompute.py`.
