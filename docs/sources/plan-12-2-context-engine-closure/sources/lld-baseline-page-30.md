Target contract after the named trusted-policy / Task 11 / coverage migration as applicable; the dated inactive production baseline is stated on the cover.

# 9D. Gateway Server-Side Policy Revalidation

The Gateway independently revalidates every privileged input. Agent-side checks are defense in
depth and never authoritative.

| Control | Gateway enforcement |
|---|---|
| Allowed domains | Intersect caller request with local allowlist; forward effective policy; reject returned URLs outside it |
| Extract provenance | Require exact prior search result for the same `run_id`; revalidate redirects and final URL |
| Capacity and accounting | Enforce the complete request guard under trusted policy; retain actual usage and explicit unknowns. Product monetary stops are removed only by the released Task 11 migration. Evaluation spend limits are separately scoped. |
| Call caps | Key by run and tool; do not share a paid-search configuration gate |
| Tool policy | Recheck tool class, policy signal, execution mode, and authenticated local subject |
| Usage | Reject missing, malformed, negative, or unparseable provider-reported cost |

```python
def authorize_tool_call(request, *, policy, ledger):
    effective_domains = policy.intersect_domains(request.domains)
    policy.require_tool_allowed(request.tool, request.execution_mode)
    policy.require_call_capacity(request.run_id, request.tool)
    require_final_capacity_and_output(request, policy)
    return AuthorizedToolCall(
        request=request,
        effective_domains=effective_domains,
    )
```

There is no org/project dimension. Cross-run spend policy remains `P9.85-FU-3` and is not added by
this correction.