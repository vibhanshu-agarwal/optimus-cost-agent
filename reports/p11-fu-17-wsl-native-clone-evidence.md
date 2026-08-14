# P11-FU-17 native WSL clone operating-decision evidence

**Decision date:** 2026-08-14
**Documentation branch:** `agent/codex/p11-fu-17-wsl-clone`
**Base invariant:** `HEAD` = `origin/main` =
`2770e0f6d55e60416c82b8ffb2f06c2c3915045e` before this documentation change.

## Decision

Linux/CI-parity gates run from a normal native WSL clone on ext4, not from a Windows-created linked
worktree on `/mnt/d`. This preserves native POSIX Git semantics, avoids the `gitdir: D:/...` pointer
incompatibility, and gives the clone its own virtual environment.

Rejected alternatives:

- A PATH override to Windows `git.exe` changes the Git implementation under test, so a passing run
  is not POSIX/CI-parity evidence; it also crosses the WSL/Windows boundary on every Git call.
- A WSL-created linked worktree fixes the particular pointer but remains on `drvfs` and creates
  mixed-path administrative files in a shared `.git`, which Windows Git cannot reliably resolve.

## Native-clone proof

| Field | Observed value |
|---|---|
| Native clone | `/root/optimus-cost-agent-p11-fu-17-proof` |
| Filesystem | `/dev/sdf`, `ext4` |
| Git executable / version | `/usr/bin/git`, `git version 2.43.0` |
| Origin | `https://github.com/vibhanshu-agarwal/optimus-cost-agent.git` |
| Revision | `HEAD` = `origin/main` = `2770e0f6d55e60416c82b8ffb2f06c2c3915045e` |
| `UV_PROJECT_ENVIRONMENT` | Unset |
| Native virtual environment | `/root/optimus-cost-agent-p11-fu-17-proof/.venv` created by `uv sync --frozen --extra dev` |
| Full unit command | `.venv/bin/python -m pytest tests/unit -q` |
| Full unit result | **2973 passed, 11 skipped, 1 warning** in 66.96 pytest seconds / **72 wall-clock seconds** |
| Former FU-17 selectors | `test_immutable_documents_match_approved_head_blobs` and `test_product_checkpoint_log_location_remains_gitignored`: **2 passed in 0.04s** |

The two selectors used their normal assertions unchanged. The native clone's normal `.git` directory
let both subprocess Git checks execute through `/usr/bin/git`.

## Mounted-worktree comparison

The comparison ran from
`/mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex-p11-fu-17-wsl-clone` with
`UV_PROJECT_ENVIRONMENT=/tmp/p11-fu17-mnt-venv`:

```bash
uv sync --frozen --extra dev
/tmp/p11-fu17-mnt-venv/bin/python -m pytest tests/unit -q
```

It produced **2971 passed, 11 skipped, 2 failed, 1 warning** in 86.28 pytest seconds / **96
wall-clock seconds**. The only failures were the two former FU-17 selectors. Native `/usr/bin/git`
returned `128` after treating the Windows `D:/...` worktree pointer as relative. This confirms the
native clone resolves the original issue without test modification and was 24 wall-clock seconds
faster in this comparison.

## Virtual-environment isolation proof

Before native `uv sync`, the dedicated Windows worktree's `.venv/pyvenv.cfg` was length 184, UTC
mtime `2026-08-14T17:03:06.2666025Z`, and SHA-256
`9C503845220632572999AAD4D94004D287277EC4971A5230D8A12FCD3EE91AFB`. After native `uv sync` with
`UV_PROJECT_ENVIRONMENT` unset, all three values were identical.

Therefore the accepted native-clone gate does not share or alter the Windows worktree virtual
environment. Mounted-worktree diagnostics remain an unsupported exception and must use
`UV_PROJECT_ENVIRONMENT=/tmp/<task>-venv`.
