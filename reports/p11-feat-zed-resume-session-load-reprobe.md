# P11-FEAT-ZED-RESUME `session/load` re-probe

## Finding

**INDETERMINATE** as of `2026-08-15T11:28:04.040327+00:00` at commit
`e624632b10169de938188e8001dbc822ee6ebd31`.

The installed Zed reported:

```text
Zed 1.15.0 e17dc4f9d50db73a458b64dcce50ecd4878b98a  – \\?\C:\Users\pc\AppData\Local\Programs\Zed\Zed.exe
```

The independently authored client was `acpx 0.12.0`. Its temporary, non-prompt
ACP session could not reach `initialize`: the real Optimus agent stopped at
startup because local Redis was unreachable (`Timeout connecting to server`).
Consequently the live result contains `capability_payload: null` and
`session_load_exchange: null`; no claim about `session/load` support is possible.

The disposable workspace’s launch approval was created through `optimus-trust`,
then revoked and verified absent before the workspace was removed. The run made
zero Zed launches and zero origin-A launches.

## Re-run

```powershell
uv run --frozen python tools/probe_p11_zed_session_load.py C:\Users\pc\AppData\Local\Temp
```

The sole argument must be an existing non-repository directory. The probe creates
and removes one child directory, asks for approval of that exact child workspace,
and always records the observed Zed version, acpx version, UTC timestamp, commit,
the resolved acpx launcher and SHA-256, capability payload, and `session/load`
exchange. It neither starts Zed nor sends a prompt, Gateway request, origin-A
fixture, or correlation launch. Its protocol records and command streams pass
through the repository evidence sanitizer before they are emitted.

Before authoring its temporary approval, the probe verifies that the keyring has
no approval for its unique child workspace. It retries revocation and absence
verification at most three times. If that cleanup cannot be verified, the result
is **INDETERMINATE**, the child workspace is retained, and its `cleanup_remediation`
field gives the exact workspace-scoped `optimus-trust ... revoke` command; the
probe never represents that run as safely cleaned up.

When Redis is reachable, `acpx` creates and exports a session, imports it into a
second isolated acpx home, and uses a non-prompt reconnect to make acpx invoke
`session/load` when `session/resume` is not advertised. `REACHABLE` requires both
`loadSession: true` and a real result; a returned error is `UNREACHABLE`; any
missing prerequisite or incomplete exchange is `INDETERMINATE`.

This probe tests the live ACP API precondition only. It does not prove that Zed
itself emits `session/load` after restart, establish origin-A correlation, or
authorize a budget-expansion amendment. The requested UNREACHABLE-only scoping
position is not reached by this INDETERMINATE result.
