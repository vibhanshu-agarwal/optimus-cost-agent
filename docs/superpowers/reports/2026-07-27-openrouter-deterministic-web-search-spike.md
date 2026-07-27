# OpenRouter Deterministic Web Search Spike

**Status:** Approved 2026-07-27 as architecture-review evidence; not production acceptance
**Run timestamp:** 2026-07-27T14:36:05Z
**Design note:** `docs/superpowers/specs/2026-07-27-local-gateway-aggregator-architecture-design.md`
**Credential handling:** real operator-approved OpenRouter credential; read from the owner-protected
Cursor worktree `.env.gateway`; never copied, printed, or persisted in this worktree

## 1. Scope and fixed configuration

This spike answered only the four operator-approved questions. It did not compare models, providers,
or search engines.

| Setting | Measured run value |
|---|---|
| Endpoint | `https://openrouter.ai/api/v1/chat/completions` |
| Model | `google/gemini-2.5-flash-lite` |
| Search mechanism | deterministic `plugins: [{"id": "web", ...}]` |
| Engine | default; `engine` omitted |
| `max_tokens` | 16 |
| `max_results` | 3 |
| Search requests in successful run | 3 |
| Extract implementation | Python standard-library HTTPS fetch + `HTMLParser` |

Each search request set `temperature=0`. The baseline query had no domain filter. The policy probe
used the same `pathlib.Path.read_text` query first with
`include_domains=["docs.python.org"]`, then with
`exclude_domains=["docs.python.org"]`.

## 2. Result summary

| Question | Result | Measured evidence |
|---|---|---|
| Do annotations survive minimal output? | **Yes** | 3 annotations at `max_tokens=16`; completion stopped with `finish_reason="length"` after exactly 16 completion tokens |
| Does `include_domains` / `exclude_domains` enforce policy? | **Yes for this probe** | Include: 3/3 citations inside `docs.python.org`; exclude: 0/3 citations inside `docs.python.org`; zero violations in both directions |
| Is citation quality adequate? | **Yes for typed search evidence** | 9/9 citations had `url_citation` type, HTTPS URL, non-empty title, and non-empty extractive content; all 9 were query-relevant on manual title/URL review |
| Does direct fetch + HTML-to-text work? | **Yes** | HTTP 200; 270,008 bytes; 534.2 ms fetch; 55.3 ms parse; 60,077 text characters; 9,783 words |

The measured result supports the design's deterministic-search direction. It does not by itself
authorize Tavily removal or production implementation.

## 3. Annotation and citation measurements

### 3.1 Minimal-output probe

Query: current stable Python release.

| Metric | Value |
|---|---:|
| HTTP status | 200 |
| Latency | 6,534.2 ms |
| Prompt tokens | 1,429 |
| Completion tokens | 16 |
| Total tokens | 1,445 |
| Assistant text | 56 characters |
| Annotations | 3 |
| Provider returned | Google |
| Provider-reported total cost | $0.0051493 |

The three citations were Python.org release/source/download pages. Their extractive content lengths
were 443, 4,381, and 200 characters. Annotations therefore remained available even though generation
hit the 16-token output cap.

### 3.2 Include-domain probe

| Metric | Value |
|---|---:|
| HTTP status | 200 |
| Latency | 7,422.9 ms |
| Prompt tokens | 1,346 |
| Completion tokens | 16 |
| Total tokens | 1,362 |
| Annotations | 3 |
| Allowed-domain citations | 3 |
| Off-allowlist citations | 0 |
| Provider-reported total cost | $0.0051410 |

Returned URLs:

- `https://docs.python.org/3/library/pathlib.html`
- `https://docs.python.org/3.10/library/pathlib.html`
- `https://docs.python.org/3.11/library/pathlib.html`

All three titles named the `pathlib` documentation and all three carried non-empty extractive
content (1,752, 995, and 942 characters).

### 3.3 Exclude-domain probe

| Metric | Value |
|---|---:|
| HTTP status | 200 |
| Latency | 7,249.0 ms |
| Prompt tokens | 1,784 |
| Completion tokens | 16 |
| Total tokens | 1,800 |
| Annotations | 3 |
| Excluded-domain citations | 0 |
| Alternative relevant citations | 3 |
| Provider-reported total cost | $0.0051848 |

The alternatives were two CPython GitHub source/documentation URLs and one independent Python
documentation mirror. This matters: the excluded domain was absent without collapsing the search
to zero results.

### 3.4 Aggregate successful-run accounting

| Metric | Value |
|---|---:|
| Search latency, sum | 21,206.1 ms |
| Search latency, mean | 7,068.7 ms |
| Prompt tokens | 4,559 |
| Completion tokens | 48 |
| Total tokens | 4,607 |
| Citations | 9 |
| Citation content, total | 13,930 characters |
| Citation content, median | 1,185 characters |
| Provider-reported total cost | **$0.0154751** |

