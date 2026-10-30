"""Plan 11.30 Task 1: test profiles — one cost tier per collected node, and the static profiles.

The first part pins the pure classification contract on synthetic manifests. The guards below it
hold the repository's own manifest (`tests/profiles.toml`) against the real collected universe.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from tools.testing import test_profiles as profiles

_WINDOWS_H5_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows H5 capture")

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
    "tests/unit/context/test_project_registry.py": "a git helper builds fixture repositories; three registry child sites (concurrent allocators, one killed at the commit boundary, one at first initialization); the other nodes run in-process",
    "tests/unit/context_engine/test_boundaries.py": _MIXED,
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
    "tests/unit/tools/test_plan12_stage_c_launch_rehearsal.py": "one inert ACP double child answering one request; the rehearsal's other nodes drive a fake executor in-process",
    "tests/unit/tools/test_registry_maintenance.py": "one literal child whose identity the PID-reuse controls end; tool unit tests",
    "tests/unit/tools/test_run_context_xdist_probes.py": "the xdist targets: one literal sleep grandchild, started only inside the nested grandchild control; otherwise empty",
    "tests/unit/tools/test_run_plan996_acpx_security_evidence.py": _MIXED,
    "tests/unit/tools/test_test_profiles.py": "existing launching nodes have proc/gates rules; the six H5 core nodes launch seven owned two-node synthetic passive pytest children through one inventoried helper, never the H5 probe; remaining core nodes run in-process",
    "tests/unit/tools/test_verify_plan99_noneditable_install.py": _MIXED,
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


def test_h5_budget_platform_tags_are_node_scoped(manifest):
    nodes = (
        "tests/unit/tools/plan1126_runtime_audit/test_current_measurement.py::test_short_sidecar_temp_path[native]",
        "tests/unit/tools/test_h5_failure_capture.py::test_capture_path_budget",
        "tests/unit/tools/test_h5_failure_capture.py::test_retains_every_ordered_row_and_long_error_metadata",
        "tests/unit/tools/test_test_profiles.py::test_capture_controls_never_touch_inherited_outer_base",
        "tests/unit/tools/plan1126_runtime_audit/test_current_measurement.py::test_short_sidecar_temp_path[simulated]",
        "tests/unit/tools/plan1126_runtime_audit/test_current_measurement.py::test_short_sidecar_fault_cleanup[write]",
        "tests/unit/tools/test_h5_failure_capture.py::test_non_windows_branch_is_simulated_and_does_no_io",
    )
    found = profiles.classify_nodes(nodes, manifest)
    targets = frozenset(nodes[:4])
    assert profiles.profile_members(found, "platform") == targets
    assert {node for node, tags in found.tags.items() if "platform" in tags} == targets
    assert all(found.tiers[node] == "core" for node in targets)
    assert targets <= profiles.profile_members(found, "core-serial")
    parallel = profiles.profile_members(found, "core-parallel")
    assert targets.isdisjoint(parallel) and nodes[-1] in parallel
    assert all(not found.tags[node] for node in nodes[4:])


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


@pytest.fixture
def h5_capture_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Synthetic bridge state; inherited activation and outer state never escape this scope."""
    from tests.support import profiles_plugin as plugin
    from tools.testing import run_context

    monkeypatch.delenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY", raising=False)
    context = run_context.RunContext(
        run_id=f"20261023T000000-{os.getpid()}-abc123", mode="passive", reason="synthetic_fixture",
        record_dir=tmp_path / "records", started_utc="2026-10-23T00:00:00+00:00",
        worktree=str(_ROOT), head="a" * 40, root={"pid": os.getpid(), "creation_time": 123456},
    )
    monkeypatch.setattr(plugin, "_h5_context", lambda: context)
    monkeypatch.setattr(plugin, "_SESSIONS", [{"depth": "full", "reused": []}, {"depth": "full", "reused": []}])
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist (call)")
    directory = tmp_path / "capture"
    directory.mkdir()
    monkeypatch.setenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY", str(directory))
    return plugin, context, directory


def test_legacy_h5_activation_does_not_admit(h5_capture_scope, monkeypatch):
    from tests.support import h5_failure_capture as capture

    plugin, _, directory = h5_capture_scope
    monkeypatch.delenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY")
    monkeypatch.setenv("OPTIMUS_H5_CAPTURE_DIRECTORY", str(directory))
    binding, result, calls = _h5_stub(monkeypatch)
    monkeypatch.setattr(capture, "validate_capture_directory", lambda *a: pytest.fail("no capture I/O"))
    monkeypatch.setattr(plugin, "_h5_utc_now", lambda: pytest.fail("no diagnostic timing"))
    actual = _h5_bridge(plugin)
    assert actual[0] is binding and actual[1] is result and len(calls) == 1
    session = plugin.current_audit_session()
    assert "h5_capture" not in session and "h5_lines" not in session
    assert _h5_report(plugin).sections == [("existing", "UNCHANGED")]
    assert os.listdir(directory) == []


def _h5_synthetic_measurement():
    """Full synthetic 100-repeat fixture, never a measured acceptance result."""
    from tools.plan1126_runtime_audit.measurement import EnvironmentBinding
    from tools.plan1126_runtime_audit.shutdown import ResourceOwnershipRecord, ShutdownScheduleObservation

    binding = EnvironmentBinding(sys.executable, sys.version, sys.prefix, "a" * 64,
                                 (("src/fixture.py", str(_ROOT / "src/fixture.py"), "b" * 64),), ())
    resource = ResourceOwnershipRecord("h5-synthetic", "Fixture", "Fixture.close", "fixture", "fixture", "fixture",
                                       "fixture", "fixture", "fixture", 1, ("merged",), True)
    inventory = {"kind": "shutdown-close-paths", "resources": [resource.to_dict()], "source_fingerprint": "a" * 64, "close_path_count": 1, "close_sites": []}
    rows = []
    for cause in ("orderly_eof", "request_cancellation", "transport_failure", "server_cancellation", "partial_startup_failure"):
        for _ in range(100):
            row = ShutdownScheduleObservation("h5-synthetic", cause, True, 3, ("MainThread",), (), (),
                                              "WITHIN_100MS", 1, "CLOSED_ONCE", f"{cause}:prepared").to_dict()
            rows.append({"observation_id": "h5-synthetic", **row})
    return binding, {"inventory": inventory, "inventory_identifiers": ["h5-synthetic"], "observations": rows}


