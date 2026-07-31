"""Sole executable entry point for evidence collection stages."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evidence_handoff.collector.bundles import write_run_manifest
from evidence_handoff.collector.scenarios import load_scenario, resolve_bindings, scenario_sha256

from tools.evidence_gather_support.common import HostError, require_directory, require_existing_file
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
        "collect": _handle_unavailable,
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
