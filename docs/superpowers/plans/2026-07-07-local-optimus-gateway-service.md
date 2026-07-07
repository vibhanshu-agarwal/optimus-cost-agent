# Local Optimus Gateway Service Implementation Plan

> **Prerequisite for:** Plan 9.6 (`docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md`)
> Tasks L5, L6, and the strict preflight gateway-auth probe (`--check-config --strict`) all assume
> a real Optimus Gateway is reachable. It is not — see "Retrospective" below. This plan builds the
> smallest thing that makes that assumption true, so those tasks can be verified against a genuine
> live LLM call instead of fake gateway credentials.

**Goal:** A small, self-hosted local service that implements the Optimus Gateway wire contract
(`POST /v1/responses`) by proxying to a real upstream LLM provider using a developer-owned key. The
agent side never holds a provider key; it holds a Gateway URL and a locally-generated shared secret,
exactly as the existing gateway-only architecture already assumes — the difference is the Gateway
is now a process you run yourself, not a hosted service someone issues you credentials for.

**Status:** Loopback exemption and a v1 stub service landed on `agent/cursor/local-optimus-gateway`
(`80b3d1a` → `53cf8da`), verified working end-to-end (including a real request that reached
`api.anthropic.com` and got a genuine — if auth-rejected — response). That v1 hardcoded Anthropic as
the only upstream. **This doc now reverses that choice before further work continues** — see "Design
Revision" below. The loopback exemption (`4901b75`) is unaffected and stays as-is; only the upstream
adapter and its config change.

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

## Design Revision (2026-07-08): OpenAI-compatible primary, Anthropic secondary

**What changed:** v1 (`53cf8da`) built `UrllibAnthropicClient` as the only upstream adapter,
because Anthropic (Haiku) was the model already used throughout Plan 9.6's L5 tests. That was the
wrong default to standardize on. Almost all real operators of this project will hold an OpenAI or
OpenRouter key, not a native Anthropic key — and OpenRouter itself speaks the OpenAI Chat
Completions wire format, so an OpenAI-compatible adapter pointed at OpenRouter's `base_url` reaches
Anthropic, Google, Meta, and Mistral models too, without any provider-specific code beyond the two
adapters below. This mirrors how LiteLLM, JetBrains AI Assistant, and Zed support "100s of
providers": in practice it's two or three wire-format adapters plus a per-provider config record,
not one handler per provider name.

**Decision:** OpenAI-compatible becomes the primary/default adapter. The already-built
Anthropic-native adapter (`UrllibAnthropicClient`) is kept, not deleted — demoted to a secondary,
explicitly-selected option for operators who hold a native Anthropic key and don't want to route
through OpenRouter.

**New primary contract** — adapter → upstream provider:

```
POST {base_url}/chat/completions        # e.g. https://api.openai.com/v1 or https://openrouter.ai/api/v1
Authorization: Bearer <provider-api-key>
Content-Type: application/json

{"model": "<model-id>", "messages": [{"role": "user", "content": "<prompt text>"}]}
```

Response:

```json
{
  "id": "chatcmpl-...",
  "choices": [{"message": {"role": "assistant", "content": "the output text"}}],
  "usage": {"prompt_tokens": 42, "completion_tokens": 18, "total_tokens": 60}
}
```

This maps directly onto the existing internal seam — `AnthropicMessageResult` (or a renamed
provider-agnostic equivalent) with `message_id`, `output_text`, `input_tokens`, `output_tokens` —
`id` → `message_id`, `choices[0].message.content` → `output_text`, `usage.prompt_tokens` /
`.completion_tokens` → the token fields. The `create_message(*, model, input_text) -> ...Result`
`Protocol` in `anthropic_client.py` does not need to change; only a new adapter class implementing
it, plus config to select which adapter is active. Consider renaming the protocol/module away from
"anthropic-specific" naming now that it's one of two implementations (implementer's call, not a
blocking requirement).

**The `/v1/responses` contract the *agent side* sees is unchanged** — this revision is entirely
upstream of `handle_responses_request`; `parse_gateway_response()` on the agent side does not change
at all. Nothing about Task L5's tests changes because of this revision.

## Non-goals (v1)

- Multi-tenant hosting, remote deployment, or any exposure beyond `localhost`.
- A handler per provider name. Two wire-format adapters (OpenAI-compatible, Anthropic-native) cover
  OpenAI, OpenRouter, Groq, Together, Azure OpenAI, and (via OpenRouter) Anthropic/Google/Meta/
  Mistral models without new code — see "Design Revision" above. A third adapter (e.g. Google's
  native Gemini API) is out of scope until an operator actually needs it.
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

This contract is fixed regardless of upstream provider — `"claude-haiku"` and `"provider":
"anthropic"` above are illustrative values from when Anthropic was the only adapter. Post
Design-Revision, `gateway_usage.provider` reflects whichever upstream actually served the request
(`"openai"`, `"openrouter"`, or `"anthropic"`), and the `model` field is whatever agent-facing alias
or passthrough id was requested. Nothing here changes structurally.

### 3. Real cost computation

Pull actual token usage from the upstream response and multiply by real published per-token
pricing to produce `cost_usd`; `billing_units` = total tokens (input + output, defined explicitly,
not ambiguous). A stub that fakes cost defeats the point of a *cost* agent — this is worth getting
right even at v1.

