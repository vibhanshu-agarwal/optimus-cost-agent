"""Plan 11.30 Task 1: test profiles — one cost tier per collected node, and the static profiles.

The first part pins the pure classification contract on synthetic manifests. The guards below it
hold the repository's own manifest (`tests/profiles.toml`) against the real collected universe.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.testing import test_profiles as profiles

_NODES = (
    "tests/unit/a/test_one.py::test_x",
    "tests/unit/a/test_one.py::test_y[1]",
    "tests/unit/a/test_one.py::test_y[2]",
    "tests/unit/a/test_one.py::TestGroup::test_z",
    "tests/unit/b/test_two.py::test_w",
    "tests/e2e/test_three.py::test_v",
)


def _manifest(body: str) -> profiles.ProfileManifest:
    return profiles.load_manifest('schema = "test-profiles-v1"\n' + body)


def test_every_node_gets_exactly_one_tier_and_unruled_nodes_are_core() -> None:
    manifest = _manifest('[[rules]]\ntier = "e2e-local"\npaths = ["tests/e2e/**"]\nwhy = "unmarked e2e"\n')
    found = profiles.classify_nodes(_NODES, manifest)
    assert set(found.tiers) == set(_NODES)
    assert found.tiers["tests/e2e/test_three.py::test_v"] == "e2e-local"
    assert {found.tiers[node] for node in _NODES[:5]} == {"core"}
    assert found.origins["tests/unit/b/test_two.py::test_w"] == profiles.DEFAULT_ORIGIN
    assert found.unmatched == ()


def test_the_longest_node_rule_beats_a_shorter_node_rule_and_any_path_rule() -> None:
    manifest = _manifest(
        '[[rules]]\ntier = "proc"\npaths = ["tests/unit/a/test_one.py"]\nwhy = "file"\n'
        '[[rules]]\ntier = "gates"\nnodes = ["tests/unit/a/test_one.py::TestGroup"]\nwhy = "class"\n'
        '[[rules]]\ntier = "audit-current"\nnodes = ["tests/unit/a/test_one.py::TestGroup::test_z"]\nwhy = "method"\n'
        '[[rules]]\ntier = "audit-sealed"\nnodes = ["tests/unit/a/test_one.py::test_y"]\nwhy = "all params"\n'
    )
    found = profiles.classify_nodes(_NODES, manifest)
    assert found.tiers["tests/unit/a/test_one.py::test_x"] == "proc"
    assert found.tiers["tests/unit/a/test_one.py::test_y[1]"] == "audit-sealed"
    assert found.tiers["tests/unit/a/test_one.py::test_y[2]"] == "audit-sealed"
    assert found.tiers["tests/unit/a/test_one.py::TestGroup::test_z"] == "audit-current"
    assert found.unmatched == ("rules[2]: tests/unit/a/test_one.py::TestGroup",)


def test_a_node_rule_never_matches_a_longer_name_that_merely_shares_its_prefix() -> None:
    manifest = _manifest('[[rules]]\ntier = "proc"\nnodes = ["tests/unit/a/test_one.py::test_y"]\nwhy = "y"\n')
    found = profiles.classify_nodes(("tests/unit/a/test_one.py::test_y_other",), manifest)
    assert found.tiers["tests/unit/a/test_one.py::test_y_other"] == "core"
    assert found.unmatched == ("rules[1]: tests/unit/a/test_one.py::test_y",)


def test_two_path_rules_claiming_one_file_are_a_conflict() -> None:
    manifest = _manifest(
        '[[rules]]\ntier = "proc"\npaths = ["tests/unit/a/*.py"]\nwhy = "glob"\n'
        '[[rules]]\ntier = "gates"\npaths = ["tests/unit/a/test_one.py"]\nwhy = "file"\n'
    )
    with pytest.raises(profiles.ClassificationError, match="tests/unit/a/test_one.py"):
        profiles.classify_nodes(_NODES, manifest)


def test_a_rule_that_matches_nothing_is_reported() -> None:
    manifest = _manifest('[[rules]]\ntier = "proc"\npaths = ["tests/unit/gone/test_*.py"]\nwhy = "renamed away"\n')
    assert profiles.classify_nodes(_NODES, manifest).unmatched == ("rules[1]: tests/unit/gone/test_*.py",)


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        ('[[rules]]\ntier = "fast"\npaths = ["x.py"]\nwhy = "w"\n', "tier"),
        ('[[rules]]\ntier = "core"\npaths = ["x.py"]\nnodes = ["x.py::t"]\nwhy = "w"\n', "exactly one of"),
        ('[[rules]]\ntier = "core"\npaths = []\nwhy = "w"\n', "empty"),
        ('[[rules]]\ntier = "core"\npaths = ["x.py"]\n', "why"),
        ('[[rules]]\ntier = "core"\npaths = ["x.py"]\nwhy = ""\n', "why"),
        ('[[rules]]\ntier = "core"\npaths = ["x.py"]\nwhy = "w"\nextra = 1\n', "unknown"),
        ('[[rules]]\ntier = "core"\nnodes = ["x.py"]\nwhy = "w"\n', "::"),
        ('[[rules]]\ntier = "core"\npaths = ["x.py::t"]\nwhy = "w"\n', "::"),
        ('[[rules]]\ntier = "core"\npaths = ["x.py", "x.py"]\nwhy = "w"\n', "more than once"),
        ('[[rules]]\ntier = "core"\npaths = ["x.py"]\nwhy = "w"\n[[rules]]\ntier = "proc"\npaths = ["x.py"]\nwhy = "w"\n', "more than once"),
        ('[[tags]]\nname = "slow"\npaths = ["x.py"]\nwhy = "w"\n', "tag"),
        ("unexpected = true\n", "unknown"),
        ('[measurement]\nsource = "run"\nexplicit_seconds = 2.0\nslow_nodes = ["x.py"]\n', "::"),
        ('[measurement]\nsource = "run"\nexplicit_seconds = -1\nslow_nodes = []\n', "explicit_seconds"),
    ],
)
def test_a_malformed_manifest_is_refused_with_its_reason(body: str, complaint: str) -> None:
    with pytest.raises(profiles.ManifestError, match=complaint):
        _manifest(body)


def test_another_schema_is_refused() -> None:
    with pytest.raises(profiles.ManifestError, match="schema"):
        profiles.load_manifest('schema = "test-profiles-v0"\n')
    with pytest.raises(profiles.ManifestError, match="TOML"):
        profiles.load_manifest("schema = \n")


def test_tags_are_additive_and_independent_of_tiers() -> None:
    manifest = _manifest(
        '[[rules]]\ntier = "proc"\npaths = ["tests/unit/b/test_two.py"]\nwhy = "spawns"\n'
        '[[tags]]\nname = "concurrency"\npaths = ["tests/unit/b/test_two.py"]\nwhy = "races"\n'
        '[[tags]]\nname = "concurrency"\nnodes = ["tests/unit/a/test_one.py::test_x"]\nwhy = "a race without the helpers"\n'
        '[[tags]]\nname = "platform"\nnodes = ["tests/unit/a/test_one.py::test_x"]\nwhy = "branches on sys.platform"\n'
    )
    found = profiles.classify_nodes(_NODES, manifest)
    assert found.tags["tests/unit/a/test_one.py::test_x"] == frozenset({"concurrency", "platform"})
    assert found.tags["tests/unit/b/test_two.py::test_w"] == frozenset({"concurrency"})
    assert found.tags["tests/unit/a/test_one.py::test_y[1]"] == frozenset()
    assert found.tiers["tests/unit/b/test_two.py::test_w"] == "proc"


def test_static_profiles_select_by_tier_or_tag_and_full_selects_everything() -> None:
    manifest = _manifest(
        '[[rules]]\ntier = "proc"\npaths = ["tests/unit/b/test_two.py"]\nwhy = "spawns"\n'
        '[[rules]]\ntier = "audit-current"\nnodes = ["tests/unit/a/test_one.py::test_y"]\nwhy = "measures"\n'
        '[[rules]]\ntier = "audit-sealed"\nnodes = ["tests/unit/a/test_one.py::TestGroup"]\nwhy = "replays"\n'
        '[[rules]]\ntier = "e2e-local"\npaths = ["tests/e2e/**"]\nwhy = "unmarked e2e"\n'
        '[[tags]]\nname = "platform"\nnodes = ["tests/unit/a/test_one.py::test_x"]\nwhy = "sys.platform"\n'
    )
    found = profiles.classify_nodes(_NODES, manifest)
    assert profiles.profile_members(found, "full") == frozenset(_NODES)
    assert profiles.profile_members(found, "core") == {"tests/unit/a/test_one.py::test_x"}
    assert profiles.profile_members(found, "proc") == {"tests/unit/b/test_two.py::test_w"}
    assert profiles.profile_members(found, "audit") == {
        "tests/unit/a/test_one.py::test_y[1]", "tests/unit/a/test_one.py::test_y[2]", "tests/unit/a/test_one.py::TestGroup::test_z",
    }
    assert profiles.profile_members(found, "platform") == {"tests/unit/a/test_one.py::test_x"}
    assert profiles.profile_members(found, "concurrency") == frozenset()
    with pytest.raises(profiles.ClassificationError, match="commit"):
        profiles.profile_members(found, "commit")
    assert set(profiles.STATIC_PROFILES) == {
        "full", "core", "core-parallel", "core-serial", "proc", "audit", "platform", "concurrency",
    }


_PARALLEL_RULES = (
    '[[rules]]\ntier = "proc"\npaths = ["tests/unit/b/test_two.py"]\nwhy = "spawns"\n'
    '[[tags]]\nname = "concurrency"\nnodes = ["tests/unit/a/test_one.py::test_y[1]"]\nwhy = "race"\n'
    '[[tags]]\nname = "platform"\nnodes = ["tests/unit/a/test_one.py::test_y[2]"]\nwhy = "native"\n'
)


def test_core_splits_into_a_reviewed_parallel_set_and_a_serial_remainder() -> None:
    """Plan 11.30 Task 5: only core nodes the reviewed [parallel] rule admits run on xdist workers. Tagged
    concurrency and platform nodes and the rule's serial list stay serial; together the two are exactly core."""
    manifest = _manifest(
        _PARALLEL_RULES + '[parallel]\nserial = ["tests/unit/a/test_one.py::TestGroup"]\nwhy = "shares a fixed path"\n'
    )
    found = profiles.classify_nodes(_NODES, manifest)
    core = profiles.profile_members(found, "core")
    parallel = profiles.profile_members(found, "core-parallel")
    serial = profiles.profile_members(found, "core-serial")
    assert parallel == {"tests/unit/a/test_one.py::test_x", "tests/e2e/test_three.py::test_v"}
    assert serial == {
        "tests/unit/a/test_one.py::test_y[1]", "tests/unit/a/test_one.py::test_y[2]", "tests/unit/a/test_one.py::TestGroup::test_z",
    }
    assert parallel | serial == core and not parallel & serial
    assert found.unmatched == ()


