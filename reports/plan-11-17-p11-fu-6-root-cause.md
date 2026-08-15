# Plan 11.17 — P11-FU-6 Gateway Lifecycle Investigation

**Status:** Reproduced, root cause unestablished. This report does not close P11-FU-6 or authorize a
source change.

## Windows recurrence and comparison

On Windows 11 `10.0.26200`, CPython `3.14.4`, Git `2.55.0.windows.3`, checkout
`8a05970`, Task 1 launched five completed independent `uv run --frozen pytest tests/unit -q`
processes. Processes 1–4 were clean. Process 5 failed at:

```text
tests/unit/optimus_gateway/test_server.py::test_unknown_route_remains_not_found
ConnectionAbortedError: [WinError 10053]
  at HTTPConnection.getresponse()
```

The raw process log is `unit-05.log`, SHA-256
`74C743AEC60DC3495FAE662C8F61E89116CFC888C5EA75516E48B2458B9CA2D9`. The exact selector then
passed in isolation (`1 passed in 0.94s`) and `test_server.py` passed in-file (`34 passed in
17.97s`). Their raw-log hashes, the four clean process rows, and the interrupted unrun sixth process
are recorded in `reports/plan-11-17-windows-resource-lifecycle-baseline.md`.

The 59-clean no-reproduction disposition is inapplicable after the process-5 recurrence. The
partially started sixth process is unrun and is not included in a success or failure rate.

## FU-6 event timeline

| Event | Owner / evidence | Result |
| --- | --- | --- |
| Gateway construction and bind | `serve_gateway()` creates `ThreadingHTTPServer((bind_host, bind_port), _BoundHandler)` in `src/optimus_gateway/server.py:92-120`; `_start_server()` calls it with port `0`. | The source defines this ordering; the failed log did not record the assigned address. |
| Serve thread start | `_start_server()` starts `threading.Thread(target=server.serve_forever, daemon=True)` before returning `server.server_address`. | The source defines this ordering; thread liveness at failure is unknown. |
| Client request | `test_unknown_route_remains_not_found` calls `_post_json()`; it sends `POST /v1/unknown`. | Completed through request send; failure occurs at `HTTPConnection.getresponse()`. |
| Handler response | `OptimusGatewayHandler.do_POST()` would synchronously call `_send_json(404, {"error": "not found"})` for this path. | No server-side handler completion or exception is present in the raw failure log. |
| Teardown | The test's `finally` calls `_stop_server()`, which orders `shutdown()`, `server_close()`, then `thread.join(timeout=5)`. | Because `getresponse()` raised before the `finally` ran, the observed client exception is upstream of this test invocation's teardown. Server address, post-join liveness, and thread exceptions were not captured and remain unknown. |

This table is an evidence-bound combination of source order and the raw traceback. It does not prove
readiness, shutdown, socket reuse, or a server-thread exception as the cause.

## P11-FU-26 comparison

P11-FU-26's historical `WinError 10053` came from retired Gateway-MCP tests. The pool says that its
test code was removed by Plan 11.12 and transfers only the socket-teardown signal to FU-6. The
current recurrence uses the still-live `test_server.py` helper, but no preserved FU-26 runtime trace
shows the same current `ThreadingHTTPServer` lifecycle edge. FU-26 is corroborating historical
signal, not proof of a common current cause.

## Causal and scope decision

**Decision: `insufficient_evidence`.**

1. FU-26 cannot be proven to pass through the current helper edge because its original test surface
   is retired.
2. FU-5 remains a pre-child-launch Git-handle operation, with no observed socket/server/thread
   resource.
3. No deterministic causal chain reproduces either failure, much less both.
4. FU-6 has reproduced only through `_start_server()` / `_stop_server()` in the test harness. No
   independently driven public `serve_gateway()` lifecycle has failed.

The immediate next observation target is a failure-time diagnostic that records the address,
serve-thread liveness before and after teardown, and any handler/thread exception while retaining the
real route assertion. Until that exists, there is no evidence-named deterministic red. The Task 3
and Task 4 correction paths are unavailable: no test-harness fix, production edit, retry, sleep,
timeout widening, skip, deselection, or `WinError` suppression is permitted.
