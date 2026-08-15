# Plan 11.16 P11-FU-19 native WSL ext4 evidence

**Status:** 200/200 standalone selectors green at SHA `6159200`. P11-FU-19 is eligible to close
on this lane. P11-FU-7 is not credited here.

**Date:** 2026-08-15

## Provenance (reject `/mnt/*`, Windows Git, shared env)

| Check | Value |
|---|---|
| PWD | `/root/src/optimus-cost-agent` |
| Git | `/usr/bin/git` |
| Filesystem (`stat -f -c '%T'`) | `ext2/ext3` (ext4 native clone) |
| `UV_PROJECT_ENVIRONMENT` | unset |
| `.venv/bin/python` | executable (clone-local) |
| HEAD | `6159200137b76198307591f7496ed83046af45ab` |
| `origin/agent/cursor/plan-11-16-deadline-seams` | `6159200137b76198307591f7496ed83046af45ab` |
| Distro | Ubuntu 24.04.1 LTS (Noble) |
| Kernel | `6.18.35.2-microsoft-standard-WSL2` |

Hashes match the Windows implementation SHA. Path is not under `/mnt/`.

## Deterministic green

```bash
uv run --frozen pytest tests/unit/mcp/test_client_sdk.py::test_operation_deadline_is_enforced -q
```

**1 passed** in 0.26s (first process).

## 200 standalone selectors

```bash
for run in $(seq 1 200); do
  uv run --frozen pytest tests/unit/mcp/test_client_sdk.py::test_operation_deadline_is_enforced -q || exit $?
done
```

**200/200 exit 0.** Recorded as `200_LOOP_DONE fail=0` and `wc -l` = 200 on
`/tmp/plan-11-16-p11-fu-19-wsl-200.txt` (all `exit=0`) in the WSL evidence session.
No `SUBMIT_TIMEOUT` from the SDK selector.

## Focused SDK + supervisor, full unit, Ruff

```bash
uv run --frozen pytest tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_supervisor.py -q
uv run --frozen pytest tests/unit -q
uv run --frozen ruff check .
```

| Gate | Result |
|---|---|
| SDK + supervisor | 28 passed in 1.82s |
| `tests/unit` | **3059 passed, 13 skipped**, 48.69s |
| Ruff | All checks passed |

Skips are marker skips (unrun, not passes). `requires_mcp_http` live client-MCP HTTP
tier was not run.

No unrelated failures on this WSL unit run.