@_WINDOWS_H5_ONLY
def test_h5_existing_bridge_retains_complete_bundle_before_assertions(h5_capture_scope, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.plan1126_runtime_audit import measurement

    plugin, context, directory = h5_capture_scope
    binding, result = _h5_synthetic_measurement()
    calls = []

    def measure(**kwargs):
        calls.append(kwargs)
        return binding, result, None

    monkeypatch.setattr(measurement, "session_measurement_reuse", lambda: SimpleNamespace(measure=measure))
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist (call)")
    actual_binding, actual_result = plugin.measure_current_entry(
        source=None, spec=None, entry="h5.shutdown_schedule", options={"repeats": 100}, repository_root=_ROOT,
    )
    assert actual_binding is binding and actual_result is result
    assert len(calls) == 1 and calls[0]["depth"] == "full" and calls[0]["options"] == {"repeats": 100}
    assert calls[0]["requester"] == "tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist"
    assert context.root["pid"] == os.getpid() and Path(context.worktree) == _ROOT and len(plugin._SESSIONS) == 2
    assert (directory / context.run_id / "h5/capture.json").is_file(), "existing bridge must retain the complete bundle"


def _h5_stub(monkeypatch, *, earlier=None, error=None):
    from tools.plan1126_runtime_audit import measurement
    binding, result = _h5_synthetic_measurement()
    calls = []
    def measure(**kwargs):
        calls.append(kwargs)
        if error is not None:
            raise error
        return binding, result, earlier
    monkeypatch.setattr(measurement, "session_measurement_reuse", lambda: SimpleNamespace(measure=measure))
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist (call)")
    return binding, result, calls


def _h5_bridge(plugin, **overrides):
    arguments = dict(source=None, spec=None, entry="h5.shutdown_schedule", options={"repeats": 100}, repository_root=_ROOT)
    arguments.update(overrides)
    return plugin.measure_current_entry(**arguments)


def _h5_report(plugin, *, nodeid=None):
    nodeid = nodeid or "tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist"
    report = SimpleNamespace(sections=[("existing", "UNCHANGED")], outcome="failed", when="call", longrepr=object())
    original = (report.outcome, report.when, report.longrepr)
    hook = plugin.pytest_runtest_makereport(SimpleNamespace(nodeid=nodeid), SimpleNamespace(when="call"))
    next(hook)
    with pytest.raises(StopIteration) as finished:
        hook.send(report)
    assert finished.value.value is report
    assert (report.outcome, report.when, report.longrepr) == original
    return report


@pytest.mark.parametrize("defect", ["absent", "empty", "other_node", "setup", "quick", "other_entry", "bool", "nested", "root"])
def test_h5_disabled_and_ineligible_calls_do_no_observer_work(h5_capture_scope, monkeypatch, defect):
    from tests.support import h5_failure_capture as capture
    plugin, context, directory = h5_capture_scope
    binding, result, calls = _h5_stub(monkeypatch)
    overrides = {}
    if defect == "absent":
        monkeypatch.delenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY")
    elif defect == "empty":
        monkeypatch.setenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY", "")
    elif defect in {"other_node", "setup"}:
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/unit/acp/test_other.py::test_other (call)" if defect == "other_node" else
                           "tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist (setup)")
    elif defect == "quick":
        plugin.current_audit_session()["depth"] = "quick"
    elif defect == "other_entry":
        overrides["entry"] = "h4.fixture"
    elif defect == "bool":
        overrides["options"] = {"repeats": True}
    elif defect == "nested":
        plugin._SESSIONS.append({"depth": "full", "reused": []})
    else:
        context.worktree = str(directory)
    monkeypatch.setattr(capture, "validate_capture_directory", lambda *a: pytest.fail("no capture I/O"))
    monkeypatch.setattr(plugin, "_h5_utc_now", lambda: pytest.fail("no diagnostic timing"))
    actual = _h5_bridge(plugin, **overrides)
    assert actual[0] is binding and actual[1] is result and len(calls) == 1
    assert "h5_capture" not in plugin.current_audit_session()
    assert _h5_report(plugin).sections == [("existing", "UNCHANGED")]
    assert not (directory / context.run_id).exists()


def test_disabled_raising_target_keeps_original_report_sections(h5_capture_scope, monkeypatch):
    plugin, context, directory = h5_capture_scope
    error = OSError("ORIGINAL")
    _h5_stub(monkeypatch, error=error)
    monkeypatch.delenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY")
    monkeypatch.setattr(plugin, "_h5_utc_now", lambda: pytest.fail("no disabled timestamp"))
    with pytest.raises(OSError) as found:
        _h5_bridge(plugin)
    assert found.value is error
    assert "h5_capture" not in plugin.current_audit_session()
    assert _h5_report(plugin).sections == [("existing", "UNCHANGED")]
    assert plugin.current_audit_session().get("h5_lines", []) == []
    assert not (directory / context.run_id).exists()


@_WINDOWS_H5_ONLY
@pytest.mark.parametrize("kind", ["source", "source_subclass", "ordinary", "base"])
def test_measurement_failure_kind_and_original_exception_escape(h5_capture_scope, monkeypatch, kind):
    from tools.plan1126_runtime_audit.source import ExecutingSourceMismatch
    class DerivedRefusal(ExecutingSourceMismatch):
        pass
    errors = {"source": ExecutingSourceMismatch("SOURCE_REFUSAL"), "source_subclass": DerivedRefusal("SOURCE_REFUSAL"),
              "ordinary": OSError("ORIGINAL"), "base": KeyboardInterrupt()}
    plugin, context, directory = h5_capture_scope
    error = errors[kind]
    _h5_stub(monkeypatch, error=error)
    with pytest.raises(type(error)) as found:
        _h5_bridge(plugin)
    assert found.value is error and error.__traceback__.tb_next is not None
    expected = None if kind == "base" else "ORDINARY" if kind == "ordinary" else "SOURCE_REFUSAL"
    assert plugin.current_audit_session()["h5_capture"]["failure_kind"] == expected
    report = _h5_report(plugin)
    if expected is not None:
        assert len(report.sections) == 2
        assert report.sections[1][1] == ("ISSUE287_H5_MEASUREMENT_RAISED" if kind == "ordinary" else "ISSUE287_H5_SOURCE_REFUSAL")
    else:
        assert report.sections == [("existing", "UNCHANGED")]
    assert not (directory / context.run_id).exists()


@_WINDOWS_H5_ONLY
def test_failure_kind_write_error_preserves_original_exception(h5_capture_scope, monkeypatch):
    plugin, _, _ = h5_capture_scope
    error = OSError("ORIGINAL")
    cause = ValueError("CAUSE")
    error.__cause__ = cause
    _h5_stub(monkeypatch, error=error)
    def broken_write(*args):
        raise RuntimeError("DIAGNOSTIC_WRITE")
    monkeypatch.setattr(plugin, "_h5_record_failure", broken_write)
    with pytest.raises(OSError) as found:
        _h5_bridge(plugin)
    assert found.value is error and error.__cause__ is cause and error.__context__ is None
    frames = []
    tb = error.__traceback__
    while tb:
        frames.append(tb.tb_frame.f_code.co_name)
        tb = tb.tb_next
    assert frames[-1] == "measure" and "broken_write" not in frames
    assert plugin.current_audit_session()["h5_capture"]["failure_kind"] is None