With two adapters now in scope, pricing becomes a small `(provider, resolved_model_id) -> rates`
table rather than one hardcoded Haiku rate — same shape (`billing_units`/`compute_cost_usd` still
just take token counts in, `cost_usd` out), just keyed. Unknown `(provider, model)` combinations
should fail loudly (`ValueError`), not silently default to some rate — an unpriced model producing
a wrong-but-plausible cost figure is worse than an explicit error, given this is a cost agent.
A default/fallback tier is acceptable only for the live smoke test's own minimal-cost sanity check,
not for anything a real operator run would hit silently.

### 4. Model id mapping

Provider-scoped aliases, not a single flat table: the agent-facing model string (e.g.
`"claude-haiku"`) resolves against whichever provider is configured
(`OPTIMUS_LOCAL_GATEWAY_PROVIDER`), because the same alias means a different real model id per
provider — e.g. `"claude-haiku" → "claude-haiku-4-5-20251001"` when `PROVIDER=anthropic`, or
`"claude-haiku" → "anthropic/claude-3.5-haiku"` when `PROVIDER=openrouter`. Keep the existing
Anthropic-only table as the `anthropic` provider's entry, add an `openrouter`/`openai` entry
alongside it — same file, one dict per provider, not a redesign.

Direct passthrough must also work: an operator who wants to pass `openai/gpt-4o-mini` or any other
provider-native model id verbatim (no alias defined) should be able to — only fall back to
"unsupported gateway model" if the string matches neither a known alias nor looks like a
plausible passthrough id for the active provider. Don't make every new model require a code change.

### 5. Provider configuration

New env vars on the gateway service's own process (never the agent side):

- `OPTIMUS_LOCAL_GATEWAY_PROVIDER` — `openai` | `openrouter` | `anthropic`. Default: `openrouter`
  (covers the most models with one key, per the Design Revision above).
- `OPTIMUS_LOCAL_GATEWAY_BASE_URL` — override for the OpenAI-compatible adapter's base URL. Defaults
  derived from `PROVIDER` (`https://api.openai.com/v1` for `openai`, `https://openrouter.ai/api/v1`
  for `openrouter`); required only if pointing at some other OpenAI-compatible endpoint.
- Provider API key: reuse `ANTHROPIC_API_KEY` when `PROVIDER=anthropic`; introduce
  `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` (or similarly-named single var) for the OpenAI-compatible
  path so `OPENAI_API_KEY` doesn't have to double as both "the key this gateway proxies with" and
  a name already reserved/rejected elsewhere in `LOCAL_PROVIDER_KEY_NAMES` on the agent side —
  implementer's call on exact naming, but keep it unambiguous which var is being read.

### 6. Config: `src/optimus/config/gateway.py` loopback exemption

**Status: implemented** (`4901b75`), unaffected by the Design Revision above — this section is
kept for reference only.

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

### 7. Documentation

- README "Optimus Gateway access" section: clarify the Gateway is a self-hosted local process for
  this project, not a hosted service — how to run it, how to generate the shared secret, which
  provider env vars go on which side (real provider key on the gateway service's own env only,
  never in the agent's `.env`), and how to pick a provider (`OPTIMUS_LOCAL_GATEWAY_PROVIDER`).
  Lead with the OpenRouter/OpenAI path as the default quickstart, not Anthropic-native — that's the
  key most readers will actually have.
- Explicit security note: this service must never be bound beyond `127.0.0.1` / `localhost` without
  adding real TLS first — the loopback exemption above is only sound because traffic stays on one
  machine.

## Definition of Done

- [x] Loopback exemption in `config/gateway.py` — implemented (`4901b75`), tests green, no
      production-mode regression.
- [x] v1 gateway service unit tests and live process verification — implemented (`53cf8da`),
      superseded in shape (not deleted) by the items below.
- [x] OpenAI-compatible adapter (primary): request/response shaping per "Design Revision" above,
      unit tests using a fake upstream client — deterministic, no live tier needed.
- [x] Anthropic-native adapter demoted to secondary, selected via `OPTIMUS_LOCAL_GATEWAY_PROVIDER`
      — existing `UrllibAnthropicClient` and its tests stay, wired behind the provider selector
      instead of being the only path.
- [x] Provider-scoped model-id mapping + direct passthrough (Scope item 4) with unit tests for both
      alias resolution and passthrough.
- [x] Per-provider pricing table (Scope item 3) with unit tests, including the "unknown model fails
      loudly" case.
- [x] Live smoke test defaults to whichever provider/key the operator actually configures — not
      hardcoded to Anthropic — and still asserts a real response with `cost_usd > 0` (code complete;
      requires operator key to execute).
- [x] README runbook updated: OpenRouter/OpenAI-led quickstart, `OPTIMUS_LOCAL_GATEWAY_PROVIDER`
      documented, `curl` smoke example updated.
- [ ] Plan 9.6 L5 tests (already implemented, unaffected — the `/v1/responses` contract to the agent
      doesn't change) re-run against this service for a genuine live result, with whichever provider
      the operator has a real key for. L6 (spawned-agent e2e) follows on the same basis.

## Sequencing

This lands before Plan 9.6 L5/L6 are considered "real." L1–L4 and L9 (Redis-only tiers) are
unaffected and already stand on their own live evidence — this plan does not touch them.

**Note on branch state:** the OpenAI-compatible-primary revision refactors work already committed at
`53cf8da` on `agent/cursor/local-optimus-gateway`. Don't delete that commit's tests/adapter outright
— demote the Anthropic path to secondary and add the new adapter alongside it, so the existing
coverage for the Anthropic path is preserved as one of two supported providers, not lost.
