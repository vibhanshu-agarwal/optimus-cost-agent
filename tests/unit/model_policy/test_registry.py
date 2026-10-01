"""Plan 12.2 Task 4: the curated model registry (ADR-004) — strict YAML, typed snapshot, roles.

The registry is reviewed YAML plus an optional operator override. The loader rejects YAML features
that could make two readers disagree (duplicate keys, anchors, aliases, merge keys, custom tags);
the typed schema rejects unknown fields; the structural validator checks each explicitly assigned
role; eligible models are ordered by per-token price dominance with China first on a tie.
"""

from __future__ import annotations

import textwrap
from importlib import resources
from pathlib import Path

import pytest

from optimus_model_policy import (
    RegistryError,
    Role,
    load_registry,
    ordered_assignments,
    select_eligible_models,
    validate_registry,
)

# --- A small, fully specified fixture policy -------------------------------------------------------

_FIXTURE = textwrap.dedent(
    """\
    schema_version: 1
    policy_version: "fixture-1"
    fixture: true
    context_ceiling_tokens: 262144
    output_reserve_tokens:
      implementer: 16384
      summarizer: 4096
      reviewer: 8192
    estimators:
      fixture-bytes:
        method: utf8-bytes-ratio
        tokens_per_byte: "0.5"
        per_message_tokens: 8
        fixed_tokens: 64
        verified: true
    role_price_blends: {}
    alerts:
      thresholds_usd: []
    models:
      cn/alpha:
        origin: china
        tier: cheap
        prices: {input_usd_per_million: "0.10", output_usd_per_million: "0.40"}
        data_use: {provider_may_train_on_inputs: "no", disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [low, high]}
        default_reasoning: high
        route:
          estimator: fixture-bytes
          endpoints:
            - {provider: alpha-cloud, quantization: fp8, context_window_tokens: 300000, max_output_tokens: 32768, verified: true}
      us/beta:
        origin: non-china
        tier: cheap
        prices: {input_usd_per_million: "0.20", output_usd_per_million: "0.80"}
        data_use: {provider_may_train_on_inputs: "no", disclosure: none}
        capabilities: {native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [low, high]}
        default_reasoning: low
        route:
          estimator: fixture-bytes
          endpoints:
            - {provider: beta-ai, quantization: bf16, context_window_tokens: 262144, max_output_tokens: 65536, verified: true}
    roles:
      medium: [us/beta, cn/alpha]
    """
)


def _edited(old: str, new: str) -> str:
    """The fixture with ``old`` replaced once; fails loudly if ``old`` does not occur, so a test can
    never pass on an edit that silently matched nothing."""
    assert old in _FIXTURE, f"fixture edit anchor not found: {old!r}"
    return _FIXTURE.replace(old, new, 1)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def _issues(snapshot, code: str) -> list:
    return [issue for issue in validate_registry(snapshot) if issue.code == code]


def test_the_fixture_policy_loads_and_orders_by_price_dominance(tmp_path: Path) -> None:
    snapshot = load_registry(_write(tmp_path, "defaults.yaml", _FIXTURE), None)

    assert validate_registry(snapshot) == ()
    # Assigned in the opposite order; dominance (no dearer on both, cheaper on one) puts alpha first.
    assert ordered_assignments(snapshot, Role.MEDIUM) == ("cn/alpha", "us/beta")
    assert select_eligible_models(snapshot, Role.MEDIUM) == ("cn/alpha", "us/beta")
    assert len(snapshot.effective_hash) == 64


# --- Strict YAML ---------------------------------------------------------------------------------

_SYNTAX_REJECTIONS = {
    "top-level duplicate key": "schema_version: 1\nschema_version: 1\n",
    "nested duplicate key": "models:\n  a:\n    origin: china\n    origin: china\n",
    "anchor": "x: &anchor 1\n",
    "alias": "x: &a 1\ny: *a\n",
    "merge key": "base: {a: 1}\nother:\n  <<: {a: 2}\n",
    "quoted merge key": "other:\n  '<<': {a: 2}\n",
    "python tag": "x: !!python/object/apply:os.system ['echo']\n",
    "custom tag": "x: !custom 1\n",
    "binary tag": "x: !!binary aGVsbG8=\n",
    "timestamp scalar": "x: 2026-10-02\n",
    "non-string key": "1: one\n",
    "null key": "~: one\n",
}


