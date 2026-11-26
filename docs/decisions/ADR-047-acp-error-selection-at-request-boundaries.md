# ADR-047: ACP error selection at request boundaries

**Status** — Operator approved implementation on 26 November 2026. Draft pending independent review and repository delivery.

## Decision and provenance

In the Optimus Codex chat on 26 November 2026 IST, the operator replied “Approved” to the question “should I implement the three remaining ACP error changes for #304?” The offer listed an unavailable dependency, an unavailable session, and contention with an executing turn or usage report. It proposed checking `-32913` against the registry before allocating it. [Issue #304](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/304) owns the acceptance state.

| Owner-confirmed outcome | Selected response | Reason |
| --- | --- | --- |
| An exposed dispatcher method requires a missing local dependency | `INTERNAL_ERROR`, `dependency unavailable`, `data.reason = "DEPENDENCY_UNAVAILABLE"` | The method exists. A fixed reason exposes the availability condition without leaking dependency configuration. |
| A valid prompt or session setter cannot access a session | `RESOURCE_NOT_FOUND`, `unknown session`, no data | ACP already defines the resource code. An absent session and a session kept privately in retention receive the same public response. |
| Active-turn or usage-report custody prevents a second prompt | `TURN_BUSY`, `a turn is already in progress`, no data | A distinct code lets a client distinguish contention from cancellation. The first request retains its ownership. |

Codex selected `-32913` after checking the vendored ACP schema, the Plan 11.18 registry oracles, and the existing Optimus application allocations. The value is outside the JSON-RPC reserved interval `-32768..-32000`. Put all three outcomes in the existing ACP selector and serialize through the shared error sanitizer. Determine session availability through the current request's retention lease after the method has validated its shape. An unrelated method or malformed request keeps its method or validation error.

## Alternatives and boundaries

- Keeping `METHOD_NOT_FOUND` for missing dependencies and `REQUEST_CANCELLED` for contention preserves historical compatibility but conflates conditions clients must handle differently.
- Keeping `INVALID_REQUEST` for unavailable sessions preserves legacy client behavior but groups valid requests with malformed ones.
- A session-status field offers more detail and would expose whether a session exists privately in retention. The shared response preserves that privacy boundary.
- Using a new numeric code for every failure enlarges the client-facing vocabulary. The existing resource and internal codes cover the first two cases, while a distinct application code covers contention.

Policy-refusal precedence, queue limits, response handoff and the production framed-transport restriction stay in force. The NDJSON notification path handles `session/cancel` through queued or active work. An ID-bearing `session/cancel`, `session/load` and the framed `optimus.*` methods are unsupported in the duplex request adapter and return `METHOD_NOT_FOUND` for both absent and privately retained sessions. Registry refusal precedes the Gateway-client check. The agent runner check precedes validation of the retired completion condition. The prompt handler validates the request shape, checks availability, then checks for usable text. The refusal diagnostic updates `/why` state only while the request holds a session lease. The tests exercise the dispatcher and NDJSON owner paths offline. Client compatibility for actual overlapping prompts remains a separate acceptance question. Ordinary acpx serializes same-session prompts, so a code-handling probe can establish only how that client handles the envelope. Implementation approval is scoped to this patch. Review, publication and merge have separate gates. Live E3 stays on hold.