def test_without_a_reviewed_parallel_rule_nothing_runs_in_parallel() -> None:
    found = profiles.classify_nodes(_NODES, _manifest(_PARALLEL_RULES))
    assert profiles.profile_members(found, "core-parallel") == frozenset()
    assert profiles.profile_members(found, "core-serial") == profiles.profile_members(found, "core")


def test_a_serial_pattern_that_matches_no_core_node_is_a_dead_rule() -> None:
    manifest = _manifest(_PARALLEL_RULES + '[parallel]\nserial = ["tests/unit/z/test_gone.py"]\nwhy = "gone"\n')
    assert profiles.classify_nodes(_NODES, manifest).unmatched == ("parallel: tests/unit/z/test_gone.py",)
    with pytest.raises(profiles.ManifestError, match="parallel"):
        _manifest('[parallel]\nserial = ["tests/x.py"]\n')  # a reviewed rule states why


def test_a_measured_slow_node_needs_an_explicit_rule_even_to_stay_core() -> None:
    manifest = _manifest(
        '[[rules]]\ntier = "core"\nnodes = ["tests/unit/a/test_one.py::test_x"]\nwhy = "measured 2.4 s; reviewed cheap enough"\n'
        '[[rules]]\ntier = "proc"\npaths = ["tests/unit/b/test_two.py"]\nwhy = "spawns"\n'
        '[measurement]\nsource = "run 20261002T203101-45752-c1999b"\nexplicit_seconds = 2.0\n'
        'slow_nodes = ["tests/unit/a/test_one.py::test_x", "tests/unit/b/test_two.py::test_w", '
        '"tests/unit/a/test_one.py::test_y[2]", "tests/unit/gone/test_old.py::test_q"]\n'
    )
    found = profiles.classify_nodes(_NODES, manifest)
    assert manifest.explicit_seconds == 2.0
    assert profiles.unexplained_slow_nodes(found, manifest) == ("tests/unit/a/test_one.py::test_y[2]",)


