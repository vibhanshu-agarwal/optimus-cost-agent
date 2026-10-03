"""Every default-selection child launch site is mapped to a proof, and the census hook is sensitive.

The run context guards the pytest process, not its children. A child is covered by proof instead:
its own guard, a tripwire the test loads, or an ordinary-run census in which no child asked for the
real known folders. The map in `run_context_child_sites.json` says which, per launch site. This
module keeps that map complete and shows that the census hook cannot pass by being absent.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.child_launch_inventory import default_python_sites

_ROOT = Path(__file__).resolve().parents[3]
_MAP = Path(__file__).with_name("run_context_child_sites.json")
_HOOK = _ROOT / "tests" / "support" / "child_census"
_ordinary = pytest.mark.skipif(
    getattr(sys, "_main5_guard_activated", False), reason="the MAIN-5 guard owns every child's adapter there"
)


def _defined_functions(relative: str) -> set[str]:
    tree = ast.parse((_ROOT / relative).read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_every_default_launch_site_is_mapped_to_a_proof() -> None:
    document = json.loads(_MAP.read_text(encoding="utf-8"))
    mapped, dispositions = document["sites"], document["dispositions"]
    found = {str(site["key"]): site for site in default_python_sites(_ROOT)}
    assert sorted(set(found) - set(mapped)) == [], "new launch sites: classify each in run_context_child_sites.json"
    assert sorted(set(mapped) - set(found)) == [], "the map lists launch sites that no longer exist"
    for key, entry in mapped.items():
        assert entry["disposition"] in dispositions, key
        assert entry["mechanism"] == found[key]["mechanism"], key
        proof_file, _, proof_test = str(entry["proof"]).partition("::")
        assert proof_test.split("[")[0] in _defined_functions(proof_file), f"{key}: the proof test does not exist"
        assert entry["basis"], key
        if entry["disposition"] == "literal_program":
            # A literal `-c` program with no product import: it cannot reach the resolver.
            command = str(found[key]["command"])
            assert "'-c'" in command and "optimus" not in command and "tools" not in command, key
        if entry["disposition"] == "posix_only_caller":
            source = (_ROOT / str(found[key]["file"])).read_text(encoding="utf-8")
            helper = source.index(f"    def {found[key]['function']}(")
            assert 'os.name == "nt"' in source[max(0, helper - 1200):helper], f"{key}: the enclosing test does not skip on Windows"
        if entry["disposition"] == "runner_only_plant":
            # The plant really is skipped in an ordinary run, and its program is a literal.
            source = (_ROOT / str(found[key]["file"])).read_text(encoding="utf-8")
            assert f"def {found[key]['function']}() -> None:\n    _main5_runner_probe(" in source, key


def completed_pid(completed: subprocess.CompletedProcess[str]) -> int:
    return int(completed.stdout.split("PID=", 1)[1].split()[0])


def _census_child(tmp_path: Path, program: str, *, hooked: bool = True) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
    """Launch `python -c` with the census hook on PYTHONPATH, the way a census run exposes every child."""
    rows = tmp_path / "rows"
    rows.mkdir(exist_ok=True)
    environment = {name: value for name, value in os.environ.items() if name != "OPTIMUS_TEST_CHILD_CENSUS_DIR"}
    environment["PYTHONPATH"] = os.pathsep.join([str(_HOOK), str(_ROOT / "src"), str(_ROOT)])
    if hooked:
        environment["OPTIMUS_TEST_CHILD_CENSUS_DIR"] = str(rows)
    completed = subprocess.run(
        [sys.executable, "-c", "import os; print('PID=' + str(os.getpid()))\n" + program],
        cwd=_ROOT, env=environment, capture_output=True, text=True, timeout=120, check=False,
    )
    events = [json.loads(line) for file in sorted(rows.glob("*.jsonl")) for line in file.read_text(encoding="utf-8").splitlines()]
    return completed, events


_ASKS_FOR_REAL_FOLDERS = (
    "from optimus.acp import trusted_paths\n"
    "try:\n"
    "    trusted_paths.resolve_trusted_operator_roots(platform_name='win32')\n"
    "    print('RESOLVED')\n"
    "except BaseException as error:\n"
    "    print('REFUSED=' + type(error).__name__)\n"
)


@_ordinary
def test_the_census_hook_refuses_and_attributes_a_real_adapter_request(tmp_path: Path) -> None:
    completed, events = _census_child(tmp_path, _ASKS_FOR_REAL_FOLDERS)
    assert "REFUSED=" in completed.stdout and "RESOLVED" not in completed.stdout, completed.stdout + completed.stderr
    assert [event["event"] for event in events] == ["start", "trusted_paths_imported", "real_adapter_call", "end"]
    assert events[-1]["real_adapter_calls"] == 1 and events[-1]["is_pytest"] is False
    # The start row carries the child's own identity and its parent; the import row says it was armed.
    assert events[0]["armed"] is True and events[0]["pid"] == completed_pid(completed) and events[1]["armed"] is True
    assert isinstance(events[0]["creation_time"], int) and isinstance(events[0]["ppid"], int)
    assert isinstance(events[0]["parent_creation_time"], int)
    # The row names the test that was running when the child started.
    assert all("test_the_census_hook_refuses_and_attributes_a_real_adapter_request" in str(event["test"]) for event in events)


@_ordinary
def test_the_census_hook_records_a_clean_child_and_is_inert_when_not_asked(tmp_path: Path) -> None:
    completed, events = _census_child(tmp_path, "print('RAN')")
    assert completed.returncode == 0 and "RAN" in completed.stdout
    assert [event["event"] for event in events] == ["start", "end"]
    assert (events[-1]["trusted_paths_imported"], events[-1]["real_adapter_calls"]) == (False, 0)
    # Without the census variable the hook does nothing at all: the program resolves nothing here
    # either, because it only checks that the adapter is still the product's own.
    unhooked, none = _census_child(
        tmp_path / "unhooked" if (tmp_path / "unhooked").mkdir() is None else tmp_path,
        "from optimus.acp import trusted_paths\nprint(trusted_paths._real_windows_known_folders.__module__)", hooked=False,
    )
    assert none == [] and unhooked.stdout.split()[-1] == "optimus.acp.trusted_paths", unhooked.stdout + unhooked.stderr


# --- R5: a site is credited only by its own launches, and a launch only by the child it started.

_LAUNCHING_PROGRAM = """
import os, subprocess, sys
code = "import subprocess, sys; subprocess.run([sys.executable, '-c', 'print(1)'], check=True)"
exec(compile(code, "/w/tests/unit/tools/fake_site_module.py", "exec"), {"__name__": "fake_site"})
subprocess.run([sys.executable, "-c", "print(2)"], check=True, env={"PATH": os.environ["PATH"]})
try:
    subprocess.run(["no-such-program-" + os.urandom(4).hex()])
