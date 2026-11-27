"""Children that repository code launches (helper-owned launches) never reach the host keyring (#661, residual of #540).

#540 gave every launch written in `tests/` a verdict. A child that a test starts by calling code in `src/` or `tools/` is
not written in `tests/`: this guard reads the launches in those two directories and holds each function that starts a
process to a verdict in `helper_launches.json`, each checked against the source it describes. A launch added anywhere
without a verdict fails here; a launch that begins to run product code that reaches keyring fails its verdict's check.
"""

from __future__ import annotations

import ast
import json
import os
import textwrap
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from tests.support import child_keyring
from tests.support.helper_launch_inventory import launch_functions, scan_source
from tools.tracked_repository_files import tracked_repository_files

_ROOT = Path(__file__).resolve().parents[3]
_MAP = Path(__file__).with_name("helper_launches.json")


def _document() -> dict:
    return json.loads(_MAP.read_text(encoding="utf-8"))


def _source_of(key: str) -> str:
    """The function's source, or the whole module for a module-level launch."""
    relative, _, function = key.partition("::")
    source = (_ROOT / relative).read_text(encoding="utf-8")
    if function == "<module>":
        return source
    nodes = [node for node in ast.walk(ast.parse(source)) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function]
    return textwrap.dedent("\n".join(" " * node.col_offset + (ast.get_source_segment(source, node) or "") for node in nodes))


def _launch_calls(source: str) -> list[ast.Call]:
    """The launch calls in a function's source."""
    return [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call) and ast.unparse(node.func).split(".")[-1] in {
        "Popen", "run", "check_output", "check_call", "call", "popen", "run_bounded"}]


def _launch_programs(source: str) -> list[str]:
    """The first argument of each launch call in a function's source, as written."""
    return [ast.unparse(call.args[0]) for call in _launch_calls(source) if call.args]


def _test_module_names() -> dict[str, tuple[set[str], set[str]]]:
    """For each tracked test module: every identifier and attribute it uses, and the names it calls."""
    modules: dict[str, tuple[set[str], set[str]]] = {}
    for path in tracked_repository_files(_ROOT, pathspecs=["tests"]):
        if path.name.startswith("test_") and path.suffix == ".py":
            tree = ast.parse(path.read_text(encoding="utf-8"))
            used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            called = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr for node in ast.walk(tree)
                      if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))}
            modules[path.relative_to(_ROOT).as_posix()] = (used, called)
    return modules


def problems(
    found: Mapping[str, Mapping[str, object]], document: Mapping[str, object], *,
    source_of: Callable[[str], str] = _source_of, test_modules: Mapping[str, tuple[set[str], set[str]]] | None = None,
    exists: Callable[[str], bool] = lambda relative: (_ROOT / relative).is_file(),
) -> list[str]:
    """Every way the map and the sources disagree; empty when each launch function has a verdict its check confirms."""
    found_problems: list[str] = []
    functions = document["functions"]
    verdicts = document["verdicts"]
    for key in sorted(set(found) - set(functions)):
        found_problems.append(f"{key}: a launch with no verdict (#661); classify it in helper_launches.json")
    for key in sorted(set(functions) - set(found)):
        found_problems.append(f"{key}: listed, but the function no longer launches anything")
    for key in sorted(set(found) & set(functions)):
        entry = functions[key]
        verdict = entry.get("verdict")
        if verdict not in verdicts:
            found_problems.append(f"{key}: unknown verdict {verdict!r}")
            continue
        if entry.get("launches") != found[key]["count"]:
            found_problems.append(f"{key}: holds {found[key]['count']} launch references, the map records {entry.get('launches')}")
        for test in entry.get("reached_by", []):
            if not exists(test):
                found_problems.append(f"{key}: reached_by names a file that does not exist: {test}")
        source = source_of(key)
        if verdict == "non_python":
            tools = entry.get("tools") or []
            missing = [tool for tool in tools if tool.lower() not in source.lower()]
            if not tools or missing:
                found_problems.append(f"{key}: non_python needs tools that the function names (missing {missing or 'all'})")
        elif verdict == "closure_clear":
            unnamed = [name for name in entry.get("entries") or [] if name.rpartition(".")[2] not in source]
            if unnamed or not entry.get("entries"):
                found_problems.append(f"{key}: closure_clear entries {unnamed or 'missing'} are not what the function launches")
            closure = child_keyring.import_closure(entry.get("entries") or ["<none>"])
            if closure["keyring_importers"] or closure["unbounded"]:
                found_problems.append(f"{key}: the child's closure imports keyring {closure['keyring_importers']} or is unbounded {closure['unbounded']}")
        elif verdict == "nested_pytest":
            if "pytest" not in (_module_text(key) if source_of is _source_of else source_of(key)):
                found_problems.append(f"{key}: nested_pytest, but its module builds no pytest command")
        elif verdict == "caller_program":
            named = [program for program in _launch_programs(source) if "sys.executable" in program]
            if named:
                found_problems.append(f"{key}: caller_program, but a launch names its own program: {named}")
        elif verdict == "controlled":
            control, calls = entry.get("control"), entry.get("entry_calls") or []
            if not control or not hasattr(child_keyring, control) or not calls:
                found_problems.append(f"{key}: controlled needs a control that child_keyring defines and the calls that reach it")
            else:
                if control == "control_inherited_children" and any(
                        keyword.arg == "env" or keyword.arg is None for call in _launch_calls(source) for keyword in call.keywords):
                    found_problems.append(f"{key}: the control relies on the child inheriting the environment, but a launch passes env=")
                for module, (used, called) in (test_modules if test_modules is not None else _test_module_names()).items():
                    if used & set(calls) and control not in called:
                        found_problems.append(f"{key}: {module} reaches the launch without calling {control}")
        elif verdict in {"not_reached", "wrapper"}:
            if len(str(entry.get("reason", ""))) < 30:
                found_problems.append(f"{key}: {verdict} needs a reason that says what the tests do instead or what launch it forwards")
    return found_problems


