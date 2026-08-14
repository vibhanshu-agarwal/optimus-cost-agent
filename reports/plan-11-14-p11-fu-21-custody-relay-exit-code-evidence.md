# Plan 11.14 / P11-FU-21 custody-relay exit-code evidence

Implementation SHA: `76bbf1eadad58539696d5b33a9b5a8b52330642b`
Branch: `agent/cursor/plan-11-14-custody-relay-exit-code`
Date (UTC): 2026-08-14

## Native environment provenance

Linux/CI-parity gates ran from the verified `P11-FU-17` native ext4 clone, not a `/mnt/d`
Windows-created worktree.

| Field | Observed value |
|---|---|
| Native clone | `/root/optimus-cost-agent-p11-fu-17-proof` |
| Filesystem | `/` on `/dev/sdf`, `ext4` |
| Git executable / version | `/usr/bin/git`, `git version 2.43.0` |
| `HEAD` | `76bbf1eadad58539696d5b33a9b5a8b52330642b` |
| `origin/agent/cursor/plan-11-14-custody-relay-exit-code` | `76bbf1eadad58539696d5b33a9b5a8b52330642b` |
| `UV_PROJECT_ENVIRONMENT` | Unset |
| Interpreter | CPython 3.14.6 via clone-local `.venv/bin/python` |
| Kernel | `Linux DESKTOP-PL17VTM 6.18.35.2-microsoft-standard-WSL2` |

The FU-17 clone is `--single-branch` on `main`. The implementation ref was fetched with an explicit
refspec so `origin/agent/cursor/plan-11-14-custody-relay-exit-code` existed before detach. `uv` was
invoked as `/root/.local/bin/uv`.

## Deterministic red / green

Command (red, before `tools/plan117_custody_relay.py` edit):

```powershell
uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py::test_post_exit_broken_pipe_preserves_child_exit_and_summary -q
```

Result: failed at `assert exit_code == 7` observing `1` (`1 failed in 0.54s`). Injection hit the
live `proc.stdin.write` path; `_forward_parent_to_child`, `run_relay`, the error list, and
`_write_summary` were not monkeypatched. `verify_relay_capture` was not called.

Command (green, after the pre-cleanup `proc.poll()` discriminator):

```bash
.venv/bin/python -m pytest \
  tests/unit/tools/test_plan117_custody_relay.py::test_post_exit_broken_pipe_preserves_child_exit_and_summary \
  tests/unit/tools/test_plan117_custody_relay.py::test_eof_either_direction_and_child_first_exit \
  -q
```

Native WSL result: **2 passed in 0.48s**. The injected test proves together: process exit `7`,
`summary["child_exit_code"] == 7`, `summary["terminal_disposition"] == "child_exited"`,
`summary["reason_code"] is None`, empty stderr.

Unknown-exit discriminator
(`test_unknown_exit_broken_pipe_preserves_fail_closed_summary`): exit `1`,
`terminal_disposition == "broken_pipe"`, `reason_code == relay_broken_pipe`, stderr contains
`relay_broken_pipe`.

Fail-closed filter:

```bash
.venv/bin/python -m pytest tests/unit/tools/test_plan117_custody_relay.py -q \
  -k "post_exit_broken_pipe or broken_pipe_is_nonzero or recorder_failure_terminates_owned_child_no_fallback or ctrl_c_termination_emits_summary"
```

Native WSL result: **4 passed, 44 deselected in 0.25s**. Interruption and recorder-failure paths
were not modified.

`test_eof_either_direction_and_child_first_exit` is unchanged versus `origin/main`; the injected
test was inserted after it.

`test_broken_pipe_error_path`'s process double previously returned `poll() == 0`, which the new
discriminator correctly treats as a known child exit. The double now returns `poll() is None` so
that test remains an unknown-pipe fail-closed check. `test_broken_pipe_is_nonzero_no_fallback` was
not weakened.

## Focused contract suite