def test_the_manifest_digest_is_of_its_exact_text() -> None:
    text = 'schema = "test-profiles-v1"\n'
    assert profiles.load_manifest(text).digest == profiles.load_manifest(text).digest
    assert profiles.load_manifest(text).digest != profiles.load_manifest(text + "# changed\n").digest


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from tests.support.concurrency import run_threads\n", True),
        ("import tests.support.fault_injection as faults\n", True),
        ("from tests.support import concurrency\n", True),
        ("from tests.support import gateway_settings\n", False),
        ("def f():\n    from tests.support.fault_injection import Gate\n", True),
        ("# from tests.support.concurrency import x\n", False),
        ("TEXT = 'from tests.support.concurrency import x'\n", False),
    ],
)
def test_the_concurrency_signal_is_an_import_of_the_shared_helpers(source: str, expected: bool) -> None:
    assert profiles.concurrency_signal(source) is expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import sys\nif sys.platform == 'win32':\n    pass\n", True),
        ("import os\nWINDOWS = os.name == 'nt'\n", True),
        ("import platform\nplatform.system()\n", True),
        ("import sys\nprint(sys.version)\n", False),
        ("TEXT = 'sys.platform'\n", False),
        ("platform = 'x'\nprint(platform)\n", False),
    ],
)
def test_the_platform_signal_reads_the_running_platform(source: str, expected: bool) -> None:
    assert profiles.platform_signal(source) is expected


# --- The plugin: `--profile` deselects through pytest's own hook and changes nothing else. ---

_ROOT = Path(__file__).resolve().parents[3]
_THIS = "tests/unit/tools/test_test_profiles.py"
_PROC_FILE = "tests/unit/tools/test_run_context_targets.py"
_PLUGIN = "tests.support.profiles_plugin"
_PROFILE_LINE = re.compile(r"test-profiles: profile=(?P<profile>\S+) selected=(?P<selected>\d+) deselected=(?P<deselected>\d+) manifest=(?P<manifest>[0-9a-f]{12})")
_RUN_CONTEXT_LINE = re.compile(r"test-run-context: mode=(?P<mode>\S+) reason=(?P<reason>\S+)")


def test_profile_probe_noop() -> None:
    """A do-nothing core target for the nested runs below."""


def _pytest(tmp_path: Path, *arguments: str, extra_env: dict[str, str] | None = None) -> tuple[int, str]:
    """A real nested pytest of this repository. Its temporary folders (and so its run registry) are tmp_path's."""
    scratch = tmp_path / "child-temp"
    scratch.mkdir(exist_ok=True)
    env = {**os.environ, "TMPDIR": str(scratch), "TEMP": str(scratch), "TMP": str(scratch), **(extra_env or {})}
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *arguments],
        cwd=_ROOT, env=env, capture_output=True, text=True, timeout=300, check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def _collected(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.startswith("tests/") and "::" in line]