def _module_text(key: str) -> str:
    return (_ROOT / key.partition("::")[0]).read_text(encoding="utf-8")


def test_every_launch_in_src_and_tools_has_a_verdict_that_its_check_confirms() -> None:
    assert problems(launch_functions(_ROOT), _document()) == []


def test_the_map_describes_what_the_census_recorded() -> None:
    document = _document()
    reached = {key: entry for key, entry in document["functions"].items() if entry.get("reached_by")}
    assert reached, "the census found launches that default-selection tests reach"
    # The one reached child that runs product code reaching keyring is the measurement child, and it is controlled.
    assert document["functions"]["tools/plan1126_runtime_audit/measurement.py::run_fresh_measurement"]["verdict"] == "controlled"
    assert {entry["verdict"] for entry in reached.values()} <= {"closure_clear", "controlled", "caller_program", "nested_pytest", "not_reached"}


# Mutation controls: each change a reviewer could make wrongly, and the check that must catch it.
_FOUND = {"tools/x.py::go": {"count": 1, "names": ["subprocess.run"]}}


def _document_for(entry: dict, verdicts: tuple[str, ...] = ("non_python", "closure_clear", "nested_pytest", "caller_program", "controlled", "not_reached")) -> dict:
    return {"verdicts": dict.fromkeys(verdicts, ""), "functions": {"tools/x.py::go": {"launches": 1, **entry}}}


def _problems(entry: dict, source: str = "subprocess.run(['git'])", **options: object) -> list[str]:
    return problems(_FOUND, _document_for(entry), source_of=lambda _key: source, **options)  # type: ignore[arg-type]


def test_a_launch_function_without_a_verdict_fails() -> None:
    new = scan_source("tools/y.py", "import subprocess\ndef go():\n    subprocess.run(['x'])\n")
    assert problems(new, {"verdicts": {}, "functions": {}})[0].endswith("a launch with no verdict (#661); classify it in helper_launches.json")


def test_a_removed_verdict_and_a_function_that_stopped_launching_both_fail() -> None:
    document = _document()
    found = launch_functions(_ROOT)
    victim = next(iter(document["functions"]))
    without = {**document, "functions": {key: value for key, value in document["functions"].items() if key != victim}}
    assert any(victim in text and "no verdict" in text for text in problems(found, without))
    gone = {key: value for key, value in found.items() if key != victim}
    assert any(victim in text and "no longer launches" in text for text in problems(gone, document))


