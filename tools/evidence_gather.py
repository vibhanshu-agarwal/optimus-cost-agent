"""Sole executable entry point for evidence collection stages."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from collections.abc import Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evidence_handoff.collector.bundles import write_raw_bundle, write_run_manifest
from evidence_handoff.collector.models import CapturedArtifact, CollectionBatch, Observation, RunContext
from evidence_handoff.collector.scenarios import load_scenario, resolve_bindings, scenario_sha256

from tools.evidence_gather_support import acp as acp_mod
from tools.evidence_gather_support import ndjson as ndjson_mod
from tools.evidence_gather_support import zed_logs as zed_mod
from tools.evidence_gather_support.common import HostError, require_absolute_path, require_directory, require_existing_file
from tools.evidence_gather_support.fixtures import prepare_fixtures, run_preconditions
from tools.evidence_gather_support.registry import assert_scenario_adapters_registered, build_registry

_STAGE_UNAVAILABLE = "stage_unavailable"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence_gather", add_help=True)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--scenario", type=Path, required=True)
    validate.add_argument("--bind", action="append", default=[])

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--scenario", type=Path, required=True)
    prepare.add_argument("--capture-root", type=Path, required=True)
    prepare.add_argument("--bind", action="append", default=[])

    check = sub.add_parser("check")
    check.add_argument("--scenario", type=Path, required=True)
    check.add_argument("--capture-root", type=Path, required=True)
    check.add_argument("--bind", action="append", default=[])

    collect = sub.add_parser("collect")
    collect.add_argument("--scenario", type=Path, required=True)
    collect.add_argument("--capture-root", type=Path, required=True)
    collect.add_argument("--bind", action="append", default=[])
    collect.add_argument("--workspace-root", type=Path, required=True)
    collect.add_argument("--agent-executable", type=Path, required=True)
    collect.add_argument("--prompt", type=str, required=True)
    collect.add_argument("--timeout-seconds", type=int, required=True)
    collect.add_argument("--ndjson-path", type=Path, required=False)
    collect.add_argument("--correlate-session-id", type=str, required=True)
    collect.add_argument("--correlate-request-id", type=str, required=True)
    collect.add_argument("--correlate-run-id", type=str, required=True)
    collect.add_argument("--debug-session-id", type=str, required=True)
    collect.add_argument("--launch-session-id", type=str, required=False)
    collect.add_argument("--zed-log-root", type=Path, required=False)
    collect.add_argument("--zed-client-identity", type=str, required=False)
    collect.add_argument("--zed-version", type=str, required=False)
    collect.add_argument("--zed-watch-seconds", type=float, required=False)
    collect.add_argument("--zed-pid", type=int, action="append", default=[])

    classify = sub.add_parser("classify")
    classify.add_argument("--scenario", type=Path, required=True)
    classify.add_argument("--capture-root", type=Path, required=True)
    classify.add_argument("--result", type=Path, required=True)
    classify.add_argument("--render-observation", type=Path, required=False)
    classify.add_argument("--bind", action="append", default=[])

    redact = sub.add_parser("redact")
    redact.add_argument("--scenario", type=Path, required=True)
    redact.add_argument("--workspace-root", type=Path, required=True)
    redact.add_argument("--user-data-root", type=Path, action="append", required=True)
    redact.add_argument("--forbidden-root", type=Path, action="append", default=[])
    redact.add_argument("--capture-root", type=Path, required=True)
    redact.add_argument("--result", type=Path, required=True)
    redact.add_argument("--staging-root", type=Path, required=True)
    redact.add_argument("--quarantine-root", type=Path, required=True)
    redact.add_argument("--sanitized-root", type=Path, required=True)
    redact.add_argument("--report", type=Path, required=True)
    redact.add_argument("--screenshot-approval", type=Path, required=False)
    redact.add_argument("--bind", action="append", default=[])

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--report", type=Path, required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    handlers = {
        "validate": _handle_validate,
        "prepare": _handle_prepare,
        "check": _handle_check,
        "collect": _handle_collect,
        "classify": _handle_unavailable,
        "redact": _handle_unavailable,
        "inspect": _handle_unavailable,
    }
    try:
        return handlers[args.command](args)
    except HostError as exc:
        print(exc.code, file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _handle_validate(args: argparse.Namespace) -> int:
    scenario_path = require_existing_file(Path(args.scenario))
    scenario = load_scenario(scenario_path)
    bindings = resolve_bindings(scenario, tuple(args.bind))
    registry = build_registry()
    assert_scenario_adapters_registered(scenario, registry)
    digest = scenario_sha256(scenario, bindings)
    summary = {
        "scenario_id": scenario.scenario_id,
        "scenario_sha256": digest,
        "client_adapter_id": scenario.client.adapter_id,
        "fixture_adapter_id": scenario.fixture.adapter_id,
        "binding_names": [item.name for item in bindings],
        "collection_adapter_ids": [item.adapter_id for item in scenario.collection],
        "detection_adapter_ids": [item.adapter_id for item in scenario.detection],
    }
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


def _handle_prepare(args: argparse.Namespace) -> int:
    scenario_path = require_existing_file(Path(args.scenario))
    capture_root = require_directory(Path(args.capture_root), create=True)
    scenario = load_scenario(scenario_path)
    bindings = resolve_bindings(scenario, tuple(args.bind))
    registry = build_registry()
    assert_scenario_adapters_registered(scenario, registry)
    digest = scenario_sha256(scenario, bindings)
    existing = _find_run_for_digest(capture_root, digest)
    if existing is not None:
        run_id, origin = existing
        context = write_run_manifest(
            capture_root=capture_root,
            scenario=scenario,
            bindings=bindings,
            run_id=run_id,
            monotonic_origin_ns=origin,
        )
    else:
        context = write_run_manifest(
            capture_root=capture_root,
            scenario=scenario,
            bindings=bindings,
        )
    prepare_fixtures(
        capture_root=capture_root,
        scenario=scenario,
        bindings=bindings,
        run_id=context.run_id,
    )
    return 0


def _handle_check(args: argparse.Namespace) -> int:
    scenario_path = require_existing_file(Path(args.scenario))
    capture_root = require_directory(Path(args.capture_root), create=False)
    scenario = load_scenario(scenario_path)
    bindings = resolve_bindings(scenario, tuple(args.bind))
    registry = build_registry()
    assert_scenario_adapters_registered(scenario, registry)
    digest = scenario_sha256(scenario, bindings)
    existing = _find_run_for_digest(capture_root, digest)
    if existing is None:
        raise HostError("run_dir_missing")
    run_id, _origin = existing
    run_preconditions(capture_root=capture_root, scenario=scenario, run_id=run_id)
    return 0


def _handle_collect(args: argparse.Namespace) -> int:
    scenario_path = require_existing_file(Path(args.scenario))
    capture_root = require_directory(Path(args.capture_root), create=False)
    workspace_root = require_absolute_path(Path(args.workspace_root)).resolve()
    agent_executable = require_absolute_path(Path(args.agent_executable)).resolve()
    if not workspace_root.is_dir():
        raise HostError("workspace_missing")
    if not agent_executable.is_file():
        raise HostError("agent_missing")
    scenario = load_scenario(scenario_path)
    bindings = resolve_bindings(scenario, tuple(args.bind))
    registry = build_registry()
    assert_scenario_adapters_registered(scenario, registry)
    digest = scenario_sha256(scenario, bindings)
    existing = _find_run_for_digest(capture_root, digest)
    if existing is None:
        raise HostError("run_dir_missing")
    run_id, origin = existing
    run_preconditions(capture_root=capture_root, scenario=scenario, run_id=run_id)

    zed_enabled = args.zed_log_root is not None
    zed_snapshot = None
    zed_watch_started_ns = 0
    zed_wall_started = "1970-01-01T00:00:00Z"
    zed_pids: tuple[int, ...] = tuple(int(pid) for pid in (args.zed_pid or []))
    observed_pids: tuple[int, ...] = ()
    if zed_enabled:
        if not args.zed_client_identity or not args.zed_version:
            raise HostError("zed_version_mismatch")
        if args.zed_watch_seconds is None:
            raise HostError("zed_watch_timeout")
        if not zed_pids:
            raise HostError("zed_process_lookup_failed")
        zed_mod.require_supported_client_identity(
            str(args.zed_client_identity),
            reported_version=str(args.zed_version),
        )
        zed_root = zed_mod.require_zed_log_root(require_absolute_path(Path(args.zed_log_root)).resolve())
        observed_pids = zed_mod.discover_zed_editor_pids()
        zed_mod.correlate_zed_processes(expected_pids=zed_pids, observed_pids=observed_pids)
        zed_watch_started_ns = time.monotonic_ns()
        zed_wall_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        zed_snapshot = zed_mod.snapshot_log_root(
            zed_root,
            monotonic_ns=zed_watch_started_ns,
            wall_clock=zed_wall_started,
        )

    ndjson_path = (
        require_absolute_path(Path(args.ndjson_path)).resolve()
        if args.ndjson_path is not None
        else (workspace_root / ".optimus" / "debug-acp.ndjson").resolve()
    )
    snapshot = ndjson_mod.snapshot_source(ndjson_path)
    acpx_path, acpx_version = acp_mod.resolve_acpx()
    launch_session_id = args.launch_session_id or f"evidence-{uuid.uuid4().hex}"
    command = acp_mod.build_acpx_command(
        acpx_path=acpx_path,
        workspace_root=workspace_root,
        agent_executable=agent_executable,
        prompt=args.prompt,
        launch_session_id=launch_session_id,
    )
    acp_mod.spawn_acpx(
        command=command,
        cwd=workspace_root,
        env={},
        timeout_seconds=int(args.timeout_seconds),
    )
    records = ndjson_mod.read_ordered_suffix(ndjson_path, snapshot)
    digest_hex = ndjson_mod.suffix_sha256(ndjson_path, snapshot)
    claim = ndjson_mod.normalize_completion(
        records,
        correlate_session_id=args.correlate_session_id,
        correlate_request_id=args.correlate_request_id,
        correlate_run_id=args.correlate_run_id,
        expected_debug_session_id=args.debug_session_id,
        scenario_id=scenario.scenario_id,
        run_id=run_id,
        evidence_sha256=(digest_hex,),
    )
    if claim.claim_kind.value == "render_observed":
        raise HostError("render_claim_forbidden")

    run_dir = capture_root / run_id
    relative = "artifacts/acp-debug-suffix.ndjson"
    artifact_path = run_dir / relative
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with ndjson_path.open("rb") as handle:
        handle.seek(snapshot.byte_offset)
        payload = handle.read()
    artifact_path.write_bytes(payload)
    artifact = CapturedArtifact(
        role="acp_debug_suffix",
        media_type="application/x-ndjson",
        relative_locator=relative,
        sha256=digest_hex,
        size_bytes=len(payload),
    )
    now_offset = time.monotonic_ns() - origin
    observation = Observation(
        schema="evidence-observation-v1",
        scenario_id=scenario.scenario_id,
        run_id=run_id,
        collector_id="acp_stream_collector",
        sequence=0,
        monotonic_offset_ns=max(now_offset, 0),
        observed_at="1970-01-01T00:00:00Z",
        observation_kind="completion_event",
        correlation=(
            ("session_id", args.correlate_session_id),
            ("request_id", args.correlate_request_id),
            ("run_id", args.correlate_run_id),
        ),
        artifact_role=artifact.role,
        artifact_sha256=artifact.sha256,
        reason_code=None,
    )
    batches: list[CollectionBatch] = [
        CollectionBatch(
            collector_id="acp_stream_collector",
            contract_version="v1",
            observations=(observation,),
            artifacts=(artifact,),
        )
    ]

    zed_summary: dict[str, object] | None = None
    if zed_snapshot is not None:
        candidates = zed_mod.list_new_or_changed(zed_snapshot, zed_snapshot.root)
        if not candidates:
            candidates = zed_mod.watch_log_root(
                zed_snapshot,
                watch_seconds=float(args.zed_watch_seconds),
            )
        digests: dict[str, str] = {}
        for candidate in candidates:
            source = zed_snapshot.root / candidate.name
            digests[candidate.name] = zed_mod.digest_stable(source, expected=candidate)
            dest = run_dir / "artifacts" / "zed" / candidate.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
        zed_watch_ended_ns = time.monotonic_ns()
        zed_wall_ended = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        zed_batch = zed_mod.build_collection_batch(
            scenario_id=scenario.scenario_id,
            run_id=run_id,
            monotonic_origin_ns=origin,
            snapshot=zed_snapshot,
            candidates=candidates,
            digests=digests,
            process_pids=zed_pids,
            watch_started_ns=zed_watch_started_ns,
            watch_ended_ns=zed_watch_ended_ns,
            wall_started=zed_wall_started,
            wall_ended=zed_wall_ended,
        )
        batches.append(zed_batch)
        zed_summary = {
            "client_identity": str(args.zed_client_identity),
            "reported_version": str(args.zed_version),
            "log_root": str(zed_snapshot.root),
            "pre_run_count": len(zed_snapshot.records),
            "candidate_names": [item.name for item in candidates],
            "pids": list(zed_pids),
            "observed_pids": list(observed_pids),
            "watch_started_ns": zed_watch_started_ns,
            "watch_ended_ns": zed_watch_ended_ns,
        }

    context = RunContext(
        schema="evidence-run-v1",
        scenario_id=scenario.scenario_id,
        run_id=run_id,
        scenario_sha256=digest,
        capture_root=capture_root,
        monotonic_origin_ns=origin,
    )
    write_raw_bundle(context=context, batches=tuple(batches))
    summary = {
        "schema": "evidence-collect-result-v1",
        "complete": True,
        "run_id": run_id,
        "acpx_version": acpx_version,
        "acpx_path_digest": hashlib.sha256(acpx_path.encode("utf-8")).hexdigest(),
        "artifact_sha256": digest_hex,
        "completion_claim": claim.claim_kind.value,
        "completion_reason_code": claim.reason_code,
        "zed": zed_summary,
    }
    result_path = run_dir / "collect-result.json"
    from evidence_handoff.collector.bundles import _atomic_write_json

    _atomic_write_json(result_path, summary)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "completion_claim": claim.claim_kind.value,
                "zed_candidates": ([] if zed_summary is None else zed_summary["candidate_names"]),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


def _find_run_for_digest(capture_root: Path, digest: str) -> tuple[str, int] | None:
    matches: list[tuple[str, int]] = []
    for path in sorted(capture_root.iterdir()):
        manifest = path / "run-manifest.json"
        if not manifest.is_file():
            continue
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("scenario_sha256") == digest and payload.get("complete") is True:
            matches.append((str(payload["run_id"]), int(payload["monotonic_origin_ns"])))
    if not matches:
        return None
    return matches[-1]


def _handle_unavailable(args: argparse.Namespace) -> int:
    del args
    print(_STAGE_UNAVAILABLE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
