"""Contract checks for deterministic, offline publication of the report pair."""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import socket
import subprocess
from importlib import import_module
from pathlib import Path

import pytest

from tests.unit.tools.plan1126_runtime_audit.test_composite_repeatability import HASH, REPORTS, _row, documents

ROOT = Path(__file__).resolve().parents[4]
SEALED = {
    "reports/plan-11-26-acp-runtime-audit.json": "8dc32bf425c501c1a2ec8282b0c68754839c1662dbf38f36fc109b3b4b7815df",
    "reports/plan-11-26-acp-runtime-audit.md": "49f7906be60160ef866b57fc9526e7e4488cc61eab61a3b5c216406804ee769c",
    "reports/plan-11-26-terminal-characterization.md": "114efaa96d2ca5f08cbcd9abeb9719b518b7cc39de14d0d4d5827f5f28aa999d",
}


def _cli():
    return import_module("tools.report_repeatability_attribution")


def _documents_with_decision(state: str) -> tuple[bytes, bytes]:
    payload, manifest = documents([_row(1, "PASS"), _row(2, "FAIL"), _row(3, "TIMEOUT", claim="harness")])
    declared = json.loads(manifest)
    declared["evidence_refs"]["decision"] = {"kind": "DECISION", "path": "fixtures/decision.md", "sha256": HASH}
    declared["residual_dispositions"] = [{
        "id": "D1", "state": state, "preserved_verdict": "UNRESOLVED", "owning_issue": 306,
        "decision_text": "Keep this fixture unresolved.", "decision_source_ref": "decision",
    }]
    return payload, json.dumps(declared).encode("utf-8")


def _files(tmp_path: Path, pair: tuple[bytes, bytes]) -> tuple[Path, Path]:
    root = tmp_path / "input"
    root.mkdir(exist_ok=True)
    paths = root / "input.json", root / "manifest.json"
    for path, content in zip(paths, pair, strict=True):
        path.write_bytes(content)
    return paths


def _args(paths: tuple[Path, Path], out: Path) -> list[str]:
    return ["--input", str(paths[0]), "--manifest", str(paths[1]), "--output-dir", str(out)]


def _published(out: Path) -> tuple[bytes, bytes]:
    return (out / "composite.json").read_bytes(), (out / "composite.md").read_bytes()


def test_json_and_markdown_reconcile_same_counts_and_residuals(tmp_path: Path) -> None:
    paths = _files(tmp_path, _documents_with_decision("ACCEPTED"))
    target = tmp_path / "report"
    assert _cli().main(_args(paths, target)) == 0
    raw, md = _published(target)
    result = json.loads(raw)
    assert result["schema"] == "optimus-repeatability-report-v1"
    assert result["input_validity"] == "VALID"
    assert result["harness_instability_observed"]
    assert result["product_variability_observed"]
    assert result["product_repeatability"] == "FLAKY"
    assert result["counts"]["observations"] == 3
    assert result["counts"]["harness_count"] == 1
    assert result["counts"]["unresolved_count"] == 0
    assert result["residual_dispositions"] == json.loads(paths[1].read_bytes())["residual_dispositions"]
    assert b"| Overall | VALID | 3 | 1 | 1 | 1 | 0 | 1 | 0 | true | true | FLAKY |" in md
    assert b"| D1 | UNRESOLVED | ACCEPTED | #306 |" in md
    assert b"| narrow-3 | narrow | 3 | TIMEOUT | HARNESS |" in md


def test_regeneration_is_byte_identical(tmp_path: Path) -> None:
    paths = _files(tmp_path, _documents_with_decision("ACCEPTED"))
    left, right = tmp_path / "left", tmp_path / "right"
    assert _cli().main(_args(paths, left)) == 0
    assert _cli().main(_args(paths, right)) == 0
    assert _published(left) == _published(right)
    assert all(b"\r" not in item and item.endswith(b"\n") for item in _published(left))


def test_fresh_regeneration_matches_committed_pair(tmp_path: Path) -> None:
    paths = REPORTS / "historical-input.json", REPORTS / "historical-manifest.json"
    # The CLI refuses outputs under either input directory or the repository report tree.
    target = tmp_path / "report"
    assert _cli().main(_args(paths, target)) == 0
    assert _published(target) == _published(REPORTS)
    manifest = json.loads(paths[1].read_bytes())
    assert json.loads((REPORTS / "residual-dispositions.json").read_bytes()) == manifest["residual_dispositions"]


