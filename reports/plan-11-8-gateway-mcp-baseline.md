# Plan 11.8 Gateway MCP — Task 0 baseline evidence

**Status:** Read-only baseline verification completed after approval and plan commit.

**Date:** 2026-08-06

## Result

The approved design and four authoritative PDF inputs were re-derived from committed Git object
bytes. The source/test/PDF/charter tree has no tracked diff. The pre-existing untracked `tmp/`
directory is unchanged.

The approved implementation plan is now committed, so the post-approval branch state is:

| Ref | Value |
|---|---|
| Branch | `agent/codex/plan-11-8-p11-feat-gateway-mcp` |
| `HEAD` | `64906a1e1e534f833459983c605d240866617078` — `docs: add Plan 11.8 Gateway MCP implementation plan` |
| `HEAD^` | `4a7ad47c13fe23420d6c9c97daaee784c47493c5` — approved design freeze |
| `origin/main` | `662e88666093bb93e51d35ed25f8dd7bc1159ce0` |
| Charter blob | `b10e1c884f06f24778969afbbe6e5cde2fb5a6a8` |

`HEAD^` is the frozen design baseline required by the plan; the additional `HEAD` commit contains
only the approved implementation-plan document.

## Committed-byte digests

The following were computed in memory by invoking `git show origin/main:path`-style blob reads and hashing the returned
bytes. No checked-out PDF or working-copy digest was used.

| Object | SHA-256 |
|---|---|
| `origin/main:docs/Optimus-Cost-Agent-Architecture-v2.17.pdf` | `a21bdb01bc737fa3d8ebffba8b8b7df96c65101812e17f31c3c7324368d15024` |
| `origin/main:docs/Optimus-Cost-Agent-LLD-v2.40.pdf` | `0329aef8b5392e05ddbb19ac3f76f3ce7f4fe3c4b728aef6cbfc4de84b324d03` |
| `origin/main:docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf` | `461a720fa28576523c87c2f2f89ee1fc52c99971e51acc22edc85e8c375a7070` |
| `origin/main:docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf` | `b435e55687116bd7c4d7e78b48e50d8da9ed0801575b7b5485f262d35c1b31a4` |
| Design body from `4a7ad47c13fe23420d6c9c97daaee784c47493c5:docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md`, normalized per its own header method | `1eb6cb626e1ed74e83f9ce81b048cb68da8105a1468f8f12272620bf2325f911` |

## Scope and seam census

The frozen design and charter contain the exact two routes, all six named Gateway components, and
the explicit custody entries `P11-FU-9`, `P11-FU-12`, `P11-FU-13`, `P11-FU-14`, and `P11-FU-15`.

The current repository seams named by the implementation plan were found:

- Existing Gateway route seam: `src/optimus_gateway/server.py` (`do_POST`, `serve_gateway`) and
  `src/optimus_gateway/tool_handlers.py` (`TOOL_ROUTE_PATHS`).
- Existing agent client seam: `src/optimus/gateway/client.py` (`GatewayClient`, `post_tool_json`).
- Existing local trust seam: `src/optimus/mcp/runtime.py` (`MCPRuntimeTrustContext`) and
  `src/optimus/guardrails/mcp_trust.py` (`MCPTrustRegistry`, `MCPDescriptorExposureGuard`).
- Existing signed Gateway bootstrap seam: `src/optimus_security/launch_manifest.py`
  (`GatewayChildManifest`, `build_gateway_child_manifest`), used by the existing ACP launch
  helpers and Gateway tests.

The pre-implementation `pyproject.toml` marker census confirms the current live-tier exclusions
include `requires_redis`, `requires_gateway`, `requires_live_gateway`, `requires_acpx`, and
`requires_windows_desktop`; `requires_mcp_http` and `requires_mcp_stdio` are not yet present.
Task 8 owns adding both marker declarations and both default `addopts -m` exclusions.

## Commands and outcomes

```text
git status --short --branch
## agent/codex/plan-11-8-p11-feat-gateway-mcp...origin/main [ahead 2]
?? tmp/

git rev-parse HEAD
64906a1e1e534f833459983c605d240866617078

git rev-parse HEAD^
4a7ad47c13fe23420d6c9c97daaee784c47493c5

git rev-parse origin/main
662e88666093bb93e51d35ed25f8dd7bc1159ce0

git diff --check
clean

git diff --stat
empty; no tracked working-tree diff
```

No source, test, authoritative PDF, charter, dependency, lockfile, or runtime mutation occurred
in Task 0. The implementation plan remains the only new tracked commit; `tmp/` remains untracked
and untouched.
