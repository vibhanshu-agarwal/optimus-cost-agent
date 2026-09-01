from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tools.plan1126_unrun_binding import (
    BINDING_COMMIT,
    EXPECTED_NODE_COUNT,
    OBLIGATION,
    OWNER,
    binding_commit_available,
    format_terminal_summary,
    load_scopeout_manifest,
    scopeout_nodeids,
    scopeout_reason,
    validate_scopeout_manifest,
)

_ROOT = Path(__file__).resolve().parents[3]
_TARGET_FILES = (
    "tests/unit/acp/test_plan1126_cancellation.py",
    "tests/unit/acp/test_plan1126_delivery_contract.py",
    "tests/unit/acp/test_plan1126_queue_policy.py",
    "tests/unit/acp/test_plan1126_semantic_errors.py",
    "tests/unit/acp/test_plan1126_session_lease.py",
    "tests/unit/acp/test_plan1126_shutdown.py",
    "tests/unit/telemetry/test_plan1126_runtime_contract.py",
)


def _collected_target_nodeids() -> tuple[str, ...]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *_TARGET_FILES],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    )


def test_scopeout_manifest_pins_exact_37_collected_nodeids() -> None:
    manifest = load_scopeout_manifest(_ROOT)

    assert manifest.binding_commit == BINDING_COMMIT
    assert manifest.obligation == OBLIGATION
    assert manifest.owner == OWNER
    assert len(manifest.node_ids) == EXPECTED_NODE_COUNT == 37
    assert tuple(sorted(manifest.node_ids)) == manifest.node_ids
    validate_scopeout_manifest(manifest, _collected_target_nodeids())


@pytest.mark.parametrize("mutation", ["add", "remove", "rename"])
def test_scopeout_manifest_mutations_fail_closed(mutation: str) -> None:
    manifest = load_scopeout_manifest(_ROOT)
    collected = _collected_target_nodeids()
    node_ids = list(manifest.node_ids)
    if mutation == "add":
        node_ids.append("tests/unit/acp/test_plan1126_shutdown.py::test_synthetic_scope_creep")
    elif mutation == "remove":
        node_ids.pop()
    else:
        node_ids[0] = f"{node_ids[0]}_renamed"

    with pytest.raises(ValueError):
        validate_scopeout_manifest(replace(manifest, node_ids=tuple(node_ids)), collected)


def test_scopeout_is_conditional_on_commit_object_availability(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "user.name=Scopeout Contract",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "binding",
        ],
        cwd=tmp_path,
        check=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert binding_commit_available(tmp_path, commit)
    assert not binding_commit_available(tmp_path, "0" * 40)


def test_scopeout_runs_when_available_and_attributes_every_skip_when_absent() -> None:
    manifest = load_scopeout_manifest(_ROOT)
    collected = _collected_target_nodeids()

    assert scopeout_nodeids(manifest, collected, binding_available=True) == ()
    assert scopeout_nodeids(manifest, collected, binding_available=False) == manifest.node_ids
    assert OBLIGATION in scopeout_reason()
    assert OWNER in scopeout_reason()


def test_terminal_summary_cannot_launder_unrun_claims_as_verified() -> None:
    summary = format_terminal_summary(EXPECTED_NODE_COUNT)

    assert OBLIGATION in summary
    assert OWNER in summary
    assert "37" in summary
    assert "UNRUN" in summary
    assert "not verified" in summary