def test_a_second_launch_in_a_listed_function_fails() -> None:
    document = _document()
    found = launch_functions(_ROOT)
    victim = next(key for key, entry in found.items() if entry["count"] == 1)
    grown = {**found, victim: {"count": 2, "names": []}}
    assert any(victim in text and "launch references" in text for text in problems(grown, document))


def test_an_unknown_verdict_fails() -> None:
    assert _problems({"verdict": "assumed_fine"})[0].endswith("unknown verdict 'assumed_fine'")


def test_non_python_fails_when_the_function_does_not_name_its_tool() -> None:
    assert _problems({"verdict": "non_python", "tools": ["docker"]}) != []
    assert _problems({"verdict": "non_python", "tools": ["git"]}) == []


def test_closure_clear_fails_for_a_child_whose_closure_imports_keyring() -> None:
    assert _problems({"verdict": "closure_clear", "entries": ["optimus.acp.launch_gate"]}) != []
    assert _problems({"verdict": "closure_clear", "entries": ["evidence_handoff_runtime.service_cli"]},
                     source="subprocess.run([sys.executable, '-m', 'evidence_handoff_runtime.service_cli'])") == []


def test_caller_program_fails_when_the_function_names_its_own_python() -> None:
    assert _problems({"verdict": "caller_program"}, source="subprocess.run([sys.executable, '-m', 'optimus.acp'])") != []
    assert _problems({"verdict": "caller_program"}, source="subprocess.run(argv)") == []


def test_controlled_fails_for_a_test_module_that_reaches_the_launch_without_the_control() -> None:
    entry = {"verdict": "controlled", "control": "control_inherited_children", "entry_calls": ["run_contained"]}
    assert _problems(entry, test_modules={"tests/a.py": ({"run_contained"}, set())}) != []
    assert _problems(entry, test_modules={"tests/a.py": ({"run_contained", "control_inherited_children"}, set())}) != [], "named, never called"
    assert _problems(entry, test_modules={"tests/a.py": ({"run_contained"}, {"control_inherited_children"})}) == []
    assert _problems({**entry, "control": "no_such_control"}, test_modules={}) != []


def test_an_inherited_control_fails_when_the_launch_passes_its_own_environment() -> None:
    entry = {"verdict": "controlled", "control": "control_inherited_children", "entry_calls": ["run_contained"]}
    assert _problems(entry, source="subprocess.run(argv, env={'PATH': ''})", test_modules={}) != []
    assert _problems(entry, source="subprocess.run(argv)", test_modules={}) == []


def test_closure_clear_fails_when_the_function_no_longer_launches_the_listed_module() -> None:
    entry = {"verdict": "closure_clear", "entries": ["evidence_handoff_runtime.service_cli"]}
    assert _problems(entry, source="subprocess.run([sys.executable, '-m', 'optimus.acp'])") != []
    assert _problems(entry, source="subprocess.run([sys.executable, '-m', 'evidence_handoff_runtime.service_cli'])") == []


def test_not_reached_needs_its_reason_and_reached_by_needs_real_files() -> None:
    assert _problems({"verdict": "not_reached", "reason": "no"}) != []
    assert _problems({"verdict": "non_python", "tools": ["git"], "reached_by": ["tests/missing.py"]}, exists=lambda _file: False) != []


def test_the_scan_counts_launches_and_references_but_not_annotations_or_type_checks() -> None:
    source = (
        "import subprocess\n"
        "from optimus.runtime.process_tree import popen\n"
        "def kept(process: subprocess.Popen[str] | None = None, run=subprocess.run) -> subprocess.Popen:\n"
        "    return isinstance(process, subprocess.Popen)\n"
        "def called():\n"
        "    factory = subprocess.Popen\n"
        "    return popen(['x'])\n"
    )
    found = scan_source("tools/z.py", source)
    assert {key: entry["count"] for key, entry in found.items()} == {"tools/z.py::kept": 1, "tools/z.py::called": 2}


def test_the_inherited_control_selects_fail_for_the_test_only() -> None:
    before = os.environ.get(child_keyring.VARIABLE)
    with pytest.MonkeyPatch.context() as scoped:
        child_keyring.control_inherited_children(scoped)
        assert os.environ[child_keyring.VARIABLE] == child_keyring.FAIL_BACKEND
    assert os.environ.get(child_keyring.VARIABLE) == before
