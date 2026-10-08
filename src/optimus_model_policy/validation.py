"""Structural validation per explicitly assigned role, and price ordering (ADR-004 decisions 3 and 8).

Eligibility is operator configuration plus structural facts, never a task test. A model is eligible
for a role only when it is explicitly assigned to that role and every hard requirement holds:

* implementer roles (easy/medium/complex/escalation): native tool support and the Optimus text
  planning grammar, which are distinct checks;
* every active role: a verified route of exact endpoint slugs with recorded quantizations, whose
  smallest window reaches the context ceiling and whose smallest max output covers the role's
  reserve; a verified route estimator; a set reserve; and an explicit, supported reasoning level that
  the upstream request can express (none at all only when the route has no reasoning levels);
* summarizer: a passing ``context-summary-v1`` receipt for this exact route and reasoning setting;
* reviewer and classifier are dormant, so they are never eligible.

Eligible models are ordered by per-token price dominance (no dearer on both input and output, and
cheaper on one); an exact tie puts the China-origin model first. Crossed prices need a declared
role blend; without one the role's ordering is unresolved and nothing is eligible for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from functools import cmp_to_key

from optimus_model_policy.binding import WIRE_QUANTIZATIONS, WIRE_REASONING_EFFORTS
from optimus_model_policy.registry import (
    DORMANT_ROLES,
    IMPLEMENTER_ROLES,
    SUMMARY_FIXTURE_DIGEST,
    SUMMARY_FORMAT,
    SUMMARY_PROMPT_DIGEST,
    SUMMARY_VALIDATOR,
    ModelEntry,
    Origin,
    RegistrySnapshot,
    Role,
    reserve_class,
)

__all__ = ["ValidationIssue", "ordered_assignments", "select_eligible_models", "validate_registry"]

_ENDPOINT_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
"""An OpenRouter provider slug: lower-case segments joined by "/" (``deepinfra/fp8``)."""


@dataclass(frozen=True, slots=True, order=True)
class ValidationIssue:
    code: str
    detail: str
    model_id: str | None = None
    role: Role | None = None


def _sort_key(issue: ValidationIssue) -> tuple[str, str, str, str]:
    return (issue.code, issue.model_id or "", issue.role.value if issue.role else "", issue.detail)


def _model_role_issues(snapshot: RegistrySnapshot, model_id: str, entry: ModelEntry, role: Role) -> list[ValidationIssue]:
    policy = snapshot.policy
    issues: list[ValidationIssue] = []

    def issue(code: str, detail: str) -> None:
        issues.append(ValidationIssue(code=code, detail=detail, model_id=model_id, role=role))

    if role in IMPLEMENTER_ROLES:
        if not entry.capabilities.native_tools:
            issue("IMPLEMENTER_NEEDS_NATIVE_TOOLS", "implementer roles require documented native tool support")
        if not entry.capabilities.text_planning_grammar:
            issue("IMPLEMENTER_NEEDS_TEXT_GRAMMAR", "implementer roles require the Optimus text planning grammar")

    endpoints = entry.route.endpoints
    if any(not endpoint.verified for endpoint in endpoints):
        issue("ROUTE_UNVERIFIED", "every endpoint in the route allow-set must be verified")
    malformed = sorted({endpoint.provider for endpoint in endpoints if not _ENDPOINT_SLUG.fullmatch(endpoint.provider)})
    if malformed:
        issue("ROUTE_SLUG_MALFORMED", f"endpoint slugs {malformed} are not lower-case OpenRouter provider slugs")
    inexpressible = sorted(
        {endpoint.quantization for endpoint in endpoints if endpoint.quantization is not None and endpoint.quantization not in WIRE_QUANTIZATIONS}
    )
    if inexpressible:
        issue("ROUTE_QUANTIZATION_NOT_EXPRESSIBLE", f"quantizations {inexpressible} have no upstream filter value")
    base_slugs = sorted({endpoint.provider for endpoint in endpoints if "/" not in endpoint.provider})
    if base_slugs:
        # OpenRouter routes a base slug to every variant and region of that provider, so the request
        # could not be held to the approved endpoint; only an exact variant slug is expressible.
        issue("ROUTE_TARGET_NOT_EXACT", f"provider base slugs {base_slugs} also reach other variants; record exact endpoint slugs")
    slugs = [endpoint.provider for endpoint in endpoints]
    if len(set(slugs)) != len(slugs):
        issue("ROUTE_ENDPOINT_DUPLICATE", "an endpoint slug is listed more than once in the route")
    windows = [endpoint.context_window_tokens for endpoint in endpoints]
    outputs = [endpoint.max_output_tokens for endpoint in endpoints]
    if any(endpoint.quantization is None for endpoint in endpoints):
        # The Gateway constrains each request to the route's approved quantizations; an unrecorded
        # one cannot be constrained, so the route is not usable for any role.
        issue("ROUTE_QUANTIZATION_UNKNOWN", "every endpoint needs a recorded quantization")
    if any(value is None for value in windows + outputs):
        issue("ROUTE_FACT_UNKNOWN", "an endpoint has no recorded window or max output")
    else:
        if min(windows) < policy.context_ceiling_tokens:  # type: ignore[type-var]
            issue("ROUTE_WINDOW_BELOW_CEILING", f"smallest window {min(windows)} < ceiling {policy.context_ceiling_tokens}")  # type: ignore[type-var]
        reserve = policy.output_reserve_tokens.get(reserve_class(role))
        if reserve is not None and min(outputs) < reserve:  # type: ignore[type-var]
            issue("ROUTE_OUTPUT_BELOW_RESERVE", f"smallest max output {min(outputs)} < reserve {reserve}")  # type: ignore[type-var]

    estimator = policy.estimators.get(entry.route.estimator)
    if estimator is None:
        issue("ESTIMATOR_UNKNOWN", f"route estimator {entry.route.estimator!r} is not defined")
    elif not estimator.verified:
        issue("ESTIMATOR_UNVERIFIED", f"route estimator {entry.route.estimator!r} is not verified")

    if entry.default_reasoning is not None and entry.default_reasoning not in entry.capabilities.reasoning_levels:
        issue("UNSUPPORTED_REASONING", f"default reasoning {entry.default_reasoning!r} is not supported on this route")
    if entry.default_reasoning is None and entry.capabilities.reasoning_levels:
        # The provider's own default is not an approved setting: a model with reasoning controls must
        # name the level every request will carry.
        issue("REASONING_UNSET", "this route has reasoning levels, so the approved reasoning setting must be explicit")
    if entry.default_reasoning is not None and entry.default_reasoning not in WIRE_REASONING_EFFORTS:
        issue("REASONING_NOT_EXPRESSIBLE", f"reasoning {entry.default_reasoning!r} has no upstream request form")

    if role is Role.SUMMARIZER and not any(
        # The exact registry key that owns the entry: a receipt never carries over to another model
        # that shares its route and settings (Codex CP2 R3).
        receipt.model_id == model_id
        and receipt.format == SUMMARY_FORMAT
        and receipt.providers == entry.route.providers
        and receipt.quantizations == entry.route.quantizations
        and receipt.reasoning == entry.default_reasoning
        and receipt.fixture_digest == SUMMARY_FIXTURE_DIGEST
        and receipt.prompt_digest == SUMMARY_PROMPT_DIGEST
        and receipt.validator == SUMMARY_VALIDATOR
        for receipt in entry.summary_receipts
    ):
        issue(
            "SUMMARIZER_UNQUALIFIED",
            f"no passing {SUMMARY_FORMAT} receipt for this model, route, reasoning setting, fixture, prompt and validator",
        )
    return issues


def _blend(entry: ModelEntry, weight: Decimal) -> Decimal:
    return weight * entry.prices.input_usd_per_million + (1 - weight) * entry.prices.output_usd_per_million


def _compare(a: tuple[str, ModelEntry], b: tuple[str, ModelEntry], weight: Decimal | None) -> int:
    (a_id, a_entry), (b_id, b_entry) = a, b
    a_in, a_out = a_entry.prices.input_usd_per_million, a_entry.prices.output_usd_per_million
    b_in, b_out = b_entry.prices.input_usd_per_million, b_entry.prices.output_usd_per_million
    if (a_in, a_out) != (b_in, b_out):
        if a_in <= b_in and a_out <= b_out:
            return -1
        if b_in <= a_in and b_out <= a_out:
            return 1
        if weight is not None and _blend(a_entry, weight) != _blend(b_entry, weight):
            return -1 if _blend(a_entry, weight) < _blend(b_entry, weight) else 1
    a_china, b_china = a_entry.origin is Origin.CHINA, b_entry.origin is Origin.CHINA
    if a_china != b_china:
        return -1 if a_china else 1
    return (a_id > b_id) - (a_id < b_id)


def _crossed_unresolved(snapshot: RegistrySnapshot, role: Role, model_ids: tuple[str, ...]) -> bool:
    if role in snapshot.policy.role_price_blends:
        return False
    entries = [snapshot.policy.models[model_id] for model_id in model_ids]
    for index, a in enumerate(entries):
        for b in entries[index + 1 :]:
            a_in, a_out = a.prices.input_usd_per_million, a.prices.output_usd_per_million
            b_in, b_out = b.prices.input_usd_per_million, b.prices.output_usd_per_million
            if (a_in < b_in and a_out > b_out) or (a_in > b_in and a_out < b_out):
                return True
    return False


def _known_assignments(snapshot: RegistrySnapshot, role: Role) -> tuple[str, ...]:
    return tuple(model_id for model_id in snapshot.policy.roles.get(role, ()) if model_id in snapshot.policy.models)


def ordered_assignments(snapshot: RegistrySnapshot, role: Role) -> tuple[str, ...]:
    """The role's known assigned models in price order, whether or not each is currently eligible.

    When crossed prices have no declared blend the ordering is unresolved, so the configured order
    is returned unchanged (and :func:`select_eligible_models` returns nothing for the role)."""
    assigned = _known_assignments(snapshot, role)
    if _crossed_unresolved(snapshot, role, assigned):
        return assigned
    weight = snapshot.policy.role_price_blends.get(role)
    pairs = [(model_id, snapshot.policy.models[model_id]) for model_id in assigned]
    return tuple(model_id for model_id, _ in sorted(pairs, key=cmp_to_key(lambda a, b: _compare(a, b, weight))))


def validate_registry(snapshot: RegistrySnapshot) -> tuple[ValidationIssue, ...]:
    """Every structural problem in the snapshot, sorted deterministically."""
    policy = snapshot.policy
    issues: list[ValidationIssue] = []

    for role, model_ids in policy.roles.items():
        if role is Role.CLASSIFIER and model_ids:
            issues.append(ValidationIssue("ROLE_DORMANT", "classifier assignments await accepted ADR-007", role=role))
        seen: set[str] = set()
        for model_id in model_ids:
            if model_id in seen:
                issues.append(ValidationIssue("DUPLICATE_ASSIGNMENT", "listed twice in one role", model_id, role))
            seen.add(model_id)
            if model_id not in policy.models:
                issues.append(ValidationIssue("UNKNOWN_MODEL_IN_ROLE", "assigned but not listed in models", model_id, role))
        if role in DORMANT_ROLES:
            continue
        if reserve_class(role) not in policy.output_reserve_tokens and model_ids:
            issues.append(ValidationIssue("RESERVE_UNSET", f"no {reserve_class(role)} output reserve (D3, measured in CP4)", role=role))
        known = _known_assignments(snapshot, role)
        if _crossed_unresolved(snapshot, role, known):
            issues.append(ValidationIssue("CROSSED_PRICES_UNRESOLVED", "crossed prices need a declared role blend", role=role))
        for model_id in dict.fromkeys(known):
            issues.extend(_model_role_issues(snapshot, model_id, policy.models[model_id], role))

    for tier in sorted({entry.tier for entry in policy.models.values()}):
        origins = {entry.origin for entry in policy.models.values() if entry.tier is tier}
        for origin in (Origin.CHINA, Origin.NON_CHINA):
            if origin not in origins:
                issues.append(ValidationIssue("ORIGIN_INVENTORY", f"tier {tier.value} has no {origin.value} model"))

    return tuple(sorted(issues, key=_sort_key))


def select_eligible_models(snapshot: RegistrySnapshot, role: Role) -> tuple[str, ...]:
    """The role's eligible models, cheapest first. Empty for dormant or unresolved roles."""
    if role in DORMANT_ROLES:
        return ()
    issues = validate_registry(snapshot)
    if any(issue.role is role and issue.model_id is None for issue in issues):
        return ()  # a role-wide problem: no reserve, or crossed prices without a blend
    blocked = {issue.model_id for issue in issues if issue.role is role and issue.model_id is not None}
    return tuple(model_id for model_id in ordered_assignments(snapshot, role) if model_id not in blocked)
