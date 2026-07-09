# Plan 9.7 manual E2E evidence (operator PATH path)

> **Not the contributor path.** Repo `.venv` + `pip install -e ".[dev]"` validates code for
> developers; it does **not** satisfy Plan 9.7 sign-off. Use PATH install below.

## Preconditions

- [ ] New terminal — no venv activated (`echo $env:VIRTUAL_ENV` empty on PowerShell)
- [ ] No `OPTIMUS_*` or provider API keys in the shell environment
- [ ] `.env` and `.env.gateway` renamed away in the workspace used for the test
- [ ] Docker Desktop running (for auto-start Redis)

## 1. Install on PATH

```powershell
cd <repo-checkout>
uv tool install --editable . --reinstall
# If uv unavailable: pip install --user -e . --force-reinstall
uv tool update-shell   # if optimus-agent not found
```

Verify:

```powershell
where.exe optimus-agent
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

Recorded by: _____________  Date: _____________
