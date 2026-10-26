"""Plan 12.4 v7 Design 2: the Auto overlay's first inputs, as data.

Composed over the shipped defaults by the ``auto`` composition only (A5(a)). Gemini 3.8 Flash fills medium, complex
and escalation; Luna leads easy on price, with Haiku next; Haiku stays the summarizer. Both route to one exact
endpoint from the free 2026-10-25 catalogue read, on the conservative empirical estimator.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from optimus_model_policy import Role, select_eligible_models, validate_registry
from optimus_model_policy.binding import packaged_defaults, trusted_snapshot
from optimus_model_policy.experimental import experimental_route
from optimus_model_policy.registry import RegistrySnapshot, load_registry

GEMINI, LUNA, HAIKU = "google/gemini-3.8-flash", "openai/gpt-6-luna", "anthropic/claude-haiku-5.5"
JEV = "typesafe/jev-1.14"


def _auto() -> RegistrySnapshot:
    with resources.as_file(resources.files("optimus_model_policy").joinpath("auto_overlay.yaml")) as overlay:
        return load_registry(packaged_defaults(), overlay)


def test_each_tier_gets_its_first_inputs() -> None:
    snapshot = _auto()
    assert select_eligible_models(snapshot, Role.EASY) == (LUNA, HAIKU)
    for role in (Role.MEDIUM, Role.COMPLEX, Role.ESCALATION):
        assert select_eligible_models(snapshot, role) == (GEMINI,)
    assert select_eligible_models(snapshot, Role.SUMMARIZER) == (HAIKU,)
    assert [issue for issue in validate_registry(snapshot) if issue.model_id in (GEMINI, LUNA)] == []


def test_both_inputs_route_to_one_exact_endpoint_on_the_conservative_estimate() -> None:
    snapshot = _auto()
    for model, slug in ((GEMINI, "google-vertex/global"), (LUNA, "openai/fast")):
        entry = snapshot.policy.models[model]
        assert entry.route.providers == (slug,) and entry.route.estimator == "conservative-utf8"
        assert entry.default_reasoning == "low"
        route = experimental_route(snapshot, model)
        assert route is not None and route.empirical_estimate and route.provider_family is None


def test_without_the_overlay_ordinary_launches_are_unchanged() -> None:
    ordinary = trusted_snapshot()
    assert ordinary is not None and _auto().effective_hash != ordinary.effective_hash
    assert select_eligible_models(ordinary, Role.EASY) == (HAIKU,)
    assert select_eligible_models(ordinary, Role.MEDIUM) == ()


def test_replacing_a_model_is_an_edit_to_the_overlay(tmp_path: Path) -> None:
    """Models are configuration: removing Luna from easy is a role-list replacement, no code change."""
    with resources.as_file(resources.files("optimus_model_policy").joinpath("auto_overlay.yaml")) as overlay:
        text = overlay.read_text(encoding="utf-8")
    assert text.count("  easy: [anthropic/claude-haiku-5.5, openai/gpt-6-luna]\n") == 1
    edited = tmp_path / "auto_overlay.yaml"
    edited.write_text(text.replace("  easy: [anthropic/claude-haiku-5.5, openai/gpt-6-luna]\n", "  easy: [anthropic/claude-haiku-5.5]\n"), encoding="utf-8")
    assert select_eligible_models(load_registry(packaged_defaults(), edited), Role.EASY) == (HAIKU,)


def test_the_classifier_is_jev_as_adr_027_accepted() -> None:
    """Arm H's model: Jev alone in the classifier role, on its exact endpoint, with the validator's reserve set."""
    snapshot = _auto()
    assert select_eligible_models(snapshot, Role.CLASSIFIER) == (JEV,)
    assert [issue for issue in validate_registry(snapshot) if issue.model_id == JEV] == []
    assert snapshot.policy.output_reserve_tokens["classifier"] == 256
    assert snapshot.policy.output_reserve_tokens["implementer"] == 32768  # maps combine: the defaults' reserves stay
    entry = snapshot.policy.models[JEV]
    assert entry.route.providers == ("typesafe",) and entry.route.estimator == "conservative-utf8"
    route = experimental_route(snapshot, JEV)
    assert route is not None and route.empirical_estimate and route.provider_family is not None
    assert select_eligible_models(trusted_snapshot(), Role.CLASSIFIER) == ()  # ordinary launches assign no classifier