The measured mean was **$0.0051584 per search**. Against the operator-supplied Tavily planning
baseline of approximately $0.008 per search, this run was approximately $0.0028416 (35.5%) cheaper
per search. The OpenRouter value is live provider-reported evidence; the Tavily value is a planning
comparison supplied during review, not a same-session Tavily measurement.

All nine annotations returned `start_index=0` and `end_index=0`. Production parsing must therefore
use the typed annotation objects and must not depend on meaningful inline character offsets.

Latency is a material tradeoff, not merely a metric: the 7,068.7 ms measured mean projects to
21.2-35.3 seconds for three to five sequential searches in one agent run. Review supplied a typical
Tavily comparison of roughly 1-2 seconds, but this spike did not independently measure Tavily.

OpenRouter reported inference sub-costs separately from total request cost. Across the three
successful requests, total request cost was about $0.00514-$0.00518 each; the total exceeded
inference sub-cost by approximately $0.005 per request, consistent with the documented default web
search charge. This statement is a measured arithmetic observation plus a documentation
cross-check—not a substitute for retaining the returned `usage.cost`.

## 4. Direct extract measurements

The adapter fetched the first approved include-domain result:
`https://docs.python.org/3/library/pathlib.html`.

| Metric | Value |
|---|---:|
| HTTP status | 200 |
| Final URL | unchanged |
| Content type | `text/html` |
| Response bytes | 270,008 |
| Fetch time | 534.2 ms |
| Parse time | 55.3 ms |
| Combined fetch + parse | 589.5 ms |
| Extracted characters | 60,077 |
| Extracted words | 9,783 |
| Parsed title | `pathlib — Object-oriented filesystem paths — Python 3.14.6 documentation` |

The standard-library parser removed script/style/noscript/SVG bodies and produced usable text with
no third-party package installation. This proves basic feasibility, not production SSRF, redirect,
encoding, content-type, or adversarial-HTML safety.

## 5. Failed boundary probe

The first attempt used a Wikipedia include-domain result and a 1,000,000-byte extract cap. The
bounded reader observed 1,000,001 bytes and failed closed before parsing. The harness originally
exited before printing the three search responses, so their exact provider-reported costs are not
available and are deliberately not estimated here.

This failure produced two useful design constraints:

1. extract limits must be explicit and tested against legitimate large pages; and
2. a production fetcher should stream/bound parsing or return a typed size-limit failure rather than
   silently truncating evidence.

The successful Python documentation fetch used a 2,000,000-byte cap but consumed only 270,008 bytes.

## 6. Interpretation

### Settled by the spike

- The deterministic plugin supplies standardized annotations independently of a complete assistant
  answer at a 16-token cap.
- For the tested domain and default-engine behavior, include and exclude filters produced zero
  policy violations.
- Annotation payloads are sufficient to construct the existing typed `WebSearchResult`.
- A direct bounded HTTPS fetch plus HTML-to-text conversion is viable without a separate extract
  vendor.
- OpenRouter's returned `usage.cost` captures material search cost that the current local model-rate
  table cannot reconstruct correctly.

### Still required in production

- Independently revalidate every returned URL; upstream filters are defense in depth, not the
  authorization boundary.
- Keep the harness, policy-signal, per-tool call cap, provenance registry, and `EvidenceLedger`.
- Fail closed on missing/malformed annotations or provider usage/cost.
- Add SSRF-safe resolution, redirect-by-redirect authorization, response streaming/limits, media
  validation, encoding policy, and adversarial HTML tests to extract.
- Pin a live release probe because the deterministic plugin is documented as deprecated.
- Repeat domain enforcement across the complete configured allowlist as a release/integration gate;
  one domain pair is sufficient for architecture feasibility, not universal provider conformance.

## 7. Pricing note

OpenRouter's official documentation currently lists Exa, Parallel, and Perplexity searches at
$0.005 per request, with additional result/provider-specific terms, while native search is provider
passthrough. The run intentionally omitted `engine` and made no pricing comparison. At this volume,
engine-price optimization is not architecture work; authoritative accounting is the
provider-returned `usage.cost`.

References:

- <https://openrouter.ai/docs/guides/features/plugins/web-search>
- <https://openrouter.ai/docs/cookbook/administration/usage-accounting>
- <https://openrouter.ai/google/gemini-2.5-flash-lite>

## 8. Reproduction artifact

`tools/run_openrouter_web_search_spike.py` is the sanitized experimental harness. It is not
production Gateway code and is not committed pending operator review.