def _expected(profile: str, nodeids: list[str]) -> frozenset[str]:
    manifest = profiles.load_manifest((_ROOT / "tests" / "profiles.toml").read_text(encoding="utf-8"))
    return profiles.profile_members(profiles.classify_nodes(tuple(nodeids), manifest), profile)


def test_without_a_profile_the_plugin_changes_no_collection_output(tmp_path: Path) -> None:
    """The MAIN-5 argument shape (explicit root, explicit plugins, targets): output is byte-identical
    with the plugin blocked, apart from the run-context line's run identity."""
    targets = (f"--rootdir={_ROOT}", "--collect-only", _THIS, _PROC_FILE)
    with_plugin = _pytest(tmp_path, *targets)
    without_plugin = _pytest(tmp_path, *targets, "-p", f"no:{_PLUGIN}")
    assert with_plugin[0] == without_plugin[0] == 0, with_plugin[1] + without_plugin[1]

    def stable(output: str) -> list[str]:
        return [re.sub(r" in [0-9.]+s", " in <time>", line) for line in output.splitlines() if "test-run-context:" not in line]

    assert stable(with_plugin[1]) == stable(without_plugin[1])
    assert "test-profiles:" not in with_plugin[1]


def test_a_static_profile_deselects_the_rest_through_pytest_and_says_so(tmp_path: Path) -> None:
    everything = _collected(_pytest(tmp_path, "--collect-only", _THIS, _PROC_FILE)[1])
    expected = _expected("core", everything)
    assert expected and set(everything) - expected, "the control needs both core and non-core nodes"
    code, output = _pytest(tmp_path, "--collect-only", "--profile", "core", _THIS, _PROC_FILE)
    assert code == 0, output
    assert set(_collected(output)) == expected
    line = _PROFILE_LINE.search(output)
    assert line is not None, output
    assert (line["profile"], int(line["selected"]), int(line["deselected"])) == ("core", len(expected), len(everything) - len(expected))
    assert f"{len(expected)}/{len(everything)} tests collected ({len(everything) - len(expected)} deselected)" in output


def test_a_profile_composes_with_k_and_explicit_targets(tmp_path: Path) -> None:
    code, output = _pytest(tmp_path, "--collect-only", "--profile", "core", "-k", "probe_noop", _THIS, _PROC_FILE)
    assert code == 0, output
    assert _collected(output) == [f"{_THIS}::test_profile_probe_noop"]
    code, output = _pytest(tmp_path, "--collect-only", "--profile", "proc", f"{_THIS}::test_profile_probe_noop")
    assert code == 5, output  # nothing selected: an explicit target outside the profile is not run
    assert _collected(output) == []


def test_a_single_file_session_loads_the_plugin(tmp_path: Path) -> None:
    code, output = _pytest(tmp_path, "--collect-only", "--profile", "full", _PROC_FILE)
    assert code == 0, output
    line = _PROFILE_LINE.search(output)
    assert line is not None and (line["profile"], line["deselected"]) == ("full", "0"), output


def test_an_unknown_or_change_selected_profile_is_a_usage_error(tmp_path: Path) -> None:
    for name in ("fast", "commit"):
        code, output = _pytest(tmp_path, "--collect-only", "--profile", name, _THIS)
        assert code == 4, output
        assert "--profile" in output and "core" in output, output


# --- `--audit-depth` (Task 4): only the enumerated H5 repeat budget is lowered, and the run's own record says so. ---

_AUDIT_LINE = re.compile(r"audit-depth: depth=(?P<depth>\S+)(?P<rest>.*)")
_RUN_ID = re.compile(r"test-run-context: .* run=(?P<run>\S+)")
_BUDGET_PROBE = f"{_THIS}::test_audit_budget_probe"


def test_audit_budget_probe(request: pytest.FixtureRequest) -> None:
    """A nested-run target that asks for the H5 budget. In an ordinary run it asks for nothing, so no budget is recorded."""
    if os.environ.get("OPTIMUS_AUDIT_BUDGET_PROBE") != "1":
        return
    budget = request.getfixturevalue("audit_budget")
    assert budget("h5.shutdown_schedule")["repeats"] in {1, 100}


def test_only_the_h5_repeat_budget_is_lowered_and_full_is_the_sealed_count() -> None:
    from tests.support import profiles_plugin as plugin

    # H4's 1,000 seeds, the S1 windows and every other probe have no quick budget: they always run full.
    assert plugin.AUDIT_BUDGETS == {"h5.shutdown_schedule": {"full": {"repeats": 100}, "quick": {"repeats": 1}}}
    for name in ("audit-artifact.schema.json", "audit-artifact-v2.schema.json"):
        schema = json.loads((_ROOT / "tests" / "fixtures" / "plan1126_runtime_audit" / name).read_text(encoding="utf-8"))
        sealed = schema["$defs"]["shutdownScheduleObservations"]["properties"]["repeats_per_family"]["const"]
        assert plugin.AUDIT_BUDGETS["h5.shutdown_schedule"]["full"]["repeats"] == sealed, name
    with pytest.raises(ValueError, match="no reduced-depth budget"):
        plugin.audit_options("quick", "h4.delivery_characterization")
    assert plugin.audit_options("full", "h5.shutdown_schedule") == {"repeats": 100}


