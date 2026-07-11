# Plan 9.7 manual E2E evidence (operator PATH path)

> **Not the contributor path.** Repo `.venv` + `pip install -e ".[dev]"` validates code for
> developers; it does **not** satisfy Plan 9.7 sign-off. Use PATH install below.

## Preconditions

- [x] New terminal — no venv activated (`$env:VIRTUAL_ENV` empty on PowerShell)
- [x] No `OPTIMUS_*` or provider API keys in the shell environment
- [x] `.env` and `.env.gateway` renamed away in the workspace used for the test (N/A — no dotenv on main checkout)
- [x] Docker Desktop running (for auto-start Redis)
- [x] Stale shim removed if present: rename `C:\Users\<you>\.local\bin\optimus-agent.exe` if broken (not required — fresh uv reinstall)

## 1. Install on PATH

**Preferred (when `uv` is available):**

```powershell
cd <repo-checkout>
uv tool install --editable . --reinstall
uv tool update-shell
# Open a new terminal; verify with where.exe optimus-agent
```

**Windows fallback (`pip install --user`):**

```powershell
cd <repo-checkout>
pip install --user -e . --force-reinstall

# REQUIRED: add Scripts dir to user PATH (Windows does not do this automatically)
python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))"
# Example output: C:\Users\<you>\AppData\Roaming\Python\Python314\Scripts

[Environment]::SetEnvironmentVariable(
        'Path',
        [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + (python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))"),
        'User'
)
```

**After any PATH change:** open a new terminal **and fully restart your IDE** (JetBrains/Cursor
cache PATH from launch — a new integrated terminal alone may not be enough).

Verify:

```powershell
where.exe optimus-agent
# Expected: Roaming Python\Python*\Scripts\optimus-agent.exe OR uv tool bin dir
# Expected: NOT .venv\Scripts\optimus-agent.exe
# Expected: NOT a stale C:\Users\<you>\.local\bin\optimus-agent.exe missing keyring
```

Paste `where.exe` output here:

```
$ where.exe optimus-agent
C:\Users\pc\.local\bin\optimus-agent.exe
C:\Users\pc\AppData\Roaming\Python\Python314\Scripts\optimus-agent.exe

```

## 2. Keychain setup

```powershell
optimus-agent --setup
```

Paste relevant stderr (no secrets) here:

```
PS D:\Projects\Development\Python\optimus-cost-agent> optimus-agent --setup
Provider [openrouter]: openrouter
A provider key is already stored. Overwrite? [y/N]: N
Setup cancelled; existing credentials unchanged.
```

## 3. Config check

```powershell
optimus-agent --workspace-root . --check-config
```

Exit code and stderr:

```
PS D:\Projects\Development\Python\optimus-cost-agent> optimus-agent --workspace-root . --check-config
Optimus ACP agent configuration OK.
PS D:\Projects\Development\Python\optimus-cost-agent>
```

## 4. Serve + planning call (`claude-haiku`)

Run `optimus-agent --workspace-root .` (or IDE with `"command": "optimus-agent"` only) and
trigger a real planning turn. Confirm the call uses `claude-haiku` through the auto-started
loopback gateway — not merely that processes launched.

Evidence (gateway log tail — redact secrets):

```
PS D:\Projects\Development\Python\optimus-cost-agent> Get-Content reports/local-gateway.log -Tail 40
optimus local gateway listening on http://127.0.0.1:8765 (provider=openrouter)
optimus local gateway listening on http://127.0.0.1:8765 (provider=openrouter)
```

**Operator notes (not log output):**

- Zed planning turn: plan → approval → Completed Plan (2 READ steps to fixture `example.py` paths).
- **Code provenance:** `optimus-agent` from uv editable PATH install of primary clone `main` @
  `7376e23` (`optimus_acp_file` → `D:\Projects\Development\Python\optimus-cost-agent\src\...` per
  debug trace PROVENANCE).
- **Zed workspace:** project opened in `optimus-cost-agent-wt-cursor` (`cwd` in
  `wt-cursor\.optimus\debug-acp.ndjson` PROVENANCE lines); `--workspace-root .` therefore resolved
  to the wt-cursor tree (fixture paths under `reports/.plan97-e2e-workspace/` exist there, not in
  primary clone — Plan 9.8 context-floor pathology).
- **`claude-haiku`:** no per-request model line in gateway log (startup only); default agent model
  when env unset is `claude-haiku` (`src/optimus/acp/local_infra.py:50`), consistent with
  keychain-only session (zero `OPTIMUS_*`).

## 5. Sign-off

- [x] `optimus-redis` container running (`docker ps --filter name=optimus-redis`)
- [x] Local gateway reachable on loopback
- [x] Planning call succeeded via auto-started stack on `claude-haiku`
- [x] Operator PATH path used (not venv)
- [x] `where.exe optimus-agent` showed global PATH binary before IDE launch

Recorded by: Vibhanshu  Date: 2026-07-11
Dotenv: N/A — no `.env` / `.env.gateway` on main checkout (keychain-only).
Phase E regression: see `reports/plan-9-75-zed-hitl-runtime-evidence.md` § Post-#36 regression — 2026-07-11.
