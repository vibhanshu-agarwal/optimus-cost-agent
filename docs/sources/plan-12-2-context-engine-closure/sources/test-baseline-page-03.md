# 3. Test pyramid and evidence tiers

| Tier | Dependency | Fakes permitted | Claim supported |
|---|---|---:|---|
| Unit | In-process functions | Yes | Local logic and contracts |
| Contract | Recorded request/response shape | Yes | Parser and schema behavior |
| `requires_redis` | Real TimeSeries-capable Redis | No | Persistence and retention |
| `requires_gateway` | Real loopback Gateway + approved credential | No | Gateway/provider behavior |
| ACP protocol | Independent `acpx` client | No | Real client compatibility |
| E2E | Spawned ACP process + named dependencies | No | Golden workflow |
| Release | Full process/credential/egress evidence | No | Phase 1 sign-off |

There is no hosted staging Gateway. Provider fakes remain confined to unit and contract tests and
cannot justify a live claim.

## Verification ownership

Every design claim maps to an executable unit, integration, E2E, eval, or release-gate check.
Coverage enforces the Optimus product group and separate context_engine / optimus_model_policy 80% floors; all-source aggregate is informational under section 8A, and safety-critical modules do not regress.