@pytest.mark.parametrize("label", sorted(_SYNTAX_REJECTIONS))
def test_the_loader_rejects_ambiguous_or_executable_yaml(tmp_path: Path, label: str) -> None:
    with pytest.raises(RegistryError) as rejected:
        load_registry(_write(tmp_path, "defaults.yaml", _SYNTAX_REJECTIONS[label]), None)
    assert rejected.value.code == "YAML_REJECTED", label


def test_anchor_like_characters_inside_ordinary_text_are_fine(tmp_path: Path) -> None:
    text = _edited(
        'policy_version: "fixture-1"', 'policy_version: "fixture-1 & not *an* alias, <<: or !tag"'
    )
    snapshot = load_registry(_write(tmp_path, "defaults.yaml", text), None)
    assert snapshot.policy.policy_version == "fixture-1 & not *an* alias, <<: or !tag"


# --- Typed schema --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("fixture: true\n", "fixture: true\nunexpected_field: 1\n"),
        ("    tier: cheap\n", "    tier: cheap\n    surprise: yes\n"),
        ('input_usd_per_million: "0.10"', 'input_usd_per_million: "-0.10"'),
        ('input_usd_per_million: "0.10"', 'input_usd_per_million: ".inf"'),
        ('input_usd_per_million: "0.10"', 'input_usd_per_million: "NaN"'),
        ("    origin: china\n", "    origin: atlantis\n"),
        ("    data_use: {provider_may_train_on_inputs: \"no\", disclosure: none}\n", ""),
        ("      estimator: fixture-bytes\n      endpoints:\n        - {provider: alpha-cloud", "      endpoints:\n        - {provider: alpha-cloud"),
        ("context_ceiling_tokens: 262144\n", "context_ceiling_tokens: true\n"),
        ("context_ceiling_tokens: 262144\n", "context_ceiling_tokens: 262144.0\n"),
        ("context_ceiling_tokens: 262144\n", 'context_ceiling_tokens: "262144"\n'),
        ("per_message_tokens: 8\n", "per_message_tokens: 8.0\n"),
        ("schema_version: 1\n", "schema_version: true\n"),
        ("fixture: true\n", 'fixture: "true"\n'),
        ("max_output_tokens: 32768, verified: true}", "max_output_tokens: 32768, verified: 1}"),
        ("  us/beta:\n", '  "us/beta ":\n'),
        ("max_output_tokens: 32768, verified: true}", "max_output_tokens: 32768.0, verified: true}"),
        ("context_window_tokens: 300000,", 'context_window_tokens: "300000",'),
    ],
    ids=[
        "unknown-top-field", "unknown-model-field", "negative-price", "infinite-price", "nan-price", "unknown-origin",
        "missing-data-use", "missing-route-estimator", "bool-count", "float-count", "quoted-count", "float-framing",
        "bool-schema-version", "quoted-flag", "integer-flag", "whitespace-model-id", "float-max-output", "quoted-window",
    ],
)
def test_the_schema_rejects_unknown_fields_bad_numbers_and_missing_facts(tmp_path: Path, old: str, new: str) -> None:
    with pytest.raises(RegistryError) as rejected:
        load_registry(_write(tmp_path, "defaults.yaml", _edited(old, new)), None)
    assert rejected.value.code == "SCHEMA_INVALID"


def test_model_ids_that_differ_only_by_case_are_ambiguous(tmp_path: Path) -> None:
    text = _edited("  us/beta:\n", "  CN/Alpha:\n").replace("[us/beta, cn/alpha]", "[cn/alpha]")
    with pytest.raises(RegistryError) as rejected:
        load_registry(_write(tmp_path, "defaults.yaml", text), None)
    assert rejected.value.code == "SCHEMA_INVALID"


# --- Override combination and hashing ------------------------------------------------------------