@_WINDOWS_H5_ONLY
def test_h5_reuse_keeps_original_objects_and_existing_bookkeeping(h5_capture_scope, monkeypatch):
    plugin, context, directory = h5_capture_scope
    earlier = "tests/unit/acp/test_fixture.py::test_earlier"
    binding, result, calls = _h5_stub(monkeypatch, earlier=earlier)
    actual = _h5_bridge(plugin)
    assert actual[0] is binding and actual[1] is result and len(calls) == 1
    assert plugin.current_audit_session()["reused"] == [{"entry": "h5.shutdown_schedule", "nodeid": calls[0]["requester"], "from_nodeid": earlier}]
    receipt = json.loads((directory / context.run_id / "h5/capture.json").read_text())
    assert receipt["reuse_state"] == "REUSED" and receipt["producer_window"] == "unknown"
    assert _h5_report(plugin).sections == [("existing", "UNCHANGED")]
    assert "ISSUE287_H5_CAPTURE_METRICS" in "\n".join(plugin.current_audit_session()["h5_lines"])
    assert _h5_report(plugin, nodeid="tests/unit/acp/test_fixture.py::test_later").sections == [("existing", "UNCHANGED")]


def test_same_interpreter_nested_capture_is_ineligible_even_with_outer_context(h5_capture_scope, monkeypatch):
    plugin, context, directory = h5_capture_scope
    _h5_stub(monkeypatch)
    outer = plugin.current_audit_session()
    outer["h5_capture"] = {"sentinel": "outer"}
    config = SimpleNamespace(getoption=lambda name, default=None: {"audit_depth": "full"}.get(name, default))
    plugin.pytest_configure(config)
    try:
        _h5_bridge(plugin)
        assert "h5_capture" not in plugin.current_audit_session()
    finally:
        plugin.pytest_unconfigure(config)
    assert plugin.current_audit_session() is outer and outer["h5_capture"] == {"sentinel": "outer"}
    assert not (directory / context.run_id).exists()


@_WINDOWS_H5_ONLY
def test_fixture_and_production_use_the_same_root_predicate(h5_capture_scope, monkeypatch, tmp_path):
    plugin, context, directory = h5_capture_scope
    _h5_stub(monkeypatch)
    owned_root = tmp_path / "synthetic-root"
    owned_root.mkdir()
    monkeypatch.setattr(plugin, "_H5_REPOSITORY_ROOT", owned_root)
    context.worktree = str(owned_root)
    _h5_bridge(plugin, repository_root=owned_root)
    assert (directory / context.run_id / "h5/capture.json").is_file()


def test_root_mismatch_is_ineligible_without_writes(h5_capture_scope, monkeypatch):
    plugin, context, directory = h5_capture_scope
    _h5_stub(monkeypatch)
    context.worktree = str(directory)
    _h5_bridge(plugin)
    assert "h5_capture" not in plugin.current_audit_session() and not (directory / context.run_id).exists()


def test_simulated_non_windows_status_is_visible_for_a_passing_call(h5_capture_scope, monkeypatch):
    plugin, context, directory = h5_capture_scope
    _h5_stub(monkeypatch)
    monkeypatch.setattr(plugin, "_H5_PLATFORM", "linux")
    _h5_bridge(plugin)
    report = _h5_report(plugin)
    assert report.sections[-1] == ("H5 in-suite capture", "ISSUE287_H5_CAPTURE_UNSUPPORTED")
    assert plugin.current_audit_session()["h5_lines"] == ["ISSUE287_H5_CAPTURE_UNSUPPORTED"]
    assert not (directory / context.run_id).exists()


@pytest.fixture
def h5_isolated_activation(monkeypatch):
    monkeypatch.delenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY", raising=False)


