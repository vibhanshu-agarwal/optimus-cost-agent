# P11-FEAT-ZED-RESUME `session/load` re-probe

## Finding

**INDETERMINATE / INTERNAL_CAPABILITY_UNAVAILABLE** as of `2026-08-15T12:59:36.411901+00:00` at commit
`71cb9edece036350c1027258ef86f88789630742`.

The installed Zed reported:

```text
Zed 1.15.0 e17dc4f9d50db73a458b64dcce50ecd4878b98a  – \\?\C:\Users\pc\AppData\Local\Programs\Zed\Zed.exe
```

The independently authored client was `acpx 0.12.0`. With the documented
`optimus-redis` container running, acpx created and exported an isolated live
session. The exact `agentCapabilities` payload that acpx persisted from the
Optimus ACP initialization was:

```json
{
  "mcpCapabilities": {"http": false, "sse": false},
  "promptCapabilities": {"audio": false, "embeddedContext": false, "image": false},
  "sessionCapabilities": {}
}
```

It omits `loadSession` (and `sessionCapabilities.resume`), which is the current
Optimus server's deliberate state: `src/optimus/acp/spec.py` explicitly says
not to advertise `loadSession` while `P11-FEAT-ZED-RESUME` remains unimplemented.
Acpx therefore did not force an unsupported `session/load` call; its non-prompt
reconnect returned the following client-side structured error, with its session
identifier redacted:

```json
{
  "jsonrpc": "2.0",
  "id": null,
  "error": {
    "code": -32603,
    "data": {
      "acpxCode": "RUNTIME",
      "detailCode": "SESSION_RESUME_REQUIRED",
      "origin": "acp",
      "retryable": true,
      "sessionId": "unknown"
    },
    "message": "Persistent ACP session <redacted> could not be resumed: agent does not support session/resume or session/load"
  }
}
```

This cleanly establishes the internal capability gate, not Zed reachability. No
literal `session/load` exchange exists because acpx declined to call a method
that the Optimus agent did not advertise; Zed was queried only for `--version`
and was never launched. The earlier 2026-08-15 run was `INDETERMINATE /
PRECONDITION_UNMET` because Redis was down; this run satisfies that documented
prerequisite but leaves the external question open.

The disposable workspace’s launch approval was created through `optimus-trust`,
then revoked and verified absent before the workspace was removed. The run made
zero Zed launches and zero origin-A launches.

The frozen Task 0 record names three evidence artifacts that are absent from
current `origin/main`; the resulting comparison limitation is recorded in the
[Task 0 evidence custody note](p11-feat-zed-resume-task0-evidence-custody-note.md).
This report neither re-diagnoses the historical 1.13.1 seal nor supplies an
origin-A/amendment-scoping conclusion.

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

The probe uses acpx to create and export an isolated session, retains the live
`agentCapabilities` that acpx persisted in that export, imports it into a second
isolated acpx home, and requests a non-prompt reconnect. If the payload omits
`loadSession`, the result is **INDETERMINATE /
INTERNAL_CAPABILITY_UNAVAILABLE** without forcing an unsupported call: that is
evidence about the Optimus agent gate, not Zed.
If it advertises `loadSession`, acpx reconnects through `session/load` when
`session/resume` is not advertised; a real result is **REACHABLE** and a returned
error is **UNREACHABLE**. A missing documented dependency is **INDETERMINATE /
PRECONDITION_UNMET**, while a clean but incomplete exchange is **INDETERMINATE /
OBSERVATION_INCOMPLETE**. The former includes the exact runbook command:
`optimus-agent --workspace-root <throwaway-workspace> --check-config --strict`.

This probe tests the live ACP API precondition only. It does not prove that Zed
itself emits `session/load` after restart, establish origin-A correlation, or
authorize a budget-expansion amendment. The separate current-version Zed probe
must use the frozen Task 0 temporary-advertisement design and commit its
sanitized evidence; it is deliberately outside this PR.