def test_override_maps_combine_by_key_and_lists_replace(tmp_path: Path) -> None:
    defaults = _write(tmp_path, "defaults.yaml", _FIXTURE)
    override = _write(
        tmp_path,
        "override.yaml",
        """\
        models:
          cn/alpha:
            prices: {output_usd_per_million: "0.30"}
        roles:
          medium: [us/beta]
        """,
    )
    snapshot = load_registry(defaults, override)

    alpha = snapshot.policy.models["cn/alpha"]
    assert str(alpha.prices.input_usd_per_million) == "0.10", "an untouched map key is kept"
    assert str(alpha.prices.output_usd_per_million) == "0.30", "an overridden map key is replaced"
    assert snapshot.policy.roles[Role.MEDIUM] == ("us/beta",), "a list replaces rather than appends"
    assert [name for name, _ in snapshot.input_hashes] == ["defaults.yaml", "override.yaml"]


def test_the_effective_hash_ignores_formatting_but_tracks_content(tmp_path: Path) -> None:
    first = load_registry(_write(tmp_path, "a.yaml", _FIXTURE), None)
    reformatted = "# a comment\n" + _edited("tier: cheap", "tier:    cheap")
    second = load_registry(_write(tmp_path, "b.yaml", reformatted), None)
    changed = load_registry(_write(tmp_path, "c.yaml", _edited('"0.40"', '"0.41"')), None)

    assert first.effective_hash == second.effective_hash
    assert first.input_hashes != second.input_hashes
    assert changed.effective_hash != first.effective_hash


def test_numbers_hash_by_value_not_by_their_text(tmp_path: Path) -> None:
    """``0.10``, ``0.1`` and ``1E-1`` are one price, so they are one effective snapshot."""
    first = load_registry(_write(tmp_path, "a.yaml", _FIXTURE), None)
    for index, text in enumerate(('"0.1"', '"1E-1"', '"0.100"')):
        same = load_registry(_write(tmp_path, f"b{index}.yaml", _edited('"0.10"', text)), None)
        assert same.effective_hash == first.effective_hash, text


def test_an_override_is_validated_like_the_defaults(tmp_path: Path) -> None:
    defaults = _write(tmp_path, "defaults.yaml", _FIXTURE)
    override = _write(tmp_path, "override.yaml", "models:\n  cn/alpha:\n    tier: cheap\n    tier: review\n")
    with pytest.raises(RegistryError) as rejected:
        load_registry(defaults, override)
    assert rejected.value.code == "YAML_REJECTED"


# --- Structural validation per explicitly assigned role -------------------------------------------


def test_an_implementer_needs_native_tools_and_the_text_grammar(tmp_path: Path) -> None:
    text = _edited(
        "{native_tools: true, text_planning_grammar: true, structured_output: true, reasoning_levels: [low, high]}\n    default_reasoning: high",
        "{native_tools: false, text_planning_grammar: true, structured_output: true, reasoning_levels: [low, high]}\n    default_reasoning: high",
    )
    snapshot = load_registry(_write(tmp_path, "defaults.yaml", text), None)
    assert [(i.model_id, i.role) for i in _issues(snapshot, "IMPLEMENTER_NEEDS_NATIVE_TOOLS")] == [("cn/alpha", Role.MEDIUM)]
    assert select_eligible_models(snapshot, Role.MEDIUM) == ("us/beta",)


def test_a_route_below_the_ceiling_or_reserve_is_not_eligible(tmp_path: Path) -> None:
    narrow = _edited("context_window_tokens: 262144, max_output_tokens: 65536", "context_window_tokens: 200000, max_output_tokens: 65536")
    short = _edited("context_window_tokens: 300000, max_output_tokens: 32768", "context_window_tokens: 300000, max_output_tokens: 8192")
    narrow_snapshot = load_registry(_write(tmp_path, "narrow.yaml", narrow), None)
    short_snapshot = load_registry(_write(tmp_path, "short.yaml", short), None)

    assert [i.model_id for i in _issues(narrow_snapshot, "ROUTE_WINDOW_BELOW_CEILING")] == ["us/beta"]
    assert [i.model_id for i in _issues(short_snapshot, "ROUTE_OUTPUT_BELOW_RESERVE")] == ["cn/alpha"]
    assert select_eligible_models(narrow_snapshot, Role.MEDIUM) == ("cn/alpha",)


