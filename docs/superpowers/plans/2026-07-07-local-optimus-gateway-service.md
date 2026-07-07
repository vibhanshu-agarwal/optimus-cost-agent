# Local Optimus Gateway Service Implementation Plan

> **Prerequisite for:** Plan 9.6 (`docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md`)
> Tasks L5, L6, and the strict preflight gateway-auth probe (`--check-config --strict`) all assume
> a real Optimus Gateway is reachable. It is not — see "Retrospective" below. This plan builds the
> smallest thing that makes that assumption true, so those tasks can be verified against a genuine
> live LLM call instead of fake gateway credentials.

**Goal:** A small, self-hosted local service that implements the Optimus Gateway wire contract
(`POST /v1/responses`) by proxying to a real provider (Anthropic) using a developer-owned key. The
agent side never holds a provider key; it holds a Gateway URL and a locally-generated shared secret,
exactly as the existing gateway-only architecture already assumes — the difference is the Gateway
is now a process you run yourself, not a hosted service someone issues you credentials for.

**Status:** Not started. Scoping only.

## Retrospective: why this plan exists

Plan 9.6 was written assuming an Optimus Gateway backend already existed somewhere reachable, and
that "real Gateway credentials" meant obtaining a key from that service — the same way `redis:8` is
something you `docker run` yourself, real Gateway access was implicitly treated as equally available.
It is not: `src/optimus/gateway/client.py` is an outbound HTTP client only; there is no server-side
implementation anywhere in this repository, and no hosted instance exists to issue keys against. This
was an unstated dependency that should have been an explicit planning checklist item — "does the
named external dependency actually exist, and who authorizes access to it" — before L5/L6 were
speced as if it did. Recording this here so the gap is documented, not just fixed quietly.

Separately, the original intent behind "Optimus Gateway" was clarified during planning: it was
always meant to be a **local proxy** so the agent doesn't juggle multiple provider keys directly —
not a multi-tenant hosted service. This plan builds that, scoped to what a single-developer
portfolio project actually needs.

## Non-goals (v1)

- Multi-tenant hosting, remote deployment, or any exposure beyond `localhost`.
- Provider abstraction beyond Anthropic. Other providers in `LOCAL_PROVIDER_KEY_NAMES`
  (OpenAI, GLM, OpenRouter, Tavily, ...) can follow the same pattern later if needed.
- `/v1/tools/*` and `/v1/observability/*` endpoints (`GatewayClient.post_tool_json` /
  `post_observability_json`). Nothing in Plan 9.6's L5/L6 calls them; only `/v1/responses` is
  in scope.
- Production-grade hardening (rate limiting, key rotation, multi-key management). Single shared
  secret, single provider key, both from the operator's own environment.

## Scope

### 1. Service location and shape

Open decision for the implementer to confirm placement — proposed: `src/optimus_gateway/` as a
sibling package to `src/optimus/` (it is a distinct process/deployable, not a module the agent
imports). A minimal stdlib-or-lightweight-framework HTTP server is enough; no need for the async
stack the agent side uses.

### 2. Endpoint contract (must match `src/optimus/gateway/models.py` exactly)

**Request** — what `GatewayClient.create_response()` sends:

```
POST /v1/responses
Authorization: Bearer <shared-secret>
Content-Type: application/json

{"model": "claude-haiku", "input": "<prompt text>", "metadata": {...}}   # metadata optional
```

**Response** — what `parse_gateway_response()` requires:

```json
{
  "id": "resp-123",
  "output_text": "the model's actual text output",
  "gateway_usage": {
    "gateway_request_id": "req-abc",
    "provider": "anthropic",
    "billing_units": 42,
    "cost_usd": "0.0004",
    "cache_hit": false
  }
}
```

- Required: `gateway_usage.gateway_request_id`, `.provider`, `.billing_units` (int ≥0), `.cost_usd`
  (Decimal-parseable string or number, ≥0). Everything else in `GatewayUsage` is optional.
- `output_text` can be a plain string, or omitted in favor of an `output` list shaped like
  `[{"content": [{"type": "output_text", "text": "..."}]}]` — `_extract_text_from_output` handles
  both. Plain `output_text` is simpler; use it.
- Auth failure → HTTP 401 or 403 (any body). `GatewayHttpError` carries the status through, and the
  preflight strict-mode auth probe string-matches `"401"`/`"403"` in the exception message.

