# Plan 9.9 Operator Packaging Evidence

## Identity

| Field | Value |
|---|---|
| Implementation SHA | `f120a5afde39e3b3a8a405211ae71653b6e75665` |
| Wheel | `optimus_cost_agent-0.1.0-py3-none-any.whl` |
| Wheel SHA-256 | `1F7F9AD65C3BAC3F769C8A1BE52FA584E4A2CD4DF838794FEA6E7A91441E1DEE` |
| Package version (installed agent-build identifier) | `0.1.0` |
| Workspace git SHA | n/a — live scratch workspace is outside the git checkout by design |
| acpx | `0.12.0` |
| uv | `0.11.26` |
| Model | `claude-haiku` |

## Offline package proof (non-editable install)

- Scratch root: `C:/tmp/optimus-plan99-live5`
- Isolated venv: `C:/tmp/optimus-plan99-live5/venv`
- `optimus` and `optimus_gateway` resolved under isolated `Lib/site-packages` (outside the repository checkout)
- Entry points `optimus-agent.exe` and `optimus-local-gateway.exe` returned `--help` exit 0
- `OPTIMUS_CONFIG_ROOT`: `C:/tmp/optimus-plan99-live5/operator-config` (outside the offline workspace)
- Offline runtime / debug / gateway-log destinations under `C:/tmp/optimus-plan99-live5/outside-repo/workspace/.optimus/...`
- Hostile workspace `.env.gateway` used resolver-readable names (`OPTIMUS_LOCAL_GATEWAY_PROVIDER`, `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY`, `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET`); probe against empty operator-config + empty keyring returned `provider_secrets=False` and `shared_secret=False` (workspace credentials ignored)
- No `PYTHONPATH` injection observed in offline evidence

## Live prerequisites (content-free)

| Check | Result |
|---|---|
| Redis container `optimus-redis` | Running on `127.0.0.1:6379` |
| Redis TimeSeries module | Present (`MODULE LIST`) |
| Credential source | OS keyring service `optimus-cost-agent` fields `model_provider`, `model_provider_api_key`, `local_gateway_shared_secret` (provider name `openrouter`; values not recorded) |
| `pytest -m requires_redis ...` | Not exercised in this session (fixture requires process `OPTIMUS_GATEWAY_URL` / `OPTIMUS_API_KEY` in the parent shell; Redis capability verified via TCP + MODULE LIST instead) |

## Live acpx proof

- Live workspace: `C:/tmp/optimus-plan99-live5/live-workspace` (outside checkout)
- Agent wrapper: `run-isolated-optimus-agent.cmd` invoking isolated `venv/Scripts/optimus-agent.exe` with provider keys cleared
- `OPTIMUS_CONFIG_ROOT` pointed at external `operator-config` for the live process environment
- Gateway: **started** by this live workspace; log path `C:/tmp/optimus-plan99-live5/live-workspace/.optimus/local-gateway.log` (singleton ownership under the starting workspace)
- Gateway startup recorded provider name only (`openrouter`); no key material claimed in evidence
- acpx command shape: `--format json --approve-all --cwd <live-workspace> --agent <wrapper> exec` with docstring task
- Transcript predicates: `session/request_permission` observed before mutation; final stop reason `end_turn`
- Mutation: `example.py` gained a module docstring; no other product source files in the live workspace were modified
- Result payload: `predicates_passed`

## Secret / redaction posture

- No provider API keys, shared secrets, authorization headers, or credentialed URLs are recorded here
- Hostile fixture values must not appear in this report or verifier JSON evidence

## Result

**PASS** — packaged non-editable `optimus-agent` completed a real independently authored `acpx` approve-all docstring mutation using operator-owned keyring credentials, with config root outside the workspace and gateway log ownership under the live starting workspace.