@pytest.mark.parametrize(
    ("arguments", "probe", "depth", "budgets"),
    [
        ((), True, "full", 100),
        (("--audit-depth=quick",), True, "quick", 1),
        (("--audit-depth=quick",), False, "quick", None),
        ((), False, "full", None),
    ],
)
def test_the_effective_audit_depth_and_budget_are_in_the_terminal_record_and_summary(
    tmp_path: Path, arguments: tuple[str, ...], probe: bool, depth: str, budgets: int | None,
) -> None:
    from tools.testing import run_context, run_context_records

    code, output = _pytest(tmp_path, *arguments, _BUDGET_PROBE, extra_env={"OPTIMUS_AUDIT_BUDGET_PROBE": "1" if probe else "0"})
    assert code == 0, output
    found = _RUN_ID.search(output)
    assert found is not None, output
    record = run_context_records.read_record(_ROOT / "tmp" / "test-runs" / found["run"] / "run.json")
    assert record is not None and record["checkpoint"] == "terminal", output
    assert record["audit_depth"] == depth
    expected = [] if budgets is None else [{
        "entry": "h5.shutdown_schedule", "depth": depth, "repeats": budgets, "full_repeats": 100,
        "node": run_context._node(_BUDGET_PROBE), "label": run_context._label(_BUDGET_PROBE),  # noqa: SLF001
    }]
    assert record["audit_budgets"] == expected
    line = _AUDIT_LINE.search(output)
    if depth == "full" and budgets is None:
        assert line is None, output  # an ordinary full run's output is unchanged
        return
    assert line is not None and line["depth"] == depth, output
    assert ("REDUCED-DEPTH" in line["rest"]) == (depth == "quick"), output
    assert (f"h5.shutdown_schedule repeats={budgets}/100" in line["rest"]) == (budgets is not None), output


def test_a_nested_session_restores_the_outer_session_s_audit_state() -> None:
    """A session started inside another (an in-process `pytest.main`) has its own depth and reuse list, and
    ending it gives the outer session back exactly its own."""
    from tests.support import profiles_plugin as plugin

    outer = plugin.current_audit_session()
    # Like pytest's Config.getoption: one option set, every other one at its default.
    inner_config = SimpleNamespace(getoption=lambda name, default=None: {"audit_depth": "quick"}.get(name, default))
    plugin.pytest_configure(inner_config)  # type: ignore[arg-type]
    try:
        inner = plugin.current_audit_session()
        assert inner is not outer and inner["depth"] == "quick" and inner["reused"] == []
    finally:
        plugin.pytest_unconfigure(inner_config)  # type: ignore[arg-type]
    assert plugin.current_audit_session() is outer


def test_an_unknown_audit_depth_is_a_usage_error(tmp_path: Path) -> None:
    code, output = _pytest(tmp_path, "--collect-only", "--audit-depth=deep", _BUDGET_PROBE)
    assert code == 4, output
    assert "--audit-depth: invalid choice: 'deep'" in output, output


@pytest.mark.parametrize(
    ("arguments", "mode", "reason"),
    [
        ((), "active", "default_selection"),
        (("-m", "not e2e"), "passive", "non_default_selection"),
        (("--test-run-context=passive",), "passive", "requested"),
    ],
)
def test_a_profile_never_changes_how_the_run_context_classifies_the_session(
    tmp_path: Path, arguments: tuple[str, ...], mode: str, reason: str,
) -> None:
    code, output = _pytest(tmp_path, "--profile", "core", *arguments, f"{_THIS}::test_profile_probe_noop")
    assert code == 0, output
    found = _RUN_CONTEXT_LINE.search(output)
    assert found is not None and (found["mode"], found["reason"]) == (mode, reason), output
    assert _PROFILE_LINE.search(output) is not None, output


def test_unrun_counts_only_the_final_selection(request: pytest.FixtureRequest) -> None:
    """The bound-node skip is marked before deselection; the UNRUN count is taken from the final items."""
    conftest = next(
        plugin for plugin in request.config.pluginmanager.get_plugins()
        if getattr(plugin, "__file__", "") and Path(plugin.__file__).resolve() == _ROOT / "tests" / "conftest.py"
    )
    stash = pytest.Stash()
    stash[conftest._PLAN1126_UNRUN_MARKED] = frozenset({"kept::a", "deselected::b"})  # noqa: SLF001
    session = SimpleNamespace(config=SimpleNamespace(stash=stash), items=[SimpleNamespace(nodeid="kept::a"), SimpleNamespace(nodeid="other::c")])
    conftest.pytest_collection_finish(session)
    assert stash[conftest._PLAN1126_UNRUN_COUNT] == 1  # noqa: SLF001


# --- The repository's manifest, held against the real default selection. ---