def _h5_native_fixture(tmp_path: Path) -> Path:
    """Owned isolated child fixture; source data are synthetic, mode remains passive."""
    root = tmp_path / "child"
    target = root / "tests/unit/acp"
    target.mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (root / "conftest.py").write_text('''
import json, os
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.testing import run_context, run_context_records, run_context_windows
ROOT = Path(__file__).parent.resolve()
REPOSITORY = Path(run_context.__file__).resolve().parents[2]
forbidden = {"start_run": 0, "prune_run_folders": 0, "repository_append": 0}
def refuse_start(*args, **kwargs):
    forbidden["start_run"] += 1
    raise AssertionError("H5_FIXTURE_FORBIDDEN_START")
def refuse_prune(*args, **kwargs):
    forbidden["prune_run_folders"] += 1
    raise AssertionError("H5_FIXTURE_FORBIDDEN_PRUNE")
original_append = run_context._append
def guarded_append(context, *args, **kwargs):
    if Path(context.record_dir).resolve().is_relative_to(REPOSITORY / "tmp/test-runs"):
        forbidden["repository_append"] += 1
        raise AssertionError("H5_FIXTURE_FORBIDDEN_APPEND")
    return original_append(context, *args, **kwargs)
run_context.start_run = refuse_start
run_context_records.prune_run_folders = refuse_prune
run_context._append = guarded_append
# Install custody tripwires before importing the fixture/data helpers or profile plugin.
from tests.support import profiles_plugin as plugin
from tests.support import h5_failure_capture as capture
from tools.plan1126_runtime_audit import measurement
from tests.unit.tools.test_test_profiles import _h5_synthetic_measurement
pytest_plugins = ["tests.support.profiles_plugin"]
try:
    identity = run_context_windows.current_identity()
    assert type(identity.pid) is int and identity.pid == os.getpid()
    assert type(identity.creation_time) is int and identity.creation_time > 0 and identity.error is None
except Exception:
    raise RuntimeError("H-NATIVE-IDENTITY") from None
facts = {"pid": identity.pid, "creation_time": identity.creation_time,
    "identity_method": "run_context_windows.current_identity/GetCurrentProcess/GetProcessTimes",
    "run_id": f"20261023T000000-{os.getpid()}-abc123", "head": "a"*40, "worktree": str(ROOT),
    "mode": "passive", "forbidden": forbidden, "collected": [], "executed": [], "stub_calls": 0}
reports, before = [], {}
@pytest.fixture(autouse=True)
def synthetic(monkeypatch):
    context=run_context.RunContext(run_id=facts["run_id"],mode="passive",reason="synthetic_fixture",
        record_dir=ROOT/"records",started_utc="2026-10-23T00:00:00+00:00",worktree=str(ROOT),head="a"*40,
        root={"pid":identity.pid,"creation_time":identity.creation_time})
    monkeypatch.setattr(run_context,"_current",context)
    monkeypatch.setattr(capture,"os",SimpleNamespace(path=os.path,getpid=os.getpid,lstat=os.lstat,rename=os.rename))
    monkeypatch.setattr(plugin,"_H5_REPOSITORY_ROOT",ROOT)
    binding,result=_h5_synthetic_measurement()
    def measure(**kwargs):
        facts["stub_calls"] += 1
        assert kwargs["entry"] == "h5.shutdown_schedule" and kwargs["options"] == {"repeats": 100}
        assert kwargs["depth"] == "full" and kwargs["repository_root"].resolve() == ROOT
        return binding,result,None
    monkeypatch.setattr(measurement,"session_measurement_reuse",lambda:SimpleNamespace(measure=measure))
    def fail(*args,**kwargs): raise OSError("PRIVATE_CAPTURE_MESSAGE")
    failure=os.environ.get("H5_FIXTURE_FAILURE")
    if failure=="write": monkeypatch.setattr(capture.evidence_store,"write_evidence_sidecar",fail)
    if failure=="verify": monkeypatch.setattr(capture,"_verify_bundle",fail)
    if failure=="rename": monkeypatch.setattr(capture.os,"rename",fail)
def pytest_collection_modifyitems(items):
    facts["collected"] = [item.nodeid for item in items]
@pytest.hookimpl(wrapper=True,trylast=True)
def pytest_runtest_makereport(item,call):
    report=yield
    if report.when=="call": before[item.nodeid]=(report,report.outcome,report.when,report.longrepr,list(report.sections))
    return report
def pytest_runtest_logreport(report):
    if report.when=="call":
        original,outcome,when,longrepr,sections=before[report.nodeid]
        assert report is original and report.outcome==outcome and report.when==when and report.longrepr is longrepr
        if report.nodeid.endswith("test_later"): assert report.sections==sections
        facts["executed"].append(report.nodeid)
        reports.append({"nodeid":report.nodeid,"outcome":report.outcome,"when":report.when,
            "longrepr":str(report.longrepr),"sections":report.sections,"same_object":True})
def pytest_sessionfinish(session):
    (ROOT/"reports.json").write_text(json.dumps(reports),encoding="utf-8")
    (ROOT/"contract.json").write_text(json.dumps(facts),encoding="utf-8")
''', encoding="utf-8")
    (target / "test_plan1126_shutdown.py").write_text('''
import os
from pathlib import Path
from tests.support.profiles_plugin import measure_current_entry
def test_shutdown_causes_repeat_100_with_control_allowlist():
    measure_current_entry(source=None,spec=None,entry="h5.shutdown_schedule",options={"repeats":100},repository_root=Path(__file__).parents[3])
    if os.environ.get("H5_FIXTURE_PASS")!="yes": raise AssertionError("ORIGINAL_H5_FAILURE")
def test_later(): pass
''', encoding="utf-8")
    known = ("pytest.ini", "conftest.py", "tests/unit/acp/test_plan1126_shutdown.py")
    (root / "fixture-source.json").write_text(json.dumps({name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                                        for name in known}), encoding="utf-8")
    return root


def _h5_native_run(root: Path, directory: Path | None, *, failure="", passed=False):
    known = ("pytest.ini", "conftest.py", "tests/unit/acp/test_plan1126_shutdown.py")
    manifest = json.loads((root / "fixture-source.json").read_text(encoding="utf-8"))
    assert set(manifest) == set(known)
    assert manifest == {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in known}
    assert (root / "pytest.ini").read_text(encoding="utf-8") == "[pytest]\n"
    runs_before = set(os.listdir(_ROOT / "tmp/test-runs"))
    env = dict(os.environ)
    env.pop("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY", None)
    env.update(PYTHONPATH=str(_ROOT), H5_FIXTURE_FAILURE=failure, H5_FIXTURE_PASS="yes" if passed else "no", PYTHONUTF8="1")
    if directory is not None:
        directory.mkdir(exist_ok=True)
        env["PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY"] = str(directory)
    completed = subprocess.run([sys.executable, "-m", "pytest", "--no-cov", "-q", "-c", str(root / "pytest.ini"),
                                "--rootdir", str(root), "--junitxml", str(root / "junit.xml"), str(root / "tests")],
                               cwd=root, env=env, capture_output=True, text=True, timeout=90, check=False)
    assert set(os.listdir(_ROOT / "tmp/test-runs")) == runs_before, "H5_FIXTURE_RUN_RECORD_DRIFT"
    output = completed.stdout + completed.stderr
    facts = json.loads((root / "contract.json").read_text(encoding="utf-8"))
    reports = json.loads((root / "reports.json").read_text(encoding="utf-8"))
    nodes = ["tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist",
             "tests/unit/acp/test_plan1126_shutdown.py::test_later"]
    assert facts["collected"] == facts["executed"] == [r["nodeid"] for r in reports] == nodes
    assert facts["stub_calls"] == 1 and facts["forbidden"] == {"start_run": 0, "prune_run_folders": 0, "repository_append": 0}
    assert type(facts["pid"]) is int and facts["pid"] > 0 and facts["pid"] != os.getpid()
    assert type(facts["creation_time"]) is int and facts["creation_time"] > 0
    assert facts["identity_method"] == "run_context_windows.current_identity/GetCurrentProcess/GetProcessTimes"
    assert facts["mode"] == "passive" and facts["head"] == "a" * 40 and Path(facts["worktree"]) == root
    assert completed.returncode == (0 if passed else 1), output
    assert "INTERNALERROR" not in output and "PRIVATE_CAPTURE_MESSAGE" not in output
    assert [r["outcome"] for r in reports] == (["passed", "passed"] if passed else ["failed", "passed"])
    assert all(r["same_object"] and r["when"] == "call" for r in reports) and reports[1]["sections"] == []
    suite = ET.parse(root / "junit.xml").getroot().find("testsuite")
    assert suite is not None and suite.attrib["tests"] == "2" and suite.attrib["failures"] == ("0" if passed else "1")
    if directory is None:
        assert "ISSUE287_H5_" not in output and reports[0]["sections"] == []
    elif failure:
        assert "ISSUE287_H5_CAPTURE_INVALID" in output and reports[0]["sections"][-1][1] == "ISSUE287_H5_CAPTURE_INVALID"
        assert not (directory / facts["run_id"] / "h5").exists()
    else:
        from tests.support.h5_failure_capture import verify_h5_capture_bundle

        bundle = verify_h5_capture_bundle(directory / facts["run_id"] / "h5", expected_run_id=facts["run_id"],
            expected_head=facts["head"], expected_pid=facts["pid"], expected_creation_time=facts["creation_time"],
            expected_repository_root=root)
        assert len(bundle["observations"]) == 500 and bundle["receipt"]["mode"] == "passive"
        assert "ISSUE287_H5_CAPTURE_METRICS" in output and "ISSUE287_H5_CAPTURE_CAPTURED" in output
    prefix = "disabled" if directory is None else "enabled"
    for name in ("contract.json", "reports.json", "junit.xml"):
        with (root / f"{prefix}-{name}").open("xb") as handle:
            handle.write((root / name).read_bytes())
    with (root / f"{prefix}-execution.json").open("x", encoding="utf-8") as handle:
        json.dump({"command": completed.args, "exit_code": completed.returncode,
                   "stdout": completed.stdout, "stderr": completed.stderr}, handle)
    return completed, reports


