# Plan 9.7 manual E2E evidence (operator PATH path)

> **Not the contributor path.** Repo `.venv` + `pip install -e ".[dev]"` validates code for
> developers; it does **not** satisfy Plan 9.7 sign-off. Use PATH install below.

## Preconditions

- [ ] New terminal — no venv activated (`$env:VIRTUAL_ENV` empty on PowerShell)
- [ ] No `OPTIMUS_*` or provider API keys in the shell environment
- [ ] `.env` and `.env.gateway` renamed away in the workspace used for the test
- [ ] Docker Desktop running (for auto-start Redis)
- [ ] Stale shim removed if present: rename `C:\Users\<you>\.local\bin\optimus-agent.exe` if broken

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
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
# Example output: C:\Users\<you>\AppData\Roaming\Python\Python314\Scripts

[Environment]::SetEnvironmentVariable(
  'Path',
  [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + (python -c "import sysconfig; print(sysconfig.get_path('scripts'))"),
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
(paste)
```

## 2. Keychain setup

```powershell
optimus-agent --setup
```

Paste relevant stderr (no secrets) here:

```
(paste)
```

## 3. Config check

```powershell
optimus-agent --workspace-root . --check-config
```

Exit code and stderr:

```
(paste)
```

## 4. Serve + planning call (`claude-haiku`)

Run `optimus-agent --workspace-root .` (or IDE with `"command": "optimus-agent"` only) and
trigger a real planning turn. Confirm the call uses `claude-haiku` through the auto-started
loopback gateway — not merely that processes launched.

Evidence (session log excerpt, gateway log tail — redact secrets):

```
(paste tail of reports/local-gateway.log)
```

## 5. Sign-off

- [ ] `optimus-redis` container running (`docker ps --filter name=optimus-redis`)
- [ ] Local gateway reachable on loopback
- [ ] Planning call succeeded via auto-started stack on `claude-haiku`
- [ ] Operator PATH path used (not venv)
- [ ] `where.exe optimus-agent` showed global PATH binary before IDE launch

Recorded by: _____________  Date: _____________