def test_unverified_routes_and_estimators_are_not_eligible(tmp_path: Path) -> None:
    unverified_route = _edited("max_output_tokens: 32768, verified: true", "max_output_tokens: 32768, verified: false")
    unverified_estimator = _edited("    verified: true\nrole_price_blends", "    verified: false\nrole_price_blends")
    a = load_registry(_write(tmp_path, "a.yaml", unverified_route), None)
    b = load_registry(_write(tmp_path, "b.yaml", unverified_estimator), None)

    assert [i.model_id for i in _issues(a, "ROUTE_UNVERIFIED")] == ["cn/alpha"]
    assert {i.model_id for i in _issues(b, "ESTIMATOR_UNVERIFIED")} == {"cn/alpha", "us/beta"}
    assert select_eligible_models(b, Role.MEDIUM) == ()


def test_an_endpoint_without_a_recorded_quantization_is_not_eligible(tmp_path: Path) -> None:
    """The Gateway constrains requests to the approved quantizations, so the host must not select a
    route it cannot constrain (Fable CP1 review, M1)."""
    snapshot = load_registry(_write(tmp_path, "a.yaml", _edited("quantization: fp8", "quantization: null")), None)
    assert [i.model_id for i in _issues(snapshot, "ROUTE_QUANTIZATION_UNKNOWN")] == ["cn/alpha"]
    assert select_eligible_models(snapshot, Role.MEDIUM) == ("us/beta",)


def test_unsupported_reasoning_is_reported(tmp_path: Path) -> None:
    text = _edited("default_reasoning: low", "default_reasoning: max")
    snapshot = load_registry(_write(tmp_path, "defaults.yaml", text), None)
    assert [i.model_id for i in _issues(snapshot, "UNSUPPORTED_REASONING")] == ["us/beta"]


def test_a_summarizer_without_a_receipt_is_not_eligible(tmp_path: Path) -> None:
    text = _edited("roles:\n  medium: [us/beta, cn/alpha]\n", "roles:\n  medium: [us/beta, cn/alpha]\n  summarizer: [cn/alpha]\n")
    snapshot = load_registry(_write(tmp_path, "defaults.yaml", text), None)
    assert [(i.model_id, i.role) for i in _issues(snapshot, "SUMMARIZER_UNQUALIFIED")] == [("cn/alpha", Role.SUMMARIZER)]
    assert select_eligible_models(snapshot, Role.SUMMARIZER) == ()
    assert ordered_assignments(snapshot, Role.SUMMARIZER) == ("cn/alpha",)


def test_dormant_roles_are_never_eligible(tmp_path: Path) -> None:
    text = _edited("roles:\n  medium: [us/beta, cn/alpha]\n", "roles:\n  medium: [us/beta, cn/alpha]\n  reviewer: [us/beta]\n  classifier: [cn/alpha]\n")
    snapshot = load_registry(_write(tmp_path, "defaults.yaml", text), None)
    assert select_eligible_models(snapshot, Role.REVIEWER) == ()
    assert select_eligible_models(snapshot, Role.CLASSIFIER) == ()
    assert {i.role for i in _issues(snapshot, "ROLE_DORMANT")} == {Role.CLASSIFIER}


def test_an_assignment_to_an_unknown_model_is_reported(tmp_path: Path) -> None:
    text = _edited("[us/beta, cn/alpha]", "[us/beta, cn/alpha, xx/ghost]")
    snapshot = load_registry(_write(tmp_path, "defaults.yaml", text), None)
    assert [i.model_id for i in _issues(snapshot, "UNKNOWN_MODEL_IN_ROLE")] == ["xx/ghost"]


def test_each_tier_must_list_a_china_and_a_non_china_model(tmp_path: Path) -> None:
    text = _edited("    origin: non-china\n", "    origin: china\n")
    snapshot = load_registry(_write(tmp_path, "defaults.yaml", text), None)
    assert [i.detail for i in _issues(snapshot, "ORIGIN_INVENTORY")] == ["tier cheap has no non-china model"]


# --- Crossed prices and ties ---------------------------------------------------------------------