def _h5_record_parent_retention(tmp_path, request, tmp_path_factory):
    """Observe local retention without changing the native contract's outcome."""
    try:
        ini_policy = request.config.getini("tmp_path_retention_policy")
        factory_policy = getattr(tmp_path_factory, "_retention_policy", None)
        policies = ("all", "failed", "none")
        facts = {
            "kind": "test-local-parent-retention-evidence",
            "ini_policy": ini_policy if ini_policy in policies else None,
            "factory_policy": factory_policy if factory_policy in policies else None,
            "parent": str(tmp_path.resolve(strict=True)),
        }
        (tmp_path / "retention.json").write_text(json.dumps(facts), encoding="utf-8")
    except Exception:
        pass  # Missing observational facts are assessed by the separate archive.


@_WINDOWS_H5_ONLY
@pytest.mark.parametrize("failure,passed", [("", False), ("write", False), ("verify", False), ("rename", False), ("write", True)])
def test_native_h5_capture_preserves_original_failure_and_later_test(tmp_path, monkeypatch, failure, passed, request, tmp_path_factory):
    from tests.support.h5_failure_capture import verify_h5_capture_bundle

    _h5_record_parent_retention(tmp_path, request, tmp_path_factory)
    test_h5_native_launcher_caller_inventory_is_complete()
    monkeypatch.delenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY", raising=False)
    root = _h5_native_fixture(tmp_path)
    directory = tmp_path / "capture"
    done, reports = _h5_native_run(root, directory, failure=failure, passed=passed)
    output = done.stdout + done.stderr
    assert done.returncode == (0 if passed else 1), output
    assert "INTERNALERROR" not in output and "PRIVATE_CAPTURE_MESSAGE" not in output
    assert [report["outcome"] for report in reports] == (["passed", "passed"] if passed else ["failed", "passed"])
    assert reports[1]["sections"] == [] and all(report["same_object"] for report in reports)
    suite = ET.parse(root / "junit.xml").getroot().find("testsuite")
    assert suite is not None and suite.attrib["tests"] == "2" and suite.attrib["failures"] == ("0" if passed else "1")
    if failure:
        assert "ISSUE287_H5_CAPTURE_INVALID" in output and reports[0]["sections"][-1][0] == "H5 in-suite capture"
    else:
        # Owned, bounded enumeration; no recursive repository walker or newest-session guess.
        run_names = os.listdir(directory)
        assert len(run_names) == 1
        run_id = run_names[0]
        facts = json.loads((root / "contract.json").read_text(encoding="utf-8"))
        bundle = verify_h5_capture_bundle(directory / run_id / "h5", expected_run_id=run_id, expected_head="a"*40,
            expected_pid=facts["pid"], expected_creation_time=facts["creation_time"], expected_repository_root=root)
        assert len(bundle["observations"]) == 500 and bundle["receipt"]["mode"] == "passive"
        assert "ISSUE287_H5_CAPTURE_METRICS" in output


@_WINDOWS_H5_ONLY
def test_capture_controls_never_touch_inherited_outer_base(tmp_path, monkeypatch, request, tmp_path_factory):
    _h5_record_parent_retention(tmp_path, request, tmp_path_factory)
    root = _h5_native_fixture(tmp_path)
    outer = tmp_path / "outer"
    outer.mkdir()
    (outer / "sentinel").write_bytes(b"preserve")
    monkeypatch.setenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY", str(outer))
    disabled, disabled_reports = _h5_native_run(root, None)
    enabled, enabled_reports = _h5_native_run(root, tmp_path / "child-capture")
    assert disabled.returncode == enabled.returncode == 1
    assert disabled_reports[0]["longrepr"] == enabled_reports[0]["longrepr"]
    assert disabled_reports[0]["sections"] == enabled_reports[0]["sections"] == []
    assert "ISSUE287_H5_" not in disabled.stdout
    disabled_facts = json.loads((root / "disabled-contract.json").read_text(encoding="utf-8"))
    enabled_facts = json.loads((root / "enabled-contract.json").read_text(encoding="utf-8"))
    assert (disabled_facts["pid"], disabled_facts["creation_time"]) != (enabled_facts["pid"], enabled_facts["creation_time"])
    assert disabled_facts["forbidden"] == enabled_facts["forbidden"] == {"start_run": 0, "prune_run_folders": 0, "repository_append": 0}
    assert (outer / "sentinel").read_bytes() == b"preserve" and os.listdir(outer) == ["sentinel"]
    assert os.environ["PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY"] == str(outer)


@pytest.mark.parametrize("node", ["target", "other"])
@pytest.mark.parametrize("declaration", ["relative-capture", "../capture"])
def test_malformed_capture_path_non_target_has_no_output(h5_capture_scope, monkeypatch, node, declaration):
    from tests.support import h5_failure_capture as capture

    plugin, context, directory = h5_capture_scope
    binding, result, calls = _h5_stub(monkeypatch)
    if node == "other":
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/unit/acp/test_other.py::test_other (call)")
    monkeypatch.setenv("PYTEST_OPTIMUS_H5_CAPTURE_DIRECTORY", declaration)
    events = []
    session = plugin.current_audit_session()
    def path(value):
        events.append("syntax")
        return Path(value)
    def current():
        events.append("session")
        return session
    monkeypatch.setattr(plugin, "Path", path)
    monkeypatch.setattr(plugin, "current_audit_session", current)
    monkeypatch.setattr(capture, "validate_capture_directory", lambda *a: pytest.fail("no filesystem admission"))
    monkeypatch.setattr(plugin, "_h5_utc_now", lambda: pytest.fail("no diagnostic timing"))
    actual = _h5_bridge(plugin)
    assert actual[0] is binding and actual[1] is result and len(calls) == 1
    assert events == ["syntax", "session"], "syntax must precede all candidate/state work"
    assert "h5_capture" not in session and session.get("h5_lines", []) == []
    assert _h5_report(plugin).sections == [("existing", "UNCHANGED")]
    assert not (directory / context.run_id).exists()


