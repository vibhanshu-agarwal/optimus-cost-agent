# ADR-017: One-time Package A terminal coverage exception

**Status:** Accepted. **Decider:** Operator. **Date:** 2026-10-01 (Asia/Calcutta).
**Relation:** Records the exact exception to the numeric safety-critical non-regression condition;
does not change ADR feature requirements or the general coverage policy.

## Source and exact selected scope

S3, `optimus-handoff\decisions-sources\2026-10-02-claude-session-context-engine-package-a-export.zip`, SHA-256 `9B89272060555D1542B14F25C37807F21C5763222D0A93CF2C1ECC791D642A66`, includes original question/result
`toolu_014hFoVch2v66mDcDau7J6Rd`, UTC `2026-10-01T18:25:42.932Z`.
Question: "Task 3's coverage gate is still unmet: at 38a465f, server.py (lines 574–575) and
client_sdk.py (lines 326, 338) are below Task 2, in code Package A never changed. AGENTS.md says
safety-critical modules must not regress, so only you can grant an exception. Approve Codex's
narrow exception, or keep the hold?" Selected **"Approve narrow exception (Recommended)"**, rather than
"Keep the hold". The accepted Codex decision text is:

> Approve a one-time Task 3 numeric coverage exception at head
> `38a465fda38c73712162ab2b144c1d8da3cceeeb`, solely for unchanged server.py statements 574–575
> (90.57377049180327% -> 90.1639344262295%) and client_sdk.py statements 326/338
> (78.38709677419355% -> 77.74193548387096%). Preserve the terminal failed non-regression result
> and record it as an accepted residual, with the observed coverage-repeatability class assigned
> to P11.26-CAND-5 for later scoped work. This grants no general threshold/policy change, new test
> execution or implementation, push, PR, merge, later task, paid/live call or cleanup authority.

## Reasoning and alternatives

The four newly missing statements are in unchanged cancellation/timeout code. The reviewed lock
controls restored launch approvals to its exact baseline; all applicable commit hooks passed.
The operator accepts this finite measured residual to avoid widening Package A into another
owner's test area. Keeping the hold would require a separately agreed test-only scope and one
uncontended full validation. Best-of-N, exclusions or a new threshold were not selected.
Unchanged source and passing hooks do not prove every omitted path correct.

## Recorded result and custody

Numeric non-regression remains **NOT MET with an accepted residual**, never PASS. The exception is
valid only for the named observation at `38a465f`, not future commits or different missing lines.
Task 3 offline technical acceptance was recorded under this exception; live Zed/ACP is unproved.
The historical measurement remains valid when a docs-only child adds records; it is not described
as a newly passing full-suite run or a general exception on that child.

Observed variability in launch_approvals/lifecycle/server/client_sdk retains
`P11.26-CAND-5-REPEATABILITY-ATTRIBUTION` intake custody, under `P11-FEAT-ACP-RUNTIME-HARDENING`.
Known lock paths are now deterministic. Remaining paths require separately scoped owner work;
no census, tests, production remedy or gate-policy rewrite is commissioned by this record.
See the [Package A delivery record](../superpowers/reviews/2026-10-02-plan-12-2-package-a-delivery.md) and sole backlog.
Later publication authority is separately recorded by ADR-016; this exception itself grants none.
