"""Portable collector model contracts."""

from __future__ import annotations

from dataclasses import fields


def _models():
    from evidence_handoff.collector import models

    return models


def test_enums_match_frozen_contract() -> None:
    models = _models()
    assert [member.value for member in models.BindingKind] == [
        "string",
        "integer",
        "boolean",
        "absolute_path",
    ]
    assert [member.value for member in models.Outcome] == [
        "rendered_stable",
        "rendered_then_crashed",
        "client_crashed",
        "indeterminate",
    ]
    assert [member.value for member in models.ClaimKind] == [
        "completion_observed",
        "render_observed",
        "client_alive",
        "observation_window_complete",
        "client_crash_observed",
        "integrity_valid",
    ]


def test_dataclasses_are_frozen_and_slotted() -> None:
    models = _models()
    for cls in (
        models.RequiredBinding,
        models.AdapterParameter,
        models.AdapterSpec,
        models.Scenario,
        models.RunContext,
        models.CapturedArtifact,
        models.Observation,
        models.CollectionBatch,
        models.EvidenceClaim,
        models.ClassificationResult,
    ):
        assert cls.__dataclass_params__.frozen is True
        assert hasattr(cls, "__slots__")


def test_scenario_field_names_match_frozen_contract() -> None:
    models = _models()
    assert tuple(field.name for field in fields(models.Scenario)) == (
        "schema",
        "scenario_id",
        "required_bindings",
        "client",
        "fixture",
        "preconditions",
        "collection",
        "detection",
        "required_evidence",
    )


def test_canonical_serialization_uses_enum_values_and_arrays() -> None:
    models = _models()
    binding = models.RequiredBinding(
        name="model",
        kind=models.BindingKind.STRING,
        required=True,
        min_length=1,
        max_length=32,
    )
    parameter = models.AdapterParameter(
        name="timeout_ms",
        kind=models.BindingKind.INTEGER,
        value=5,
    )
    adapter = models.AdapterSpec(
        adapter_id="acp_stream_collector",
        contract_version="v1",
        parameters=(parameter,),
    )
    scenario = models.Scenario(
        schema="evidence-scenario-v1",
        scenario_id="zed-session",
        required_bindings=(binding,),
        client=adapter,
        fixture=adapter,
        preconditions=(adapter,),
        collection=(adapter,),
        detection=(adapter,),
        required_evidence=("completion_observed",),
    )
    payload = models.scenario_to_canonical_dict(scenario)
    assert payload["required_bindings"][0]["kind"] == "string"
    assert payload["client"]["parameters"][0]["kind"] == "integer"
    assert payload["client"]["parameters"][0]["value"] == 5
    assert payload["preconditions"][0]["adapter_id"] == "acp_stream_collector"
    assert isinstance(payload["required_evidence"], list)
