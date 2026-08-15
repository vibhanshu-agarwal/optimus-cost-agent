# P11-FEAT-ZED-RESUME current-version Zed `session/load` re-probe brief

**Status:** Forward scope only. This brief authorizes neither an amendment nor
execution. It deliberately contains no production implementation and no
origin-A/correlation launch.

## Question

At the Zed version observed at execution time, does a real Zed client issue ACP
`session/load` after receiving a temporary, top-level `agentCapabilities.loadSession:
true` advertisement and an empty successful `session/load` response?

The answer must isolate Zed's behavior from the shipped Optimus agent's current
non-advertisement. It must not re-diagnose the frozen 1.13.1 seal, whose named
raw Task 0 artifacts are absent from `origin/main` (see
[`p11-feat-zed-resume-task0-evidence-custody-note.md`](../../../reports/p11-feat-zed-resume-task0-evidence-custody-note.md)).

## Required probe shape

- Reuse the frozen Plan 11.7 Task 0 design: begin from a recorded clean source
  identity, create an isolated temporary capability/load probe that changes only
  the top-level `loadSession` advertisement and returns an empty successful
  `session/load`, then restore/remove that isolated probe source.
- Run the real installed Zed binary only with a hermetic user-data root. First
  establish and record the current-version invocation required to bind Zed to
  that root; do not assume a flag from a historical Zed build. The operator's
  live profile, settings, workspaces, and running Zed process remain untouched.
- Use the independently authored `acpx` binary for ACP protocol-layer baseline
  evidence. Use an opaque byte relay for the real-Zed connection so the claim
  that Zed issued (or did not issue) `session/load` is based on captured traffic,
  not a project-authored client inference.
- Do not send an origin-A fixture or claim correlation. The probe has no
  correlation-attempt budget and cannot create `origin-a-4`.

## Normal-operation isolation gate

The temporary advertisement must be unreachable from normal operation. The
implementation must choose an isolated throwaway source/build rooted outside the
normal workspace—not a persistent default or ambient environment switch—and
must prove all of the following before live Zed execution:

1. the normal committed `optimus-agent` does not advertise top-level
   `loadSession`;
2. only the isolated probe executable advertises it and handles the empty probe
   load response;
3. the normal workspace's source digest is unchanged before and after the run;
   and
4. the throwaway source/build and hermetic Zed user-data root are removed after
   successful cleanup.

## Committed evidence contract

The separately scoped change must commit sanitized, reviewable evidence under a
dedicated `reports/` path. At minimum, its manifest records the UTC timestamp,
current branch commit, exact Zed and acpx versions, source/build identities,
hermetic-root provenance and cleanup result, temporary-advertisement proof,
agent capability payload, opaque relay digests, and the sanitized captured
request/response classification. It must preserve the literal `session/load`
exchange when one occurs; if no exchange occurs, it must preserve the bounded
real-Zed observation and name the resulting limitation.

No raw credentials, normal-profile data, or unsanitized transcript may be
committed. Temporary approval cleanup and evidence sanitization must be verified
before the evidence path is staged.

## Result discipline

- `REACHABLE` requires a captured real-Zed `session/load` request and the empty
  successful response from the isolated probe server.
- A real returned method/protocol error is `UNREACHABLE` only when the captured
  exchange identifies it.
- Missing dependencies, failed hermetic isolation, or no captured client
  exchange are `INDETERMINATE` with a named reason. An internal Optimus
  non-advertisement is never a finding about Zed.

The brief must be reviewed and converted into an approved forward amendment
before any code, real-Zed launch, or external-state action occurs.