### 3. Real cost computation

Pull actual token usage from Anthropic's response and multiply by real published per-token
Haiku pricing to produce `cost_usd`; `billing_units` = total tokens (define input+output split
explicitly in the implementation, don't leave it ambiguous). A stub that fakes cost defeats the
point of a *cost* agent — this is worth getting right even at v1.

### 4. Model id mapping

Agent-facing model strings (e.g. `"claude-haiku"`) map to real Anthropic model ids
(e.g. `claude-haiku-4-5-20251001`) via a small explicit dict in the service. Keep it in one place,
easy to extend when more models are added.

### 5. Config: `src/optimus/config/gateway.py` loopback exemption

**Decision (confirmed):** exempt `127.0.0.1` / `localhost` origins from the https-only requirement,
scoped strictly to non-production mode, documented as a trust-boundary exception — traffic never
leaves the machine, so TLS termination adds no real protection for this deployment shape. Every
other origin (including anything in `extra_trusted_origins`) keeps the existing https-only rule
unchanged.

Proposed implementation sketch (for the implementer to refine, not a final diff):

```python
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

def _is_loopback(hostname: str | None) -> bool:
    return (hostname or "").lower() in _LOOPBACK_HOSTS

def _normalize_origin(value: str, *, allow_insecure_loopback: bool = False) -> str:
    parsed = urlparse(value.strip().rstrip("/"))
    scheme_ok = parsed.scheme == "https" or (
        allow_insecure_loopback and parsed.scheme == "http" and _is_loopback(parsed.hostname)
    )
    if not scheme_ok or not parsed.netloc:
        raise ValueError(f"gateway origin must be an https origin: {value}")
    return f"{parsed.scheme}://{parsed.netloc.lower()}"
```

`validate_trusted_gateway()` needs the same `allow_insecure_loopback=not self.production_mode` passed
through for `self.gateway_url`'s origin check, and should treat a loopback origin as automatically
trusted in non-production mode (no need to also enumerate it in `OPTIMUS_EXTRA_GATEWAY_ORIGINS` —
that mechanism stays reserved for real staging origins elsewhere, which still must be https).

**Must not regress:** `production_mode=True` (the default) continues to reject every non-https /
non-built-in origin exactly as today — the existing `rogue.attacker.com`-style rejection tests in
`tests/unit/config/test_gateway_settings.py` must stay green unchanged.

**New unit tests to add (TDD, write these failing first):**
- loopback `http://127.0.0.1:<port>` origin accepted when `production_mode=False`.
- same origin rejected when `production_mode=True` (default) — loopback is not a blanket exemption,
  only an explicit non-production one.
- non-loopback `http://example.com` origin still rejected even when `production_mode=False` — only
  loopback gets the exemption, not arbitrary http.

### 6. Documentation

- README "Optimus Gateway access" section: clarify the Gateway is a self-hosted local process for
  this project, not a hosted service — how to run it, how to generate the shared secret, which env
  var goes on which side (`ANTHROPIC_API_KEY` on the gateway service's own env only, never in the
  agent's `.env`).
- Explicit security note: this service must never be bound beyond `127.0.0.1` / `localhost` without
  adding real TLS first — the loopback exemption above is only sound because traffic stays on one
  machine.

## Definition of Done

- [ ] Gateway service unit tests (payload shaping, auth check, model-id mapping, cost calculation)
      using a fake Anthropic client — deterministic, no live tier needed here.
- [ ] `config/gateway.py` loopback exemption: new tests green, all existing trusted-origin tests
      unchanged and green (no production-mode regression).
- [ ] One live smoke test: a real call through the running local gateway process to real Anthropic
      Haiku with a minimal prompt, asserting a real response and `cost_usd > 0`. This is the "the
      whole chain actually works" proof, separate from and prior to re-running Plan 9.6's L5 tests.
- [ ] Manual runbook: steps to run the service, generate the shared secret, set env vars on both
      sides, and smoke-test `/v1/responses` with `curl` before wiring into pytest.
- [ ] Plan 9.6 L5 tests (already implemented) re-run against this service for a genuine live result,
      not fake gateway credentials. L6 (spawned-agent e2e) can then proceed on the same basis.

## Sequencing

This lands before Plan 9.6 L5/L6 are considered "real." L1–L4 and L9 (Redis-only tiers) are
unaffected and already stand on their own live evidence — this plan does not touch them.