def test_crossed_prices_need_a_declared_role_blend(tmp_path: Path) -> None:
    crossed = _edited('output_usd_per_million: "0.80"', 'output_usd_per_million: "0.30"')
    snapshot = load_registry(_write(tmp_path, "crossed.yaml", crossed), None)
    assert [i.role for i in _issues(snapshot, "CROSSED_PRICES_UNRESOLVED")] == [Role.MEDIUM]
    assert select_eligible_models(snapshot, Role.MEDIUM) == ()

    # alpha 0.10/0.40, beta 0.20/0.30. With 25% input weight: alpha 0.325, beta 0.275 -> beta first.
    blended = crossed.replace("role_price_blends: {}", 'role_price_blends:\n  medium: "0.25"')
    blended_snapshot = load_registry(_write(tmp_path, "blended.yaml", blended), None)
    assert validate_registry(blended_snapshot) == ()
    assert select_eligible_models(blended_snapshot, Role.MEDIUM) == ("us/beta", "cn/alpha")


def test_an_exact_price_tie_prefers_the_china_origin(tmp_path: Path) -> None:
    tied = _edited('{input_usd_per_million: "0.20", output_usd_per_million: "0.80"}',
                            '{input_usd_per_million: "0.10", output_usd_per_million: "0.40"}')
    snapshot = load_registry(_write(tmp_path, "tied.yaml", tied), None)
    assert select_eligible_models(snapshot, Role.MEDIUM) == ("cn/alpha", "us/beta")


# --- The shipped defaults (ADR-004 decision 8; spec 9.2) ------------------------------------------


def _shipped():
    path = resources.files("optimus_model_policy").joinpath("defaults.yaml")
    with resources.as_file(path) as defaults:
        return load_registry(defaults, None)


def test_the_shipped_defaults_keep_the_frozen_role_order() -> None:
    snapshot = _shipped()
    assert snapshot.policy.fixture is False
    assert ordered_assignments(snapshot, Role.MEDIUM) == (
        "meta/muse-spark-1.3-contributor",
        "deepseek/deepseek-v4.1-flash",
        "google/gemini-3.8-flash",
        "meta/muse-spark-1.3",
    )
    assert ordered_assignments(snapshot, Role.COMPLEX) == ("google/gemini-3.8-flash", "z-ai/glm-5.3")
    assert ordered_assignments(snapshot, Role.ESCALATION) == ("google/gemini-3.8-flash", "z-ai/glm-5.3")
    assert ordered_assignments(snapshot, Role.EASY) == ("openai/gpt-6-luna",)
    assert ordered_assignments(snapshot, Role.SUMMARIZER) == ("qwen/qwen3.7-flash", "openai/gpt-6-luna")
    assert ordered_assignments(snapshot, Role.REVIEWER) == ("anthropic/claude-sonnet-5.5", "moonshotai/kimi-k3")


def test_the_shipped_defaults_list_without_granting_roles() -> None:
    snapshot = _shipped()
    assigned = {model for models in snapshot.policy.roles.values() for model in models}
    assert "z-ai/glm-5.3-flash" in snapshot.policy.models, "GLM 5.3 Flash stays listed for re-enabling"
    assert "z-ai/glm-5.3-flash" not in assigned, "GLM 5.3 Flash has no role"
    coding = {Role.EASY, Role.MEDIUM, Role.COMPLEX, Role.ESCALATION}
    assert all("qwen/qwen3.7-flash" not in snapshot.policy.roles.get(role, ()) for role in coding)
    assert not [m for m in snapshot.policy.models if "haiku" in m], "Haiku is removed (ADR-003)"
    assert _issues(snapshot, "ORIGIN_INVENTORY") == []


def test_the_shipped_defaults_admit_nothing_until_facts_are_verified() -> None:
    """Catalog facts from 2026-09-30 are recorded but unverified, and no route estimator or output
    reserve has been measured (D1-D3, CP4). Every role is therefore empty, by design."""
    snapshot = _shipped()
    for role in Role:
        assert select_eligible_models(snapshot, role) == (), role
    codes = {issue.code for issue in validate_registry(snapshot)}
    assert {"ROUTE_UNVERIFIED", "ESTIMATOR_UNKNOWN", "RESERVE_UNSET"} <= codes


def test_contributor_cannot_run_at_standard_only_max_reasoning() -> None:
    contributor = _shipped().policy.models["meta/muse-spark-1.3-contributor"]
    assert "max" not in contributor.capabilities.reasoning_levels
    assert contributor.data_use.disclosure == "contributor"
