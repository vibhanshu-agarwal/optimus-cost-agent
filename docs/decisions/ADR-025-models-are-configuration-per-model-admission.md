# ADR-025: Models are configuration: per-model admission evidence in the registry, and the operator override

**Status:** Accepted. **Decision date:** 2026-10-25. **Decider:** the operator (verbatim below, source S11). The
mechanism details are Claude's, reviewed by Codex through three rounds of the Plan 12.4 v7 plan. Codex reviews the
implementation at Plan 12.4 Checkpoint A. **Publication:** editable in pre-merge review, frozen byte for byte on
first merge to `main`.

**Relationship:**
- **Partially supersedes [ADR-023](ADR-023-plan12-shipped-empirical-admission-and-default-planner.md):** its exception
  is no longer bound in code to one effective hash and one model. ADR-023's other decisions stand, including the
  default-planner rule and the controls it lists, and so does its residual (one refused reply stops that model's
  route for the launch).
- **Completes [ADR-004](ADR-004-curated-model-registry.md) option C** ("shipped defaults plus a validated operator
  override", chosen on 2026-09-30, never wired at launch).
- **ADR-007 stays Proposed and frozen.** Its acceptance is a separate record, after the Plan 12.4 pilot.

## Provenance

Source **S11**, indexed in the [decision log](README.md#rules-for-every-record): the app's export of the Claude
session for the Plan 12.4 Auto thread, session `bbe75542-b5c9-4de6-92d1-5e865d05eece`, at
`optimus-handoff\decisions-sources\2026-10-25-claude-session-plan12-4-v7-export.zip`; SHA-256
`F72D0A6D3C3BEA81DEA5EEAB57BA714E16D3F2A591B65F8BE3AB763EB0623504`. The archive is external raw provenance, never
an operating, test or release dependency.

**The options shown** are decisions N1 and N2 in the Plan 12.4 v7 plan,
`docs/superpowers/plans/2026-10-23-plan-12-4-auto-mode_v7.md`.

**Operator, verbatim (2026-10-25):**

> "What I wanted was the tiers to remain the same and we choose from among each tier on a given set of attributes. Every time we add a model why do we need a new plan? This is one thing that is a given that will change frequently"

> "Approved: Plan 12.4 v7 (r3, 0cb60e50), with N1(a) wire the operator override and N2(a) accept the per-entry admission policy and its first-call risk. Prepare the filing."

**The earlier ruling it restates (2026-09-30, ADR-004):** "Model selection will change throughout the life of the
project and should be configurable, so tests are not needed just to check tasks".

## Options and trade-offs

| Decision | Options weighed | Chosen, and why |
|---|---|---|
| N2, where admission evidence lives | (a) a block on each model's registry entry, approved with the effective hash; (b) one code-pinned exception per model, as ADR-023 did | **(a).** Under (b), any registry change (a new model, a price) changes the whole-registry hash, so the code pin breaks and every model change needs a code PR. Under (a), the evidence travels with the model, and the operator's approval of the effective hash stays the gate |
| N1, how the operator changes models without a release | (a) wire ADR-004's operator override at a fixed, trusted path, applied only after the operator approves the resulting hash; (b) shipped YAML only, a release per change | **(a).** It is the option ADR-004 chose. Without it, every model change waits for a PR and a release |

## Decision, paraphrased

- **The tiers are fixed; models are configuration.** Within each role, the cheapest eligible model is chosen by the
  existing per-token price rule (ADR-004). Adding, removing or re-pricing a model is a YAML change and an approval
  of the new effective hash, never a plan or a code change. There are no per-model task-quality tests; the
  summarizer's quality check (ADR-006) is the one exception kept.
- **Admission evidence is per model.** A model entry's `admission` block has two independent parts:
  - `empirical_estimate`: the entry's estimator may be unverified. The part records its evidence, assumptions and
    limitations;
  - `provider_family`: the route may use a provider's base slug. The part records the provider name every reply's
    router metadata must report, its evidence and its limitations.
  Using one part never relaxes the other's checks.
- **A conservative default estimator ships:** `conservative-utf8`, 1 token per UTF-8 byte of message and tool text,
  16 per message, 256 fixed, `verified: false`. Any model may name it. It is an empirical estimate, not a proven
  bound: it assumes text-only input and a tokenizer that does not expand text past one token per byte, and it does
  not prove that provider framing fits the allowances. A measured estimator, when one exists, replaces it.
- **The per-reply checks** apply to every model admitted with either part: the usage and finish checks, one router
  attempt and no pipeline stage; `empirical_estimate` adds billed input at most the estimate; `provider_family`
  adds the reported provider's equality with the recorded one.
- **A failed check stops that model only**, for the rest of the Gateway's life.
- **The operator override** is one file at a fixed path resolved through the trusted operator-path machinery. The
  launch gate and the Gateway compose it independently over the shipped defaults (and over the Auto overlay in the
  Auto composition). It is enforced only after the operator approves the resulting effective hash.
  `optimus-trust run-gateway` signs only a registry hash that a valid launch approval for the workspace already
  binds. Test profiles never read the override.

## The residual risk the operator accepted

A model admitted on an empirical estimate can make a first call that exceeds its estimate, or is charged, before the
per-reply check stops its later calls. Unknown-cost handling is unchanged.

## Authority boundary

- **Accepted by the operator:** N1(a) and N2(a), as quoted.
- **Agent detail, reviewed by Codex:** the block's fields, the estimator's values, the per-part checks and the
  per-model stop.
- **Not decided here:** which models are admitted (that is configuration), selection filters beyond price and origin
  (#398), and Auto's classifier (ADR-007).
- **Implementation** was released by the operator on 2026-10-25 for Plan 12.4. This record grants no merge, paid
  call or GitHub write.
