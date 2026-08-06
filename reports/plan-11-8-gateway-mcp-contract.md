# Plan 11.8 Gateway MCP — Task 1 contract evidence

**Status:** Task 1 complete; implementation remains stopped before Task 2.

**Scope:** Agent/Gateway typed MCP wire contracts, canonical namespace/manifest helpers, result
content and attribution validation, and deployable import-boundary checks.

## Production changes

- Added `src/optimus/gateway/mcp_models.py` for the agent-side typed contract.
- Added `src/optimus_gateway/mcp_models.py` as an independently deployable duplicate; it imports
  only stdlib and Pydantic and does not import `optimus.*`.
- Both modules define strict extra-forbidden/frozen models for discover/call requests and responses,
  descriptors, content, binding summaries, and `MCPUsageRecordSummary`.
- Both modules validate JSON-compatible arguments and descriptor payloads, reject non-finite floats,
  enforce `profile_id.tool_name`, reject image/audio content types, enforce attribution-state
  monetary invariants, and compute canonical manifest bytes/hashes without disposition or secret
  fields.

## Tests

- Added `tests/unit/mcp/test_models.py`.
- Added `tests/unit/optimus_gateway/test_mcp_models.py`.
- Added `tests/unit/optimus_gateway/test_mcp_import_boundary.py`.

The first RED run failed during collection because the two production modules did not exist. A
test-only repository-root path was corrected before implementation; the production contract was
then written and the focused suite passed.

## Verification commands

```text
uv run --frozen pytest tests/unit/mcp/test_models.py tests/unit/optimus_gateway/test_mcp_models.py tests/unit/optimus_gateway/test_mcp_import_boundary.py -q
..............                                                           [100%]
14 passed in 0.17s

uv run --frozen ruff check src/optimus/gateway/mcp_models.py src/optimus_gateway/mcp_models.py tests/unit/mcp/test_models.py tests/unit/optimus_gateway/test_mcp_models.py tests/unit/optimus_gateway/test_mcp_import_boundary.py
All checks passed!

uv run --frozen pytest tests/unit/mcp tests/unit/gateway/test_client.py tests/unit/gateway/test_models.py tests/unit/optimus_gateway/test_models.py tests/unit/optimus_gateway/test_server.py -q
108 passed in 18.97s

git diff --check
clean
```

The focused test and Ruff commands used the recreated frozen development environment. No live
dependency tier was invoked by Task 1. No upstream credential, endpoint, or secret was used or
recorded.