_PROC_RUN_CONTEXT_FILES = (
    "tests/unit/tools/test_run_context.py",
    "tests/unit/tools/test_run_context_boundaries.py",
    "tests/unit/tools/test_run_context_child_sites.py",
    "tests/unit/tools/test_run_context_lifecycle.py",
    "tests/unit/tools/test_run_context_reviewed_programs.py",
    "tests/unit/tools/test_run_context_targets.py",
    "tests/unit/tools/test_process_tree.py",
)
_AUDIT_TIERS = frozenset({"audit-current", "audit-sealed"})
# Test modules that import the shared concurrency/fault-injection helpers for tooling, not to race
# current product code. Each must still carry the signal, so a stale entry fails.
_CONCURRENCY_SIGNAL_NOT_PRODUCT = {
    "tests/unit/guardrails/test_ci_parity.py": "fault injection drives CI-parity tooling probes, not product code",
    "tests/unit/support/test_concurrency_diagnostics.py": "tests the concurrency helpers themselves",
    "tests/unit/tools/test_evidence_gather.py": "evidence-gathering tool fault paths",
    "tests/unit/tools/test_probe_p11_zed_session_load.py": "Zed probe tool fault paths",
    "tests/unit/tools/test_process_tree.py": "process-tree tool, proc tier",
    "tests/unit/tools/test_run_context_reviewed_programs.py": "run-context launch proofs, proc tier",
    "tests/unit/tools/test_run_p11_fu_10_acpx_error_code_evidence.py": "acpx evidence tool fault paths",
    "tests/unit/tools/test_run_plan996_acpx_security_evidence.py": "acpx security evidence tool fault paths",
}
# Current-source guards that v4 design contract 1 names: each must stay `gates` or `audit-current`, never a
# change-selected cost tier, so a commit cannot skip them.
_CURRENT_SOURCE_GUARDS = {
    "S1 execution closure": (
        "tests/unit/tools/plan1126_runtime_audit/test_serving_custody.py::test_a_binding_that_omits_an_executing_distribution_is_refused",
        "tests/unit/tools/plan1126_runtime_audit/test_serving_custody.py::test_a_binding_that_omits_an_executing_product_file_is_refused",
        "tests/unit/tools/plan1126_runtime_audit/test_serving_custody.py::test_the_recorder_sees_work_on_threads_started_while_armed",
    ),
    "Zed import closure": (
        "tests/unit/tools/test_probe_p11_zed_session_load.py::test_establishing_import_closure_equals_explicit_module_path_subset",
        "tests/unit/tools/test_probe_p11_zed_session_load.py::test_establishing_import_closure_refuses_a_genuinely_unlisted_reachable_module",
        "tests/unit/tools/test_probe_p11_zed_session_load.py::test_establishing_import_closure_refuses_each_seam2_module_when_unlisted",
    ),
    "logging-surface manifest": ("tests/unit/tools/test_verify_plan996_logging_surfaces.py::test_checked_in_manifest_covers_current_surface_inventory",),
    "walker allowlist": ("tests/unit/guardrails/test_tracked_file_scanners.py::test_every_filesystem_walker_is_migrated_or_has_a_reviewed_non_repository_reason",),
    "debug-trace": (
        "tests/unit/acp/test_debug_trace_call_sites.py::test_call_inventory_is_exactly_the_classified_sites",
        "tests/unit/tools/test_debug_trace_message_rule.py::test_real_sink_module_passes_the_gate",
    ),
    "naming, package and collector boundaries": (
        "tests/unit/evidence/test_naming_boundaries.py::test_package_and_module_names_are_descriptive",
        "tests/unit/evidence/test_import_boundaries.py::test_evidence_handoff_imports_only_stdlib_and_allowlisted_third_party",
        "tests/unit/evidence/test_collector_boundaries.py::test_collector_rejects_optimus_security_and_deployable_imports",
    ),
    # The retirement guard scans tests/ for its retired token, so its file name is assembled, as in the guard itself.
    "provider-balance retirement": (
        "tests/unit/test_" + "cred" + "it_surface_retirement.py::test_no_legacy_provider_balance_identifiers_remain_in_active_surfaces",
    ),
    "UNRUN binding manifest": ("tests/unit/tools/test_plan1126_unrun_binding.py::test_scopeout_manifest_pins_exact_37_collected_nodeids",),
    "run-context source guards in proc files": (
        "tests/unit/tools/test_run_context.py::test_the_context_creates_no_thread",
        "tests/unit/tools/test_run_context_child_sites.py::test_every_default_launch_site_is_mapped_to_a_proof",
    ),
    "the profile manifest itself": ("tests/unit/tools/test_test_profiles.py::test_the_manifest_classifies_the_whole_default_selection_with_no_dead_rule",),
}
# Files with child launch sites that keep `core` nodes, each reviewed. In every other launching file the
# nodes are proc, an audit tier, e2e-local or current-source gates.
_MIXED = "the launching nodes are proc, audit or gates node rules; the core nodes run in-process"
_REVIEWED_CHEAP_LAUNCHERS = {
    "tests/integration/evidence/test_subprocess_truncation.py": "one literal writer program, terminated by the test (0.9 s for the file)",
    "tests/integration/release/test_phase1_release_gate_cli.py": "one release-CLI child with the tripwire at the site; product CLI tests",
    "tests/unit/acp/test_plan1126_queue_policy.py": _MIXED,
    "tests/unit/acp/test_server_reader_ownership.py": _MIXED,
    "tests/unit/acp/test_stdio_ndjson.py": "its launch sites are runner-only plants, skipped in an ordinary run",
    "tests/unit/guardrails/test_ci_parity.py": _MIXED,
    "tests/unit/guardrails/test_local_secret_scan_encoding.py": _MIXED,
    "tests/unit/optimus_gateway/test_request_body_rejection.py": "one gateway child with the tripwire at the site; the file's cost is server shutdown polling",
    "tests/unit/support/test_concurrency_diagnostics.py": "tests of the concurrency helpers: two short literal programs and one reviewed program",
    "tests/unit/tools/test_coverage_products.py": "one short coverage.py run over a synthetic package; the Git end-to-end binding node is proc; tool unit tests",
    "tests/unit/tools/plan1126_runtime_audit/test_current_measurement.py": _MIXED,
    "tests/unit/tools/plan1126_runtime_audit/test_render.py": _MIXED,
    "tests/unit/tools/plan1126_runtime_audit/test_serving_custody.py": _MIXED,
    "tests/unit/tools/test_debug_trace_message_rule.py": _MIXED,
    "tests/unit/tools/test_plan1126_unrun_binding.py": _MIXED,
    "tests/unit/tools/test_registry_maintenance.py": "one literal child whose identity the PID-reuse controls end; tool unit tests",
    "tests/unit/tools/test_run_context_xdist_probes.py": "the xdist targets: one literal sleep grandchild, started only inside the nested grandchild control; otherwise empty",
    "tests/unit/tools/test_run_plan996_acpx_security_evidence.py": _MIXED,
    "tests/unit/tools/test_test_profiles.py": _MIXED,
}