def test_manifest_disposition_change_changes_report(tmp_path: Path) -> None:
    targets = tmp_path / "proposed", tmp_path / "accepted"
    for target, state in zip(targets, ("PROPOSED", "ACCEPTED"), strict=True):
        paths = _files(tmp_path, _documents_with_decision(state))
        assert _cli().main(_args(paths, target)) == 0
    first, first_md = _published(targets[0])
    second, second_md = _published(targets[1])
    assert json.loads(first)["inputs"]["manifest_sha256"] != json.loads(second)["inputs"]["manifest_sha256"]
    assert b"| PROPOSED |" in first_md
    assert b"| ACCEPTED |" in second_md


def test_render_launches_nothing_and_never_imports_probe_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row(1, "PASS", claim="none")
    row["command"] = "<historical-interpreter> ignored; echo INERT-MARKER"
    paths = _files(tmp_path, documents([row]))

    def forbidden(*args, **kwargs):
        pytest.fail("Report crossed an offline boundary")

    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        blocked = {"source", "measurement", "repeatability", "run_plan1126_runtime_audit", "keyring"}
        if name.rsplit(".", 1)[-1] in blocked or blocked.intersection(fromlist or ()):
            forbidden()
        return original_import(name, globals, locals, fromlist, level)

    target = tmp_path / "out"
    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(builtins, "__import__", guarded_import)
        assert _cli().main(_args(paths, target)) == 0
    assert b"echo INERT-MARKER" in _published(target)[0]


