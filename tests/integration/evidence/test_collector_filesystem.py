"""Real-filesystem integration for portable collector bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_handoff.collector.models import (
    AdapterParameter,
    AdapterSpec,
    BindingKind,
    CapturedArtifact,
    CollectionBatch,
    Observation,
    RequiredBinding,
    Scenario,
)
from evidence_handoff.collector.scenarios import scenario_sha256


def _bundles():
    from evidence_handoff.collector import bundles

    return bundles


def _scenario() -> Scenario:
    binding = RequiredBinding(
        name="model",
        kind=BindingKind.STRING,
        required=True,
        min_length=1,
        max_length=64,
    )
    adapter = AdapterSpec(
        adapter_id="zed_acp_client",
        contract_version="v1",
        parameters=(),
    )
    return Scenario(
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


def _bindings() -> tuple[AdapterParameter, ...]:
    return (
        AdapterParameter(name="model", kind=BindingKind.STRING, value="operator-supplied"),
    )


def _batch(run_id: str, scenario_id: str = "zed-session") -> CollectionBatch:
    artifact = CapturedArtifact(
        role="trace",
        media_type="application/x-ndjson",
        relative_locator="artifacts/trace.ndjson",
        sha256="b" * 64,
        size_bytes=3,
    )
    observation = Observation(
        schema="evidence-observation-v1",
        scenario_id=scenario_id,
        run_id=run_id,
        collector_id="c1",
        sequence=1,
        monotonic_offset_ns=10,
        observed_at="2026-07-31T00:00:00+00:00",
        observation_kind="sample",
        correlation=(),
        artifact_role="trace",
        artifact_sha256="b" * 64,
        reason_code=None,
    )
    return CollectionBatch(
        collector_id="c1",
        contract_version="v1",
        observations=(observation,),
        artifacts=(artifact,),
    )


def test_write_run_manifest_is_idempotent_for_identical_content(tmp_path: Path) -> None:
    bundles = _bundles()
    capture = tmp_path / "capture"
    capture.mkdir()
    scenario = _scenario()
    bindings = _bindings()
    first = bundles.write_run_manifest(
        capture_root=capture,
        scenario=scenario,
        bindings=bindings,
    )
    second = bundles.write_run_manifest(
        capture_root=capture,
        scenario=scenario,
        bindings=bindings,
        run_id=first.run_id,
        monotonic_origin_ns=first.monotonic_origin_ns,
    )
    assert first == second
    digest = scenario_sha256(scenario, bindings)
    assert first.scenario_sha256 == digest


def test_write_run_manifest_rejects_immutable_mismatch(tmp_path: Path) -> None:
    bundles = _bundles()
    capture = tmp_path / "capture"
    capture.mkdir()
    scenario = _scenario()
    bindings = _bindings()
    first = bundles.write_run_manifest(
        capture_root=capture,
        scenario=scenario,
        bindings=bindings,
    )
    other = AdapterParameter(name="model", kind=BindingKind.STRING, value="different-model")
    with pytest.raises(ValueError, match="immutable_mismatch"):
        bundles.write_run_manifest(
            capture_root=capture,
            scenario=scenario,
            bindings=(other,),
            run_id=first.run_id,
            monotonic_origin_ns=first.monotonic_origin_ns,
        )


def test_partial_stage_metadata_cannot_be_loaded_as_complete(tmp_path: Path) -> None:
    bundles = _bundles()
    capture = tmp_path / "capture"
    capture.mkdir()
    context = bundles.write_run_manifest(
        capture_root=capture,
        scenario=_scenario(),
        bindings=_bindings(),
    )
    partial = capture / context.run_id / "raw-bundle.json.partial-deadbeef"
    partial.write_text('{"schema":"evidence-raw-bundle-v1"', encoding="utf-8")
    with pytest.raises(ValueError, match="partial_stage|bundle_missing"):
        bundles.load_verified_raw_bundle(
            context=context,
            bundle_path=capture / context.run_id / "raw-bundle.json",
        )


def test_atomic_replacement_and_resume(tmp_path: Path) -> None:
    bundles = _bundles()
    capture = tmp_path / "capture"
    capture.mkdir()
    context = bundles.write_run_manifest(
        capture_root=capture,
        scenario=_scenario(),
        bindings=_bindings(),
    )
    batch = _batch(context.run_id)
    path = bundles.write_raw_bundle(context=context, batches=(batch,))
    assert path.is_file()
    loaded = bundles.load_verified_raw_bundle(context=context, bundle_path=path)
    assert loaded == (batch,)
    # Resume: rewrite identical bundle succeeds; load still verifies.
    path_again = bundles.write_raw_bundle(context=context, batches=(batch,))
    assert path_again == path
    assert bundles.load_verified_raw_bundle(context=context, bundle_path=path) == (batch,)


def test_file_identity_change_fails_verification(tmp_path: Path) -> None:
    bundles = _bundles()
    capture = tmp_path / "capture"
    capture.mkdir()
    context = bundles.write_run_manifest(
        capture_root=capture,
        scenario=_scenario(),
        bindings=_bindings(),
    )
    path = bundles.write_raw_bundle(context=context, batches=(_batch(context.run_id),))
    # Mutate bytes in place after a successful write.
    path.write_text(
        path.read_text(encoding="utf-8").replace("sample", "tampered"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="digest_mismatch"):
        bundles.load_verified_raw_bundle(context=context, bundle_path=path)


def test_explicit_targets_and_relative_locators_only(tmp_path: Path) -> None:
    bundles = _bundles()
    capture = tmp_path / "capture"
    capture.mkdir()
    context = bundles.write_run_manifest(
        capture_root=capture,
        scenario=_scenario(),
        bindings=_bindings(),
    )
    bad = CollectionBatch(
        collector_id="c1",
        contract_version="v1",
        observations=(),
        artifacts=(
            CapturedArtifact(
                role="trace",
                media_type="text/plain",
                relative_locator="../escape.txt",
                sha256="b" * 64,
                size_bytes=1,
            ),
        ),
    )
    with pytest.raises(ValueError, match="unsafe_relative_locator"):
        bundles.write_raw_bundle(context=context, batches=(bad,))


def test_path_overlap_rejected(tmp_path: Path) -> None:
    bundles = _bundles()
    capture = tmp_path / "capture"
    nested = capture / "nested"
    nested.mkdir(parents=True)
    with pytest.raises(ValueError, match="path_overlap"):
        bundles.validate_custody_roots(
            capture_root=capture,
            other_roots=(nested,),
            forbidden_roots=(),
        )


def test_forbidden_custody_roots_rejected(tmp_path: Path) -> None:
    bundles = _bundles()
    forbidden = tmp_path / "repo"
    forbidden.mkdir()
    capture = forbidden / "capture"
    capture.mkdir()
    with pytest.raises(ValueError, match="path_under_forbidden_root"):
        bundles.validate_custody_roots(
            capture_root=capture,
            other_roots=(),
            forbidden_roots=(forbidden,),
        )


def test_write_run_manifest_requires_absolute_capture_root(tmp_path: Path) -> None:
    bundles = _bundles()
    relative = Path("relative-capture")
    with pytest.raises(ValueError, match="relative_path_rejected|invalid_binding"):
        bundles.write_run_manifest(
            capture_root=relative,
            scenario=_scenario(),
            bindings=_bindings(),
        )


def test_temporary_partial_files_are_not_completed_stage_names(tmp_path: Path) -> None:
    bundles = _bundles()
    capture = (tmp_path / "capture").resolve()
    capture.mkdir()
    context = bundles.write_run_manifest(
        capture_root=capture,
        scenario=_scenario(),
        bindings=_bindings(),
    )
    path = bundles.write_raw_bundle(context=context, batches=(_batch(context.run_id),))
    run_dir = path.parent
    leftovers = [p.name for p in run_dir.iterdir() if "partial" in p.name.lower()]
    assert leftovers == []
    # Completed document must include schema marker used by loader.
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "evidence-raw-bundle-v1"
    assert payload["complete"] is True