@pytest.fixture(scope="module")
def universe(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, ...]:
    code, output = _pytest(tmp_path_factory.mktemp("universe"), "--collect-only")
    assert code == 0, output[-4000:]
    nodes = tuple(_collected(output))
    assert len(nodes) > 4000, output[-4000:]
    return nodes


@pytest.fixture(scope="module")
def manifest() -> profiles.ProfileManifest:
    return profiles.load_manifest((_ROOT / "tests" / "profiles.toml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def classification(universe: tuple[str, ...], manifest: profiles.ProfileManifest) -> profiles.Classification:
    return profiles.classify_nodes(universe, manifest)


def _files(classification: profiles.Classification) -> dict[str, set[str]]:
    tiers: dict[str, set[str]] = {}
    for node, tier in classification.tiers.items():
        tiers.setdefault(node.split("::", 1)[0], set()).add(tier)
    return tiers


def _signal_files(signal: object, universe: tuple[str, ...]) -> set[str]:
    from tools.tracked_repository_files import tracked_repository_files

    collected = {node.split("::", 1)[0] for node in universe}
    found = set()
    for path in tracked_repository_files(_ROOT, pathspecs=["tests"]):
        relative = path.relative_to(_ROOT).as_posix()
        if relative in collected and signal(path.read_text(encoding="utf-8")):  # type: ignore[operator]
            found.add(relative)
    return found


def test_the_manifest_classifies_the_whole_default_selection_with_no_dead_rule(
    classification: profiles.Classification, universe: tuple[str, ...],
) -> None:
    assert set(classification.tiers) == set(universe)
    assert classification.unmatched == ()
    members = [profiles.profile_members(classification, name) for name in ("core", "proc", "audit")]
    rest = {node for node, tier in classification.tiers.items() if tier in {"gates", "e2e-local"}}
    assert sum(len(group) for group in members) + len(rest) == len(universe)


def test_every_measured_slow_node_has_an_explicit_rule(
    classification: profiles.Classification, manifest: profiles.ProfileManifest,
) -> None:
    assert manifest.slow_nodes and manifest.measurement_source
    # A snapshot entry that is not a collected node ID would make this check vacuous: refresh it instead.
    assert sorted(set(manifest.slow_nodes) - set(classification.tiers)) == [], "stale measurement snapshot entries"
    assert profiles.unexplained_slow_nodes(classification, manifest) == ()


def test_run_context_and_process_tree_tests_are_proc(classification: profiles.Classification) -> None:
    """Proc, except per-node current-source gates that must stay always required (v4 design contract 1)."""
    files = _files(classification)
    for file in _PROC_RUN_CONTEXT_FILES:
        assert "proc" in files.get(file, set()) and files[file] <= {"proc", "gates"}, (file, files.get(file))


@pytest.mark.parametrize("path", ["tests/conftest.py", "tests/support/profiles_plugin.py"])
def test_a_session_hook_change_selects_the_run_context_controls(
    classification: profiles.Classification, manifest: profiles.ProfileManifest, path: str,
) -> None:
    """The conftest and the profile plugin carry run-context identity (collection, deselection, phases, UNRUN); only
    the proc run-context tests control those hooks, so a change to either runs them, not only core and gates."""
    dependencies = profiles.build_dependency_map({}, (path,), manifest)
    changes = profiles.ChangeSet(view="commit", changes=(profiles.Change("M", path),), provisional=(), old_graph=True)
    found = profiles.select_tests(changes, classification, dependencies, profiles.ProfileRequest("commit"))
    lifecycle = {node for node in classification.tiers if node.startswith("tests/unit/tools/test_run_context_lifecycle.py::")}
    assert "tests/unit/tools/test_run_context_lifecycle.py::test_deselected_tests_keep_their_identity" in found.nodes
    assert "proc" in {classification.tiers[node] for node in lifecycle} and lifecycle <= set(found.nodes)


def test_unmarked_end_to_end_tests_are_e2e_local(classification: profiles.Classification) -> None:
    found = {file: tiers for file, tiers in _files(classification).items() if file.startswith("tests/e2e/")}
    assert found and all(tiers == {"e2e-local"} for tiers in found.values()), found


def test_the_concurrency_tag_follows_its_maintained_signal(
    classification: profiles.Classification, universe: tuple[str, ...],
) -> None:
    signal = _signal_files(profiles.concurrency_signal, universe)
    assert set(_CONCURRENCY_SIGNAL_NOT_PRODUCT) <= signal, "a reviewed exclusion lost its signal"
    files = _files(classification)
    # Audit-family files race seeded models of pinned code, not current product code.
    audit = {file for file, tiers in files.items() if tiers & _AUDIT_TIERS}
    tagged = {node.split("::", 1)[0] for node, tags in classification.tags.items() if "concurrency" in tags}
    assert sorted(signal - audit - set(_CONCURRENCY_SIGNAL_NOT_PRODUCT) - tagged) == [], "unaudited concurrency signal"
    assert sorted(tagged & (audit | set(_CONCURRENCY_SIGNAL_NOT_PRODUCT))) == []
    assert not any("concurrency" in classification.tags[node] for node, tier in classification.tiers.items() if tier in _AUDIT_TIERS)


def test_the_platform_tag_follows_its_maintained_signal(
    classification: profiles.Classification, universe: tuple[str, ...],
) -> None:
    signal = _signal_files(profiles.platform_signal, universe)
    tagged = {node.split("::", 1)[0] for node, tags in classification.tags.items() if "platform" in tags}
    assert sorted(signal - tagged) == [], "unaudited platform signal"
    assert sorted(tagged - signal) == [], "a platform-tagged file no longer reads the platform"


def test_every_file_that_launches_a_child_has_a_reviewed_tier(classification: profiles.Classification) -> None:
    sites = json.loads((_ROOT / "tests" / "unit" / "tools" / "run_context_child_sites.json").read_text(encoding="utf-8"))["sites"]
    files = _files(classification)
    cheap = {file for file in {key.split("::", 1)[0] for key in sites} if "core" in files.get(file, set())}
    assert sorted(cheap - set(_REVIEWED_CHEAP_LAUNCHERS)) == [], "a launching file has unreviewed core nodes"
    assert sorted(set(_REVIEWED_CHEAP_LAUNCHERS) - cheap) == [], "a reviewed launcher no longer has core nodes"


# The xdist targets launch a child only inside the nested grandchild control, where that launch is the subject.
_PARALLEL_LAUNCHERS = {"tests/unit/tools/test_run_context_xdist_probes.py"}


def test_no_core_file_that_launches_a_child_runs_on_xdist_workers(classification: profiles.Classification) -> None:
    """Plan 11.30 Task 5, v4 design contract 5: subprocess ownership stays serial. Every core node in a file with a
    mapped launch site is outside core-parallel (the reviewed [parallel] rule lists the file)."""
    sites = json.loads((_ROOT / "tests" / "unit" / "tools" / "run_context_child_sites.json").read_text(encoding="utf-8"))["sites"]
    launching = {key.split("::", 1)[0] for key in sites} - _PARALLEL_LAUNCHERS
    admitted = profiles.profile_members(classification, "core-parallel")
    assert sorted({node.split("::", 1)[0] for node in admitted} & launching) == [], "a launching file runs on xdist workers"
    assert any(node.split("::", 1)[0] in _PARALLEL_LAUNCHERS for node in admitted), "the xdist targets are not admitted"


def test_current_source_guards_are_gates_or_audit_current(classification: profiles.Classification) -> None:
    for category, targets in _CURRENT_SOURCE_GUARDS.items():
        for target in targets:
            found = {node: tier for node, tier in classification.tiers.items() if node == target or node.startswith((target + "::", target + "["))}
            assert found, f"{category}: {target} is not collected"
            assert set(found.values()) <= {"gates", "audit-current"}, (category, found)


def test_every_selection_declaration_still_names_something(
    classification: profiles.Classification, manifest: profiles.ProfileManifest,
) -> None:
    """A stale broad path, input or docs-gate pattern would silently change what a commit selects."""
    from pathlib import PurePosixPath

    from tools.tracked_repository_files import tracked_repository_files

    tracked = [PurePosixPath(path.relative_to(_ROOT).as_posix()) for path in tracked_repository_files(_ROOT, pathspecs=["."])]
    files = [PurePosixPath(file) for file in _files(classification)]
    dead = [f"broad_paths: {pattern}" for pattern in manifest.broad_paths if not any(path.full_match(pattern) for path in tracked)]
    dead += [f"prose_gates: {pattern}" for pattern in manifest.prose_gates if not any(file.full_match(pattern) for file in files)]
    for rule in manifest.inputs:
        dead += [f"{rule.label}.paths: {pattern}" for pattern in rule.patterns if not any(path.full_match(pattern) for path in tracked)]
        dead += [f"{rule.label}.files: {pattern}" for pattern in rule.files if not any(file.full_match(pattern) for file in files)]
    assert dead == []