def test_invalid_input_has_no_success_exit(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    good = [_row(1, "PASS"), _row(2, "FAIL"), _row(3, "TIMEOUT", claim="harness")]
    paths = _files(tmp_path, documents(good[:2], good))
    target = tmp_path / "invalid"
    assert _cli().main(_args(paths, target)) == 2
    assert "diagnostic_kind=VALIDATION" in capsys.readouterr().err
    structured = json.loads(_published(target)[0])
    assert structured["input_validity"] == "INVALID"
    assert structured["product_variability_observed"]
    assert structured["product_repeatability"] == "INDETERMINATE"
    assert len(structured["rows"]) == 2

    assert _cli().main(["--input", str(paths[0])]) == 2
    assert "diagnostic_kind=USAGE" in capsys.readouterr().err


def test_parse_error_and_write_failure_leave_no_partial_report(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, manifest = _documents_with_decision("ACCEPTED")
    paths = _files(tmp_path, (b"{bad", manifest))
    target = tmp_path / "report"
    assert _cli().main(_args(paths, target)) == 2
    assert "diagnostic_kind=PARSE" in capsys.readouterr().err
    assert not target.exists()

    # A digest disagreement would otherwise produce an INVALID pair and exit 2.
    paths = _files(tmp_path, (payload + b"\n", manifest))
    original_write = Path.write_bytes

    def fail_on_second(path: Path, data: bytes) -> int:
        if path.name == "composite.md":
            raise OSError("injected write failure")
        return original_write(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_on_second)
    assert _cli().main(_args(paths, target)) == 1
    assert "diagnostic_kind=IO" in capsys.readouterr().err
    assert set(tmp_path.iterdir()) == {paths[0].parent}


def test_output_refuses_existing_paths_and_input_aliases(tmp_path: Path) -> None:
    paths = _files(tmp_path, _documents_with_decision("ACCEPTED"))
    existing = tmp_path / "existing"
    existing.mkdir()
    for target in (existing, paths[0], paths[0].parent / "under-input", ROOT / "reports" / "must-not-write"):
        assert _cli().main(_args(paths, target)) == 1
    assert not list(existing.iterdir())


def test_output_refuses_actual_link_traversal_and_dangling_links(tmp_path: Path) -> None:
    paths = _files(tmp_path, _documents_with_decision("ACCEPTED"))
    alias = tmp_path / "alias"
    dangling = tmp_path / "dangling"
    try:
        alias.symlink_to(paths[0].parent, target_is_directory=True)
        dangling.symlink_to(tmp_path / "missing", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Host cannot create a directory symlink: {exc}")
    assert _cli().main(_args(paths, alias / "out")) == 1
    assert _cli().main(_args(paths, dangling)) == 1
    assert dangling.is_symlink()
    assert not (paths[0].parent / "out").exists()


def test_output_refuses_a_destination_created_after_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _files(tmp_path, _documents_with_decision("ACCEPTED"))
    target = tmp_path / "report"
    original_write = Path.write_bytes

    def create_competing_directory(path: Path, data: bytes) -> int:
        result = original_write(path, data)
        if path.name == "composite.md":
            target.mkdir()
        return result

    monkeypatch.setattr(Path, "write_bytes", create_competing_directory)
    assert _cli().main(_args(paths, target)) == 1
    assert list(target.iterdir()) == []
    assert set(tmp_path.iterdir()) == {paths[0].parent, target}


def test_sealed_artifact_hashes_unchanged(tmp_path: Path) -> None:
    before = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SEALED}
    assert before == SEALED
    paths = _files(tmp_path, _documents_with_decision("ACCEPTED"))
    assert _cli().main(_args(paths, tmp_path / "out")) == 0
    after = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SEALED}
    assert after == before


@pytest.mark.parametrize("payload", [b'{"schema":"optimus-repeatability-input-v1"}', b"[]"])
def test_readable_input_without_observations_emits_an_invalid_pair(
    payload: bytes, tmp_path: Path, capsys: pytest.CaptureFixture,
) -> None:
    _, manifest = _documents_with_decision("ACCEPTED")
    paths = _files(tmp_path, (payload, manifest))
    target = tmp_path / "invalid"
    assert _cli().main(_args(paths, target)) == 2
    assert "diagnostic_kind=VALIDATION" in capsys.readouterr().err
    structured = json.loads(_published(target)[0])
    assert structured["input_validity"] == "INVALID"
    assert structured["rows"] == []
    assert any(issue["code"] == "missing_observations_array" for issue in structured["diagnostics"])


def test_document_digest_failure_withholds_each_cohorts_verdict(tmp_path: Path) -> None:
    rows = [
        _row(1, "PASS"),
        _row(2, "FAIL"),
        _row(3, "TIMEOUT", claim="harness"),
        _row(1, "PASS", cohort="group"),
        _row(2, "PASS", cohort="group"),
    ]
    payload, manifest = documents(rows)
    paths = _files(tmp_path, (payload + b"\n", manifest))
    target = tmp_path / "invalid"
    assert _cli().main(_args(paths, target)) == 2
    raw, markdown = _published(target)
    data = json.loads(raw)
    assert data["input_validity"] == "INVALID"
    assert data["product_repeatability"] == "INDETERMINATE"
    assert data["product_variability_observed"] and data["harness_instability_observed"]
    cohorts = {row["cohort"]: row for row in data["cohorts"]}
    for cohort in cohorts.values():
        assert cohort["input_validity"] == "INVALID"
        assert cohort["product_repeatability"] == "INDETERMINATE"
    assert cohorts["narrow"]["product_variability_observed"]
    assert cohorts["narrow"]["harness_instability_observed"]
    assert b"| narrow | INVALID |" in markdown
    assert b"| group | INVALID |" in markdown


def test_unknown_manifest_schema_has_no_output_pair(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    payload, manifest = _documents_with_decision("ACCEPTED")
    declared = json.loads(manifest)
    declared["schema"] = "unknown-manifest"
    target = tmp_path / "report"
    assert _cli().main(_args(_files(tmp_path, (payload, json.dumps(declared).encode())), target)) == 2
    assert "diagnostic_kind=PARSE" in capsys.readouterr().err
    assert not target.exists()


def test_deeply_nested_input_is_a_parse_refusal(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _, manifest = _documents_with_decision("ACCEPTED")
    nested = b"[" * 800 + b"null" + b"]" * 800
    payload = b'{"schema":"optimus-repeatability-input-v1","observations":[{"extra":' + nested + b"}]}"
    target = tmp_path / "report"
    assert _cli().main(_args(_files(tmp_path, (payload, manifest)), target)) == 2
    assert "diagnostic_kind=PARSE" in capsys.readouterr().err
    assert not target.exists()


def test_historical_runner_does_not_import_composite_path() -> None:
    tree = ast.parse((ROOT / "tools" / "run_plan1126_runtime_audit.py").read_text(encoding="utf-8"))
    names = {
        name.rsplit(".", 1)[-1]
        for statement in ast.walk(tree)
        if isinstance(statement, (ast.Import, ast.ImportFrom))
        for name in [*(item.name for item in statement.names), getattr(statement, "module", "") or ""]
    }
    assert not names & {"composite_repeatability", "composite_report", "report_repeatability_attribution"}