def test_h5_activation_token_is_item_and_call_scoped_and_cleared(h5_capture_scope, monkeypatch):
    plugin, _, _ = h5_capture_scope
    _h5_stub(monkeypatch)
    _h5_bridge(plugin)
    session = plugin.current_audit_session()
    token = session["h5_capture"]
    for node, phase in ((plugin._H5_TARGET, "setup"), ("tests/unit/acp/test_fixture.py::test_later", "call")):
        report = SimpleNamespace(sections=[], outcome="passed", when=phase, longrepr=None)
        hook = plugin.pytest_runtest_makereport(SimpleNamespace(nodeid=node), SimpleNamespace(when=phase))
        next(hook)
        with pytest.raises(StopIteration) as finished:
            hook.send(report)
        assert finished.value.value is report and report.sections == []
        assert session["h5_capture"] is token and "h5_lines" not in session
    token["phase"] = "setup"
    assert _h5_report(plugin).sections == [("existing", "UNCHANGED")]
    assert session.get("h5_capture") is token and "h5_lines" not in session
    token["phase"] = "call"
    _h5_report(plugin)
    assert "h5_capture" not in session
    lines = list(session["h5_lines"])
    assert _h5_report(plugin).sections == [("existing", "UNCHANGED")]
    assert _h5_report(plugin, nodeid="tests/unit/acp/test_fixture.py::test_later").sections == [("existing", "UNCHANGED")]
    assert session["h5_lines"] == lines


def _h5_launcher_callers(source):
    import ast
    tree = ast.parse(source)
    definitions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == "_h5_native_run"]
    assert len(definitions) == 1 and isinstance(definitions[0], ast.FunctionDef) and definitions[0] in tree.body
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            assert "_h5_native_run" not in node.names, "no scope rebinding"
        if isinstance(node, ast.arg):
            assert node.arg != "_h5_native_run", "no parameter rebinding"
        if isinstance(node, ast.alias):
            assert (node.asname or node.name) != "_h5_native_run", "no import rebinding"
        if isinstance(node, ast.Name) and node.id == "_h5_native_run":
            assert isinstance(node.ctx, ast.Load), "no rebinding"
            call = parents[node]
            assert isinstance(call, ast.Call) and call.func is node, "no alias or callback escape"
            owner = parents[call]
            while owner is not tree and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                owner = parents[owner]
            assert isinstance(owner, ast.FunctionDef) and owner in tree.body, "no module/class/nested caller"
            calls.append((owner.name, ast.unparse(call)))
    # ast.walk is breadth-first; source offsets preserve the exact reviewed caller order.
    calls.sort(key=lambda pair: next(n.lineno for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == pair[0]))
    return definitions, calls


@pytest.mark.usefixtures("h5_isolated_activation")
def test_h5_native_launcher_caller_inventory_is_complete():
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    definitions, calls = _h5_launcher_callers(Path(__file__).read_text(encoding="utf-8"))
    assert calls == [
        ("test_native_h5_capture_preserves_original_failure_and_later_test", "_h5_native_run(root, directory, failure=failure, passed=passed)"),
        ("test_capture_controls_never_touch_inherited_outer_base", "_h5_native_run(root, None)"),
        ("test_capture_controls_never_touch_inherited_outer_base", "_h5_native_run(root, tmp_path / 'child-capture')"),
    ]
    # Core's classification control must not reach a nested collection via fixture dependencies.
    fixtures = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)
                and any(ast.unparse(d).startswith("pytest.fixture") for d in n.decorator_list)}
    check = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == "test_h5_launching_nodes_have_explicit_reviewed_core_disposition")
    pending, visited = [arg.arg for arg in check.args.args], set()
    while pending:
        name = pending.pop()
        if name in visited or name not in fixtures:
            continue
        visited.add(name)
        fixture = fixtures[name]
        assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                       and n.func.id in {"_pytest", "_h5_native_run"} for n in ast.walk(fixture)), "core fixture must not launch pytest"
        pending.extend(arg.arg for arg in fixture.args.args)
    launches = [n for n in ast.walk(definitions[0]) if isinstance(n, ast.Call) and ast.unparse(n.func) == "subprocess.run"]
    assert len(launches) == 1
    primary = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == calls[0][0])
    decorator = next(n for n in primary.decorator_list if isinstance(n, ast.Call))
    assert ast.literal_eval(decorator.args[1]) == [("", False), ("write", False), ("verify", False), ("rename", False), ("write", True)]
    factory = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_h5_native_fixture")
    program = next(n.value for n in ast.walk(factory) if isinstance(n, ast.Constant) and isinstance(n.value, str) and "pytest_plugins" in n.value)
    child = ast.parse(program)
    statements = [ast.unparse(n) for n in child.body]
    helper_import = next(i for i,s in enumerate(statements) if "from tests.unit.tools.test_test_profiles import" in s)
    for assignment in ("run_context.start_run =", "run_context_records.prune_run_folders =", "run_context._append ="):
        assert any(s.startswith(assignment) for s in statements[:helper_import]), assignment
    assert "current_identity()" in program and "123456" not in program


_H5_UNTRACKED = ("tests/support/h5_failure_capture.py", "tests/unit/tools/test_h5_failure_capture.py")