```bash
.venv/bin/python -m pytest \
  tests/unit/tools/test_plan117_custody_relay.py \
  tests/unit/tools/test_plan117_custody_contract.py \
  tests/unit/tools/test_run_plan117_custody_feasibility.py \
  -q
```

Native WSL result: **199 passed in 7.55s**.

No `relay-summary.json` schema migration: `SCHEMA_SUMMARY` remains
`plan117-custody-relay-summary-v1`. `verify_relay_capture()` still requires both directional EOF
markers (`relay_missing_directional_eof` at `tools/plan117_custody_relay.py:1454-1457`).
`mutate_settings_insert_relay()` inserts Zed `command`/`args` only and does not consume a relay
exit-code convention. `tools/plan117_custody_contract.py` has no summary-schema model of the relay
file.

## 200/200 unchanged race test

Exact loop from Plan 11.14 Task 4 Step 2 against
`tests/unit/tools/test_plan117_custody_relay.py::test_eof_either_direction_and_child_first_exit`.

```
iterations=200 passes=200 failures=0 wall_seconds=128
```

Logs: `/tmp/p11-fu21-plan-11-14-loop`. Zero failures; no retries or skips.

## Full suite and aggregate coverage

Commands from the native clone with `UV_PROJECT_ENVIRONMENT` unset:

```bash
uv run --frozen pytest -q
uv run --frozen pytest --cov -q
```

| Gate | Result |
|---|---|
| Full suite | **3069 passed, 12 skipped, 110 deselected, 1 warning** in 62.15s |
| Bare `--cov` | **3069 passed, 12 skipped, 110 deselected, 1 warning** in 84.95s |
| Aggregate | **80.37%** (`fail_under = 80` reached; TOTAL 18530 / 3080 / 5136 / 879) |

The warning is the pre-existing `optimus.acp.__main__` `RuntimeWarning` from
`tests/unit/acp/test_entrypoint.py::test_module_entrypoint_exists`.

## Ruff, diff, and sealed artifact

Task 5 commands:

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen ruff check .
git diff --check
git diff --exit-code origin/main...HEAD -- reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/pre-fix-relay/plan117_custody_relay.py
git diff --name-only origin/main...HEAD
```

| Gate | Result |
|---|---|
| Pool hygiene | Native WSL: **45 passed in 0.12s**. Windows worktree reproduced the two known `P11-FU-17` Git-pointer / `WinError 6` failures; those are not this plan's gate. |
| Ruff (`uv run --frozen python -m ruff check .`) | `All checks passed!` (native clone) |
| `git diff --check` | Exit 0 |
| Sealed pre-fix relay `git diff --exit-code` | Exit 0 |
| `git hash-object` sealed file before any edit | `f5c6903cd5c405d9771cf85914092c5f25286e12` |
| `git hash-object` sealed file after source commit and docs | `f5c6903cd5c405d9771cf85914092c5f25286e12` |
| Operator-captured baseline | `f5c6903cd5c405d9771cf85914092c5f25286e12` |

Changed paths versus `origin/main` after documentation closure: live relay, relay unit test, pool, and this report.

## Windows pytest-capture observation (not a Linux-parity gate)

On win32 with default pytest FD capture, the injected test is not deterministic: about one third
of runs take `recorder_failure` because a reader-thread `OSError` lands in `errors[0]` instead of
the injected `BrokenPipeError`. The same test is 20/20 under `--capture=no` and 20/20 plus 200/200
on native WSL ext4, which is the Plan 11.14 / `P11-FU-17` evidence environment. No production
widening to generic `OSError` was added; the discriminator remains the plan's `BrokenPipeError`
branch.

## Contract

Known post-exit pipe closure (`BrokenPipeError` and `proc.poll() is not None`): return the child
code and record `child_exited` / `reason_code is None` / no broken-pipe stderr.

Unknown mid-stream pipe failure (`BrokenPipeError` and `proc.poll() is None`): return `1`, record
`broken_pipe` / `REASON_BROKEN_PIPE`, terminate the owned child, emit stderr. Pre-cleanup
`child_exit is None` is retained in the summary.

`interrupted` and `recorder_failure` paths still force `1`.
