"""CLI ownership, parser surface, and Task-4 stage behavior."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ENTRY = REPO_ROOT / "tools" / "evidence_gather.py"
SUPPORT = REPO_ROOT / "tools" / "evidence_gather_support"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "evidence" / "scenarios" / "zed-session.toml"
PROMPT_INJECTION_RE = re.compile(r"prompt[_-]?inject", re.IGNORECASE)


def _gather():
    import tools.evidence_gather as gather

    return gather


def test_entry_point_module_exists() -> None:
    assert ENTRY.is_file()
    assert not (SUPPORT / "__main__.py").exists()


def test_parser_exposes_exactly_seven_subcommands() -> None:
    gather = _gather()
    parser = gather.build_parser()
    sub = next(action for action in parser._actions if getattr(action, "choices", None))
    assert set(sub.choices) == {
        "validate",
        "prepare",
        "check",
        "collect",
        "classify",
        "redact",
        "inspect",
    }
    assert "all" not in sub.choices
    assert "run" not in sub.choices


def test_forbidden_commands_are_rejected() -> None:
    gather = _gather()
    with pytest.raises(SystemExit):
        gather.build_parser().parse_args(["all"])
    with pytest.raises(SystemExit):
        gather.build_parser().parse_args(["run"])


def test_no_destination_or_model_defaults_on_parser() -> None:
    gather = _gather()
    help_text = gather.build_parser().format_help().lower()
    assert "--model" not in help_text
    assert " all" not in f" {help_text} "
    prepare = gather.build_parser().parse_args(
        [
            "prepare",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str((REPO_ROOT / "tmp-capture").resolve()),
        ]
    )
    assert Path(prepare.capture_root).is_absolute()


def test_no_console_script_registration_for_evidence_gather() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    scripts = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    assert "evidence_gather" not in scripts
    assert "evidence-gather" not in scripts
    assert 'optimus-agent = "optimus.acp.__main__:main"' in scripts


def test_support_package_has_no_main_or_prompt_injection_ids() -> None:
    assert SUPPORT.is_dir()
    assert not (SUPPORT / "__main__.py").exists()
    offenders: list[str] = []
    for path in SUPPORT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if PROMPT_INJECTION_RE.search(text):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_only_entry_point_imports_support_from_outside() -> None:
    allowed = {ENTRY.resolve()}
    offenders: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
                "tools.evidence_gather_support"
            ):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("tools.evidence_gather_support"):
                        offenders.append(path.relative_to(REPO_ROOT).as_posix())
    for path in (REPO_ROOT / "tools").rglob("*.py"):
        if path.resolve() in allowed:
            continue
        if SUPPORT in path.parents or path.parent == SUPPORT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
                "tools.evidence_gather_support"
            ):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_validate_without_model_binding_fails_before_side_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gather = _gather()
    code = gather.main(
        [
            "validate",
            "--scenario",
            str(FIXTURE.resolve()),
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "missing_binding" in err


def test_validate_with_model_binding_emits_content_free_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gather = _gather()
    code = gather.main(
        [
            "validate",
            "--scenario",
            str(FIXTURE.resolve()),
            "--bind",
            "model=operator-supplied",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["scenario_id"] == "zed-session"
    assert "scenario_sha256" in payload
    assert payload["client_adapter_id"] == "zed_acp_client"
    assert "operator-supplied" not in out  # content-free: no binding values


def test_prepare_and_check_are_digest_idempotent(tmp_path: Path) -> None:
    gather = _gather()
    capture = (tmp_path / "capture").resolve()
    scenario = str(FIXTURE.resolve())
    bind = ["--bind", "model=operator-supplied"]
    first = gather.main(
        ["prepare", "--scenario", scenario, "--capture-root", str(capture), *bind]
    )
    second = gather.main(
        ["prepare", "--scenario", scenario, "--capture-root", str(capture), *bind]
    )
    assert first == 0
    assert second == 0
    check = gather.main(
        ["check", "--scenario", scenario, "--capture-root", str(capture), *bind]
    )
    assert check == 0


def test_truncated_fixture_marker_fails_prepare_with_stable_code(tmp_path: Path) -> None:
    from evidence_handoff.collector.scenarios import load_scenario, resolve_bindings
    from tools.evidence_gather_support.common import HostError
    from tools.evidence_gather_support.fixtures import prepare_fixtures

    capture = (tmp_path / "capture").resolve()
    run_id = "run-truncated"
    run_dir = capture / run_id
    run_dir.mkdir(parents=True)
    marker = run_dir / "fixture-marker.json"
    # Simulate crash mid-write: on-disk bytes that are not a complete stage document.
    marker.write_text(
        '{"schema":"evidence-fixture-marker-v1","complete":tru',
        encoding="utf-8",
    )
    scenario = load_scenario(FIXTURE)
    bindings = resolve_bindings(scenario, ("model=operator-supplied",))
    with pytest.raises(HostError) as exc_info:
        prepare_fixtures(
            capture_root=capture,
            scenario=scenario,
            bindings=bindings,
            run_id=run_id,
        )
    assert exc_info.value.code in {"invalid_json", "partial_stage"}
    assert "Expecting" not in str(exc_info.value)
    assert "JSONDecode" not in type(exc_info.value).__name__


def test_truncated_fixture_marker_fails_check_without_claiming_ready(
    tmp_path: Path,
) -> None:
    from evidence_handoff.collector.scenarios import load_scenario
    from tools.evidence_gather_support.common import HostError
    from tools.evidence_gather_support.fixtures import run_preconditions

    capture = (tmp_path / "capture").resolve()
    run_id = "run-truncated-check"
    run_dir = capture / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "fixture-marker.json").write_text(
        '{"schema":"evidence-fixture-marker-v1","complete":tru',
        encoding="utf-8",
    )
    scenario = load_scenario(FIXTURE)
    with pytest.raises(HostError) as exc_info:
        run_preconditions(capture_root=capture, scenario=scenario, run_id=run_id)
    assert exc_info.value.code in {"fixture_incomplete", "invalid_json", "partial_stage"}
    result = json.loads((run_dir / "precondition-result.json").read_text(encoding="utf-8"))
    assert result["complete"] is True
    assert "capture_root_ready" not in result["codes"]
    assert any(
        code in {"fixture_incomplete", "invalid_json", "partial_stage", "fixture_missing"}
        for code in result["codes"]
    )


def test_fixture_stage_writes_use_atomic_json_helpers() -> None:
    text = (SUPPORT / "fixtures.py").read_text(encoding="utf-8")
    assert "_atomic_write_json" in text
    assert "_read_complete_json" in text
    assert ".write_text(" not in text


def test_unknown_adapter_fails_before_fixture_mutation(tmp_path: Path) -> None:
    gather = _gather()
    scenario_path = tmp_path / "bad.toml"
    text = FIXTURE.read_text(encoding="utf-8").replace(
        'adapter_id = "hermetic_user_data_fixture"',
        'adapter_id = "unknown_fixture"',
    )
    scenario_path.write_text(text, encoding="utf-8")
    capture = (tmp_path / "capture").resolve()
    code = gather.main(
        [
            "prepare",
            "--scenario",
            str(scenario_path.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
        ]
    )
    assert code == 2
    assert not any(capture.rglob("*")) if capture.exists() else True


def test_unavailable_stages_print_stable_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gather = _gather()
    capture = (tmp_path / "capture").resolve()
    capture.mkdir()
    code = gather.main(
        [
            "collect",
            "--scenario",
            str(FIXTURE.resolve()),
            "--capture-root",
            str(capture),
            "--bind",
            "model=operator-supplied",
        ]
    )
    assert code == 2
    assert "stage_unavailable" in capsys.readouterr().err


def test_live_markers_are_registered_and_excluded_by_default() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for marker in (
        "requires_acpx",
        "requires_zed",
        "requires_windows_desktop",
        "evidence_investigation",
    ):
        assert marker in text
    addopts = text.split("addopts", 1)[1].split("]", 1)[0]
    for marker in (
        "requires_acpx",
        "requires_zed",
        "requires_windows_desktop",
        "evidence_investigation",
    ):
        assert f"not {marker}" in addopts or marker in addopts
    # Default selection must exclude the new live markers.
    assert "not requires_acpx" in text
    assert "not requires_zed" in text
    assert "not requires_windows_desktop" in text
    assert "not evidence_investigation" in text