except OSError:
    print("LAUNCH_FAILED")
"""


@_ordinary
@pytest.mark.parametrize("started_by", ["launcher", "base_interpreter"])
def test_the_census_hook_binds_each_launch_to_the_child_it_started(tmp_path: Path, started_by: str) -> None:
    """Through the venv launcher the hooked interpreter is one hop below the launched process; started
    directly, it is that process. Both bindings carry the full identity, read on both sides."""
    from tests.support.child_census import attribution

    base = getattr(sys, "_base_executable", sys.executable)
    if started_by == "base_interpreter" and (os.name != "nt" or base == sys.executable):
        pytest.skip("no separate venv launcher on this platform")
    with pytest.MonkeyPatch.context() as patched:
        if started_by == "base_interpreter":
            patched.setattr(sys, "executable", base)  # the whole tree below is then started without the launcher
        completed, events = _census_child(tmp_path, _LAUNCHING_PROGRAM)
    assert completed.returncode == 0 and "LAUNCH_FAILED" in completed.stdout, completed.stdout + completed.stderr
    launcher = completed_pid(completed)
    launches = [event for event in events if event["event"] == "launch" and event["pid"] == launcher]
    assert [(launch["site_file"], launch["site_function"], launch["hook_env"], launch["launch"]) for launch in launches] == [
        ("tests/unit/tools/fake_site_module.py", "<module>", True, 1), (None, None, False, 2), (None, None, True, 3)]
    assert all("test_the_census_hook_binds_each_launch" in str(launch["launching_test"]) for launch in launches)
    # The first launch names the process it created; the hooked child wrote its own start row with its
    # identity and its parent's. Through the venv launcher the hooked interpreter is one hop below the
    # launched process; elsewhere it is that process.
    hooked, unhooked, failed = launches
    assert failed["child"] is None and unhooked["child"]["pid"] and hooked["child"]["pid"]
    assert isinstance(hooked["child"]["creation_time"], int)
    children = [attribution.child_record([event for event in events if event["pid"] == pid and event["event"] != "launch"])
                for pid in {event["pid"] for event in events} - {launcher}]
    assert len(children) == 1 and children[0]["ended"] and children[0]["armed"]
    bound, how = attribution.bound_children({**hooked, "launcher_pid": launcher}, children)
    through_launcher = started_by == "launcher" and os.name == "nt" and sys.prefix != sys.base_prefix
    assert bound == children and how == ("via_parent" if through_launcher else "identity")
    assert (children[0]["ppid"] == hooked["child"]["pid"]) is through_launcher and (children[0]["pid"] == hooked["child"]["pid"]) is not through_launcher
    assert attribution.launch_verdict({**hooked, "launcher_pid": launcher}, bound) == "clean"
    # The launch whose environment dropped the hook started a child that wrote nothing: it binds to no record.
    assert attribution.bound_children({**unhooked, "launcher_pid": launcher}, children) == ([], "none")
    assert attribution.launch_verdict({**unhooked, "launcher_pid": launcher}, []) == "launched_without_hook"
    assert attribution.launch_verdict({**failed, "hook_env": True}, []) == "launch_failed"
    # The frame line maps to the nearest site at or before it in the same file and function.
    sites = [{"key": "a.py::f#1", "file": "a.py", "function": "f", "line": 10},
             {"key": "a.py::f#2", "file": "a.py", "function": "f", "line": 20},
             {"key": "a.py::g#1", "file": "a.py", "function": "g", "line": 15}]
    assert attribution.site_for("a.py", "f", 12, sites) == "a.py::f#1"
    assert attribution.site_for("a.py", "f", 20, sites) == "a.py::f#2"
    assert attribution.site_for("a.py", "g", 14, sites) is None
    assert attribution.site_for("b.py", "f", 12, sites) is None


def _launch(site: str, test: str, pid: int, created: int | None = 1000, *, hook_env: bool = True, launcher: int = 10) -> dict[str, object]:
    return {"site": site, "test": f"{test} (call)", "hook_env": hook_env, "launcher_pid": launcher,
            "child": {"pid": pid, "creation_time": created}}


def _child(pid: int, created: int | None = 1000, *, ppid: int = 10, parent_created: int | None = 1, armed: bool = True,
           ended: bool = True, calls: int = 0, is_pytest: bool = False, imported_unarmed: bool = False) -> dict[str, object]:
    return {"pid": pid, "creation_time": created, "ppid": ppid, "parent_creation_time": parent_created, "armed": armed,
            "ended": ended, "calls": calls, "is_pytest": is_pytest, "imported_unarmed": imported_unarmed, "test": "unused (call)"}


def test_a_launch_is_credited_only_by_the_child_it_started() -> None:
    """R5: two sites under one test, one child; missing, incomplete and unarmed children; reused PIDs."""
    from tests.support.child_census import attribution

    one, two = "a.py::test_same#1", "a.py::test_same#2"
    site_map = {key: {"disposition": "census", "proof": "p"} for key in (one, two)}
    sites = [{"key": key, "file": "a.py", "function": "test_same", "line": index} for index, key in enumerate(site_map, 1)]
    collected = {"a.py::test_same"}
    # Two launches, one observed child: only the site whose launch started that child is clean.
    launches = [_launch(one, "a.py::test_same", 101), _launch(two, "a.py::test_same", 102)]
    table = attribution.per_site_table(site_map, sites, launches, [_child(101)], collected)
    assert (table[one]["status"], table[two]["status"]) == ("launched_and_clean", "child_unobserved")
    assert table[one]["bindings"] == {"identity": 1} and table[two]["bindings"] == {"none": 1}
    assert attribution.unproven(table) == [two]
    # The only child's record is start-only: incomplete, so its own site is not clean either.
    table = attribution.per_site_table(site_map, sites, launches, [_child(101, ended=False)], collected)
    assert (table[one]["status"], table[two]["status"]) == ("child_incomplete", "child_unobserved")
    # A child whose hook never armed; a child that imported the adapter without arming; a nested session.
    for record, status in ((_child(101, armed=False), "child_unarmed"), (_child(101, imported_unarmed=True), "pytest_session"),
                           (_child(101, is_pytest=True), "pytest_session"), (_child(101, calls=2), "REAL_ADAPTER_REQUESTED")):
        assert attribution.per_site_table(site_map, sites, launches[:1], [record], collected)[one]["status"] == status
    # The same PID with another creation time is a different process: never bound.
    assert attribution.bound_children(launches[0], [_child(101, created=2000)]) == ([], "none")
    assert attribution.per_site_table(site_map, sites, launches[:1], [_child(101, created=2000)], collected)[one]["status"] == "child_unobserved"
    # The launched process may be the hooked child's parent (the venv launcher): bound on that full identity only.
    below = _child(555, 9, ppid=101, parent_created=1000)
    assert attribution.bound_children(launches[0], [below]) == ([below], "via_parent")
    assert attribution.bound_children(launches[0], [_child(555, 9, ppid=101, parent_created=1001)]) == ([], "none")
    # Every hooked child one hop below the launched process is that launch's: one unclean one spoils it.
    assert attribution.launch_verdict(launches[0], [below, _child(556, 9, ppid=101, parent_created=1000, ended=False)]) == "child_incomplete"
    # A launch whose created process's creation time could not be read names no exact process: it binds
    # to nothing, however well the PID, parent PID and uniqueness of the rows seem to agree.
    for lone in ([_child(101, None)], [_child(101, 999999)], [_child(101, None, ppid=10)]):
        assert attribution.bound_children(_launch(one, "t", 101, None), lone) == ([], "none")
        table = attribution.per_site_table(site_map, sites, [_launch(one, "a.py::test_same", 101, None)], lone, collected)
        assert table[one]["status"] == "launch_identity_unread" and attribution.unproven(table) == [one, two]
    # Positive: every launch of a site bound to its own clean child; a lost hook on one launch spoils the site.
    many = [_launch(one, "a.py::test_same", pid, 1000 + pid) for pid in (201, 202, 203)]
    children = [_child(pid, 1000 + pid) for pid in (201, 202, 203)]
    table = attribution.per_site_table(site_map, sites, many, children, collected)
    assert table[one]["status"] == "launched_and_clean" and table[one]["verdicts"] == {"clean": 3} and table[one]["children_bound"] == 3
    many[1]["hook_env"] = False
    table = attribution.per_site_table(site_map, sites, many, children, collected)
    assert table[one]["status"] == "launched_without_hook" and table[one]["verdicts"] == {"clean": 2, "launched_without_hook": 1}
    assert table[one]["hook_env_on_every_launch"] is False
    # A failed launch has no child to prove anything with.
    table = attribution.per_site_table(site_map, sites, [{**launches[0], "child": None}], children, collected)
    assert table[one]["status"] == "launch_failed"


def test_a_launch_in_the_same_file_never_credits_another_site() -> None:
    from tests.support.child_census import attribution

    site_map = {"a.py::test_one#1": {"disposition": "census", "proof": "p"}, "a.py::_helper#1": {"disposition": "census", "proof": "p"},
                "a.py::test_two#1": {"disposition": "census", "proof": "p"}, "b.py::test_three#1": {"disposition": "tripwire_at_site", "proof": "p"}}
    sites = [{"key": key, "file": key.split("::")[0], "function": key.split("::")[1].split("#")[0], "line": 1} for key in site_map]
    launches = [_launch("a.py::test_one#1", "a.py::test_one", 301), _launch("a.py::_helper#1", "a.py::test_four", 302, hook_env=False)]
    children = [_child(301), _child(302)]
    table = attribution.per_site_table(site_map, sites, launches, children, {"a.py::test_one", "a.py::test_four"})
    assert table["a.py::test_one#1"]["status"] == "launched_and_clean" and table["a.py::test_one#1"]["reachability"] == "collected"
    assert table["a.py::_helper#1"]["status"] == "launched_without_hook" and table["a.py::_helper#1"]["reachability"] == "helper"
    # The same file launched twice, yet the site that never launched is not credited by either.
    assert table["a.py::test_two#1"]["status"] == "not_launched" and table["a.py::test_two#1"]["reachability"] == "not_collected"
    assert table["b.py::test_three#1"]["status"] == "proof_elsewhere"
    assert attribution.unproven(table) == ["a.py::_helper#1", "a.py::test_two#1"]
    # A child that asked for the real folders is named, not averaged away.
    children[0]["calls"] = 1
    assert attribution.per_site_table(site_map, sites, launches, children, set())["a.py::test_one#1"]["status"] == "REAL_ADAPTER_REQUESTED"