def _h5_check_untracked_source(relative, source):
    """Bounded direct-source checks supplement the tracked guards' alias limits."""
    import ast

    from tests.unit.guardrails.test_tracked_file_scanners import _walker_calls_from_source

    tree = ast.parse(source)
    assert not _walker_calls_from_source(relative, source)
    aliases = {}
    banned_modules = {"subprocess", "multiprocessing", "asyncio", "ctypes", "importlib", "tools.process_tree"}
    admitted_imports = {
        "__future__.annotations", "copy", "json", "os", "re", "stat", "sys", "tempfile", "time", "pytest", "_winapi",
        "collections.Counter", "collections.abc.Mapping", "dataclasses.dataclass", "dataclasses.fields",
        "datetime.UTC", "datetime.datetime", "pathlib.Path", "types.SimpleNamespace", "typing.Any",
        "jsonschema.Draft202012Validator", "tests.support.h5_failure_capture",
        "tools.plan1126_runtime_audit.evidence_store", "tools.plan1126_runtime_audit.shutdown",
        "tools.plan1126_runtime_audit.measurement.EnvironmentBinding", "tools.plan1126_runtime_audit.shutdown.CloseSite",
        "tools.plan1126_runtime_audit.shutdown.ResourceOwnershipRecord", "tools.plan1126_runtime_audit.shutdown.ShutdownScheduleObservation",
        "tools.plan1126_runtime_audit.source.ExecutingSourceMismatch", "tools.testing.run_context.RunContext",
        "tools.testing.run_context_records.COMMIT", "tools.testing.run_context_records.RUN_ID",
    }
    helper_imports = {
        "tests.unit.tools.plan1126_runtime_audit.test_current_measurement._budget_tempfile_facade",
        "tests.unit.tools.plan1126_runtime_audit.test_current_measurement._pad_budget_directory",
    } if relative == _H5_UNTRACKED[1] else set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in admitted_imports, "unreviewed import"
                assert not any(alias.name == m or alias.name.startswith(m + ".") for m in banned_modules)
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None and all(a.name != "*" for a in node.names)
            assert not any(node.module == m or node.module.startswith(m + ".") for m in banned_modules)
            for alias in node.names:
                assert node.level == 0 and node.module + "." + alias.name in (
                    admitted_imports | helper_imports
                ), "unreviewed import/re-export"
                aliases[alias.asname or alias.name] = node.module + "." + alias.name
    def name(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return name(node.value) + "." + node.attr
        return ""
    inert = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "exec"
             and len(n.args) == 2 and not n.keywords and isinstance(n.args[1], ast.Dict) and not n.args[1].keys
             and isinstance(n.args[0], ast.Call) and isinstance(n.args[0].func, ast.Name) and n.args[0].func.id == "compile"
             and not n.args[0].keywords and len(n.args[0].args) == 3
             and isinstance(n.args[0].args[0], ast.Constant) and n.args[0].args[0].value == "raise OSError(5, 'PRIVATE_MESSAGE')"
             and isinstance(n.args[0].args[1], ast.Name) and n.args[0].args[1].id == "filename"
             and isinstance(n.args[0].args[2], ast.Constant) and n.args[0].args[2].value == "exec"]
    assert len(inert) <= (1 if relative == _H5_UNTRACKED[1] else 0)
    allowed_dynamic = {id(n.func) for call in inert for n in (call, call.args[0])}
    dangerous = {"system", "popen", "startfile", "CreateProcess", "ShellExecute", "stdio_client", "StdioServerParameters",
                 "vars", "__dict__", "modules", "importorskip"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute)):
            spelled = name(node)
            tail = spelled.rsplit(".", 1)[-1]
            assert not (tail in dangerous or tail.startswith(("CreateProcess", "ShellExecute", "create_subprocess"))
                        or tail in {"glob", "iglob", "rglob", "iterdir", "listdir", "scandir", "fork", "forkpty"}
                        or (tail == "walk" and spelled != "ast.walk")
                        or (spelled.startswith("os.") and tail.startswith(("spawn", "exec", "posix_spawn"))))
            assert not (spelled.startswith("_winapi.") and spelled != "_winapi.CreateJunction")
            if tail in {"exec", "eval", "compile", "__import__"}:
                assert id(node) in allowed_dynamic
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                assert node.id not in aliases and node.id not in {"exec", "eval", "compile", "__import__"}
        if isinstance(node, ast.Call) and name(node.func) == "getattr":
            assert (not node.keywords and len(node.args) == 3 and ast.unparse(node.args[0]) == "info"
                    and isinstance(node.args[1], ast.Constant) and node.args[1].value == "st_file_attributes"
                    and isinstance(node.args[2], ast.Constant) and node.args[2].value == 0), "dynamic attribute lookup"


def _h5_recognized_untracked(monkeypatch, sources):
    from tests.support import child_launch_inventory

    paths = tuple(_ROOT / relative for relative in _H5_UNTRACKED)
    real_read = Path.read_text
    with monkeypatch.context() as scoped:
        scoped.setattr(child_launch_inventory, "tracked_repository_files", lambda *a, **kw: paths)
        scoped.setattr(Path, "read_text", lambda path, *a, **kw: sources[path.relative_to(_ROOT).as_posix()]
                       if path in paths else real_read(path, *a, **kw))
        return child_launch_inventory.launch_sites(_ROOT)


@pytest.mark.usefixtures("h5_isolated_activation")
def test_h5_untracked_files_have_no_launch_or_scanner_sites(monkeypatch):
    sources = {relative: (_ROOT / relative).read_text(encoding="utf-8") for relative in _H5_UNTRACKED}
    assert not _h5_recognized_untracked(monkeypatch, sources)
    for relative, source in sources.items():
        _h5_check_untracked_source(relative, source)


@pytest.mark.usefixtures("h5_isolated_activation")
@pytest.mark.parametrize("relative,source,accepted", [
    pytest.param(_H5_UNTRACKED[1], "from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import _budget_tempfile_facade", True, id="facade"),
    pytest.param(_H5_UNTRACKED[1], "from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import _pad_budget_directory", True, id="padding"),
    pytest.param(_H5_UNTRACKED[1], "from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import _budget_tempfile_facade, _pad_budget_directory", True, id="both"),
    pytest.param(_H5_UNTRACKED[1], "from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import _budget_tempfile_facade as facade, _pad_budget_directory as padding", True, id="aliases"),
    pytest.param(_H5_UNTRACKED[0], "from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import _budget_tempfile_facade", False, id="support-facade"),
    pytest.param(_H5_UNTRACKED[0], "from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import _pad_budget_directory", False, id="support-padding"),
    pytest.param(_H5_UNTRACKED[1], "from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import *", False, id="star"),
    pytest.param(_H5_UNTRACKED[1], "import tests.unit.tools.plan1126_runtime_audit.test_current_measurement", False, id="module"),
    pytest.param(_H5_UNTRACKED[1], "import tests.unit.tools.plan1126_runtime_audit.test_current_measurement as hidden", False, id="module-alias"),
    pytest.param(_H5_UNTRACKED[1], "import tests.unit.tools.plan1126_runtime_audit.test_current_measurement._budget_tempfile_facade", False, id="dotted-facade"),
    pytest.param(_H5_UNTRACKED[1], "import tests.unit.tools.plan1126_runtime_audit.test_current_measurement._pad_budget_directory", False, id="dotted-padding"),
    pytest.param(_H5_UNTRACKED[1], "from tests.unit.tools.plan1126_runtime_audit import test_current_measurement", False, id="parent-reexport"),
    pytest.param(_H5_UNTRACKED[1], "from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import _tree", False, id="unknown-helper"),
    pytest.param(_H5_UNTRACKED[1], "from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import run_fresh_measurement", False, id="measurement"),
    pytest.param(_H5_UNTRACKED[1], "from tests.unit.tools.plan1126_runtime_audit.test_current_measurement import _budget_tempfile_facade, _tree", False, id="mixed"),
])
def test_h5_budget_helper_imports_are_scoped(relative, source, accepted):
    if accepted:
        _h5_check_untracked_source(relative, source)
    else:
        with pytest.raises(AssertionError):
            _h5_check_untracked_source(relative, source)


