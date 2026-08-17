# Plan 11.19 current-Zed `session/load` re-probe

## Finding

**INDETERMINATE / RELAY_FAILURE** as of `2026-08-17T16:37:37.933990+00:00` at commit
`1be938c5e6666c75e0892b6afb54e3afb1783625`.

This is a bounded no-exchange observation. No ACP `session/load` request or response was
captured on the opaque relay. The finding is **not** `UNREACHABLE`: the brief and verifier
require a captured protocol-level error object for that class, and none exists here.

## What this run established

Four authorized live Windows shots refined the harness until the launch and settings layers
were verified. The pinned evidence is the final unattended shot (shot 4):

| Layer | Outcome |
|---|---|
| Hermetic GUI launch | Succeeded (`Zed.exe` app binary, `--user-data-dir`, `returncode: 0`, visible window) |
| Hermetic settings | Succeeded (`APPDATA`-only bind; `…\zed-appdata\Zed\settings.json` present before and after launch with identical SHA-256) |
| Opaque relay ACP capture | Failed closed — capture files never appeared; committed relay digests are of empty byte streams |
| Origin-A | Zero launches |
| Cleanup | Verified (`cleanup_verified: true`; scratch roots removed) |

The isolated temporary probe advertised top-level `loadSession: true` and answered
`session/load` with `{}` under independent `acpx` 0.12.0. The normal production agent did
not advertise `loadSession`. Normal source digests were unchanged across the run.

## Bounded observation (not a protocol claim)

During shot 4 the operator observed Zed's **Unrecognized Project / Restricted Mode**
workspace-trust dialog for the hermetic `zed-workspace` path. Restricted Mode's own UI copy
states that it prevents project settings from applying and MCP server integrations from
installing. That observation is recorded here as a **plausible structural reason** the
unattended relay never dialed. It is **not** asserted as a captured ACP method/protocol
error, and it must not be read as `UNREACHABLE` or as proof that Zed "does not support"
`session/load`.

## Non-claims

- Does not re-diagnose Zed 1.13.1.
- Does not establish origin-A correlation or authorize a budget-expansion amendment.
- Does not claim that a trusted workspace plus a manual Agent-panel start would (or would
  not) produce `session/load`; that would be a differently shaped experiment outside this
  pinned unattended lane.

## Identities (shot 4)

- Zed: `1.15.0 e17dc4f9d50db73a458b64dcce50ecd4878b98a3` (app
  `C:\Users\pc\AppData\Local\Programs\Zed\Zed.exe`; CLI
  `…\Zed\bin\Zed.exe` used only for discovery).
- acpx: `0.12.0`.
- Live-Zed lane closed by operator decision 2026-08-17 after pinning shots 1–4; no further
  live Zed launches for Plan 11.19.
