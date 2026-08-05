# Current-state note: `assert_prompt_retry_preflight` signature supersession

**Status:** Current-state documentation only. Not a digest-bound amendment rewrite.  
**Recorded:** 2026-08-05  
**Branch/HEAD at note:** `agent/cursor/p11-feat-zed-resume` (see git for tip)  
**Owning task:** Plan 11.7 retry-preflight amendment Task 6 docs-freshness  
**Related review fix:** commit `f8c51f2`

## Immutable parent

The merged amendment

`docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md`

remains byte-pinned at SHA-256

`106FD92B8E43F44A7115D7EDB1F9CF1E3EE643E4B6F594FA656FB4119A969B82`.

Its **Required interfaces** section still shows the pre-fix public gate signature
without `launch_identity`. That historical text must not be silently rewritten.

## Live contract (source of truth)

After independent review of Tasks 0–4 and the follow-up fix in `f8c51f2`, the public
runner gate is:

```python
def assert_prompt_retry_preflight(
    *,
    run_attempt_id: str,
    ledger: StageLedger,
    prompt_fixture: Path,
    target_sha256: str,
    live_session_proof: LiveSessionProof | None,
    launch_identity: LaunchSessionIdentity,
) -> RetryPreflightResult:
```

`launch_identity` must come from immutable custody records. The gate binds
`live_session_proof` to that identity and must not re-derive expected identity
from the proof under validation.

Module and export identity are unchanged: the function remains in
`tools/run_plan117_custody_feasibility.py` and in that module's `__all__`.

## Why this note exists

Reviewer finding (post-`f8c51f2`): code/tests were corrected, but the digest-pinned
amendment's Required interfaces were left historical. Per project custody pattern,
approved docs stay byte-pinned; deviations are recorded as current-state notes or a
separately approved follow-up amendment — never a silent rewrite.

## Path A evidence anchor

Task 5 Path A fail-closed seal (no live accepted retry):

`reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json`