@pytest.mark.usefixtures("h5_isolated_activation")
def test_h5_untracked_file_check_detects_forbidden_sites(monkeypatch):
    sources = {relative: "" for relative in _H5_UNTRACKED}
    sources[_H5_UNTRACKED[0]] = "import subprocess\ndef bad(): subprocess.run(['python', '-c', 'pass'])"
    sites = _h5_recognized_untracked(monkeypatch, sources)
    assert [site["key"] for site in sites] == [_H5_UNTRACKED[0] + "::bad#1"]
    for source in (
        sources[_H5_UNTRACKED[0]], "from subprocess import run as hidden\nhidden([])",
        "import os as hidden\nhidden.system('ignored')", "from os import spawnv as hidden\nhidden(0, 'x', [])",
        "import multiprocessing as hidden\nhidden.Process()", "import _winapi\n_winapi.CreateProcess()",
        "import ctypes\nctypes.windll.kernel32.CreateProcessW()", "from pathlib import Path\nPath('.').rglob('*')",
        "import os as hidden\nhidden.listdir('.')", "eval('ignored')", "f = exec\nf('ignored')",
        "exec(compile('import subprocess', filename, 'exec'), {})", "import importlib\nimportlib.import_module('subprocess')",
        "import os\ngetattr(os, 'system')('ignored')", "from unknown_launcher import launch\nlaunch()",
    ):
        with pytest.raises(AssertionError):
            _h5_check_untracked_source(_H5_UNTRACKED[1], source)


def test_h5_fixture_keeps_outer_recorder_context(h5_capture_scope):
    from tools.testing import run_context
    _, synthetic, _ = h5_capture_scope
    assert run_context.current() is not synthetic
    assert run_context.current() is not None


@_WINDOWS_H5_ONLY
@pytest.mark.parametrize("site", ["admission_import", "returned_import", "status_constructor"])
def test_h5_diagnostic_import_and_constructor_errors_are_contained(h5_capture_scope, monkeypatch, site):
    import builtins

    from tests.support import h5_failure_capture as capture
    plugin, _, _ = h5_capture_scope
    binding, result, calls = _h5_stub(monkeypatch)
    real_import = builtins.__import__
    def fail_import(name, *args, **kwargs):
        if name == "tests.support.h5_failure_capture":
            raise ImportError("PRIVATE_IMPORT")
        return real_import(name, *args, **kwargs)
    if site == "admission_import":
        with monkeypatch.context() as scoped:
            scoped.setattr(builtins, "__import__", fail_import)
            actual = _h5_bridge(plugin)
        assert actual[0] is binding and actual[1] is result and len(calls) == 1
        assert "h5_capture" not in plugin.current_audit_session()
        assert _h5_report(plugin).sections == [("existing", "UNCHANGED")]
    else:
        if site == "status_constructor":
            def fail_status(*args, **kwargs):
                raise RuntimeError("PRIVATE_CONSTRUCTOR")
            monkeypatch.setattr(capture, "CaptureStatus", fail_status)
        # Fail the post-measurement import at its real bridge point, after admission succeeds.
        if site == "returned_import":
            def measure(**kwargs):
                calls.append(kwargs)
                monkeypatch.setattr(builtins, "__import__", fail_import)
                return binding, result, None
            from tools.plan1126_runtime_audit import measurement
            monkeypatch.setattr(measurement, "session_measurement_reuse", lambda: SimpleNamespace(measure=measure))
        actual = _h5_bridge(plugin)
        monkeypatch.setattr(builtins, "__import__", real_import)
        assert actual[0] is binding and actual[1] is result and len(calls) == 1
        assert _h5_report(plugin).sections[-1] == ("H5 in-suite capture", "ISSUE287_H5_CAPTURE_INVALID")
        assert "PRIVATE_" not in str(plugin.current_audit_session().get("h5_lines", []))


@_WINDOWS_H5_ONLY
def test_h5_duplicate_call_preserves_first_status_and_bundle(h5_capture_scope, monkeypatch):
    plugin, context, directory = h5_capture_scope
    binding, result, calls = _h5_stub(monkeypatch, earlier="tests/unit/acp/test_fixture.py::test_earlier")
    first = _h5_bridge(plugin)
    original = (directory / context.run_id / "h5/capture.json").read_bytes()
    second = _h5_bridge(plugin)
    assert first[0] is second[0] is binding and first[1] is second[1] is result
    assert len(calls) == 2 and len(plugin.current_audit_session()["reused"]) == 2
    assert (directory / context.run_id / "h5/capture.json").read_bytes() == original
    _h5_report(plugin)
    lines = plugin.current_audit_session()["h5_lines"]
    assert [line for line in lines if not line.startswith("ISSUE287_H5_CAPTURE_METRICS")] == [
        "ISSUE287_H5_CAPTURE_CAPTURED", "ISSUE287_H5_CAPTURE_INVALID"]
    assert "h5_capture" not in plugin.current_audit_session()


@pytest.mark.parametrize("escape", ["alias = _h5_native_run", "class Escape:\n    alias = _h5_native_run", "class _h5_native_run: pass", "def escape():\n    global _h5_native_run\n    _h5_native_run = None"])
def test_h5_launcher_inventory_rejects_outside_and_rebound_references(escape):
    with pytest.raises(AssertionError):
        _h5_launcher_callers("def _h5_native_run(): pass\n" + escape)


@pytest.mark.parametrize("source", [
    "import sys\nsys.modules['subprocess'].run([])",
    "import os\nvars(os)['system']('ignored')",
    "import os\nos.__dict__['system']('ignored')",
    "import pytest\npytest.importorskip('subprocess').run([])",
])
def test_h5_untracked_checker_rejects_namespace_escapes(source):
    with pytest.raises(AssertionError):
        _h5_check_untracked_source(_H5_UNTRACKED[0], source)


def test_h5_launching_nodes_have_explicit_reviewed_core_disposition(manifest):
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    primary = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == "test_native_h5_capture_preserves_original_failure_and_later_test")
    parameterize = next(n for n in primary.decorator_list if isinstance(n, ast.Call)
                        and ast.unparse(n.func) == "pytest.mark.parametrize")
    assert ast.literal_eval(parameterize.args[0]) == "failure,passed"
    cases = ast.literal_eval(parameterize.args[1])
    nodes = tuple(f"tests/unit/tools/test_test_profiles.py::{primary.name}[{failure}-{passed}]"
                  for failure, passed in cases) + (
        "tests/unit/tools/test_test_profiles.py::test_capture_controls_never_touch_inherited_outer_base",
    )
    actual = profiles.classify_nodes(nodes, manifest).tiers
    assert len(actual) == 6 and set(actual.values()) == {"core"}
    rationale = _REVIEWED_CHEAP_LAUNCHERS["tests/unit/tools/test_test_profiles.py"]
    assert rationale != _MIXED and "synthetic passive" in rationale and "never the H5 probe" in rationale
