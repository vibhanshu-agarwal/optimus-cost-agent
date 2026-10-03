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
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.child_launch_inventory import default_python_sites, launch_sites

_ROOT = Path(__file__).resolve().parents[3]
_MAP = Path(__file__).with_name("run_context_child_sites.json")
_HOOK = _ROOT / "tests" / "support" / "child_census"
_ordinary = pytest.mark.skipif(
    getattr(sys, "_main5_guard_activated", False), reason="the MAIN-5 guard owns every child's adapter there"
)


def _defined_functions(relative: str) -> set[str]:
    tree = ast.parse((_ROOT / relative).read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _module_constant(relative: str, name: str) -> str | None:
    """The string a module assigns to `name` at top level, or None."""
    for node in ast.parse((_ROOT / relative).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets) \
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    return None


# --- literal_program: the command is `python -c <program> [data...]`, and the program cannot reach the resolver.
#
# The command list is read in order: the interpreter, then options that select no code, then the
# inline flag, then the program (a string literal, or a name bound to a string constant of the
# module), then anything else, which is data in the program's argv. Options that choose code
# (`-m`, a script path, combined forms such as `-Sc`) are not accepted, so a program cannot hide
# there. The program itself must parse, import only `os`, `sys` and `time` (statically or through
# `__import__` of one of those names), and never mention the product or evaluate text.

_INTERPRETERS = {"sys.executable", "sys._base_executable"}
_CODELESS_FLAGS = {"-B", "-u", "-E", "-s", "-S", "-I", "-q", "-O", "-OO"}
_CODELESS_X = re.compile(r"^(utf8(=[01])?|dev|importtime|faulthandler|tracemalloc(=\d+)?)$")
_PROGRAM_IMPORTS = {"os", "sys", "time"}
_PROGRAM_FORBIDDEN_NAMES = {"exec", "eval", "compile", "importlib", "subprocess", "runpy", "getattr", "globals", "builtins"}


def inline_program(command: str, relative: str) -> str:
    """The program text of a literal `-c` launch command, or an AssertionError naming what is wrong."""
    try:
        tree = ast.parse(command, mode="eval").body
    except SyntaxError as exc:
        raise AssertionError(f"command does not parse: {command!r}") from exc
    assert isinstance(tree, (ast.List, ast.Tuple)) and tree.elts, f"command is not a list: {command!r}"
    elements = list(tree.elts)
    assert ast.unparse(elements[0]) in _INTERPRETERS, f"interpreter is not sys.executable: {command!r}"
    index = 1
    while index < len(elements):
        element = elements[index]
        text = element.value if isinstance(element, ast.Constant) and isinstance(element.value, str) else None
        if text == "-c":
            break
        if text in _CODELESS_FLAGS:
            index += 1
            continue
        if text == "-X" and index + 1 < len(elements):
            value = elements[index + 1]
            assert isinstance(value, ast.Constant) and isinstance(value.value, str) and _CODELESS_X.match(value.value), \
                f"-X option that is not a code-free setting: {command!r}"
            index += 2
            continue
        raise AssertionError(f"option before -c that could select code: {ast.unparse(element)!r} in {command!r}")
    else:
        raise AssertionError(f"no bare '-c' in {command!r}")
    assert index + 1 < len(elements), f"nothing follows -c in {command!r}"
    program_node = elements[index + 1]
    if isinstance(program_node, ast.Constant) and isinstance(program_node.value, str):
        program = program_node.value
    elif isinstance(program_node, ast.Name):
        constant = _module_constant(relative, program_node.id)
        assert constant is not None, f"{program_node.id} is not a string constant of {relative}"
        program = constant
    else:
        raise AssertionError(f"the program is neither a literal nor a module constant: {ast.unparse(program_node)!r}")
    check_program_text(program)
    return program  # elements[index + 2:] are the program's argv: data, whatever expressions produce them


def check_program_text(program: str) -> None:
    """A program that cannot reach the product: parses, imports only os/sys/time, evaluates nothing."""
    assert "optimus" not in program and "tools" not in program, "the program mentions the product"
    try:
        body = ast.parse(program)
    except SyntaxError as exc:
        raise AssertionError(f"the program does not parse: {exc}") from exc
    for node in ast.walk(body):
        if isinstance(node, ast.Import):
            modules = {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            modules = {(node.module or "").split(".")[0]}
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            argument = node.args[0] if node.args else None
            assert isinstance(argument, ast.Constant) and isinstance(argument.value, str), "__import__ of a non-literal name"
            modules = {argument.value.split(".")[0]}
        elif isinstance(node, ast.Name):
            assert node.id not in _PROGRAM_FORBIDDEN_NAMES, f"the program uses {node.id}"
            continue
        else:
            continue
        assert modules <= _PROGRAM_IMPORTS, f"the program imports {sorted(modules - _PROGRAM_IMPORTS)}"


def _skips_on_windows(relative: str, function: str) -> bool:
    source = (_ROOT / relative).read_text(encoding="utf-8")
    helper = source.index(f"def {function}(")
    window = source[max(0, helper - 1200):helper]
    return 'os.name == "nt"' in window or 'sys.platform == "win32"' in window


def test_every_default_launch_site_is_mapped_to_a_proof() -> None:
    from tests.unit.tools import test_run_context_reviewed_programs as reviewed

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
            inline_program(str(found[key]["command"]), str(found[key]["file"]))
        if entry["disposition"] == "reviewed_program":
            # The program is assembled at run time; a site-specific executable proof in the reviewed-
            # programs module vouches for the helper, every reachable tail and the generated code.
            assert reviewed.PROVEN_SITES.get(key) == proof_test, f"{key}: no executable proof registered for this site"
            assert proof_file == reviewed.__name__.replace(".", "/") + ".py", key
        if entry["disposition"] == "posix_only_caller":
            assert _skips_on_windows(str(found[key]["file"]), str(found[key]["function"])), \
                f"{key}: the enclosing test does not skip on Windows"
        if entry["disposition"] == "runner_only_plant":
            # The plant really is skipped in an ordinary run, and its program is a literal.
            source = (_ROOT / str(found[key]["file"])).read_text(encoding="utf-8")
            assert f"def {found[key]['function']}() -> None:\n    _main5_runner_probe(" in source, key


@pytest.mark.parametrize(
    ("name", "command", "accepted"),
    [
        ("literal", "[sys.executable, '-c', 'import time; time.sleep(30)']", True),
        ("trailing-data", "[sys.executable, '-c', 'import time; time.sleep(30)', marker]", True),
        ("trailing-expressions", "[sys.executable, '-c', 'pass', str(path), mode, f'{x}']", True),
        ("codeless-options", "[sys.executable, '-X', 'utf8', '-B', '-c', 'pass']", True),
        ("base-interpreter", "[sys._base_executable, '-c', 'pass']", True),
        ("module-constant", "[sys.executable, '-c', _PROGRAM]", True),
        ("other-interpreter", "['python', '-c', 'pass']", False),
        ("module-option", "[sys.executable, '-m', 'pytest', '-c', 'pass']", False),
        ("combined-flag", "[sys.executable, '-Sc', 'pass']", False),
        ("script-before-c", "[sys.executable, 'run.py', '-c', 'pass']", False),
        ("x-option-selecting-code", "[sys.executable, '-X', 'importpath=x', '-c', 'pass']", False),
        ("no-c", "[sys.executable, 'script.py']", False),
        ("program-is-local-name", "[sys.executable, '-c', code]", False),
        ("program-is-fstring", "[sys.executable, '-c', f'open({path!r})']", False),
        ("program-imports-product", "[sys.executable, '-c', 'import optimus']", False),
        ("program-imports-subprocess", "[sys.executable, '-c', 'import subprocess']", False),
        ("program-dunder-import-dynamic", "[sys.executable, '-c', '__import__(name)']", False),
        ("program-dunder-import-other", "[sys.executable, '-c', '__import__(\"importlib\")']", False),
        ("program-exec", "[sys.executable, '-c', 'exec(\"pass\")']", False),
        ("program-does-not-parse", "[sys.executable, '-c', 'import (']", False),
    ],
)
def test_the_literal_program_check_reads_the_command_in_order(tmp_path: Path, monkeypatch, name: str, command: str, accepted: bool) -> None:
    """Sensitivity of the literal check: data after the program is fine; anything that selects code is not."""
    module = tmp_path / "site_module.py"
    module.write_text('_PROGRAM = "import os; os._exit(3)"\n', encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "_ROOT", tmp_path)
    if accepted:
        program = inline_program(command, "site_module.py")
        assert program in {"import time; time.sleep(30)", "pass", "import os; os._exit(3)"}
    else:
        with pytest.raises(AssertionError):
            inline_program(command, "site_module.py")


def test_the_literal_program_check_accepts_the_repository_writer_program() -> None:
    """Control: the existing literal programs (file writes through `__import__('os')`, sleeps, exits) stay accepted."""
    for key, entry in json.loads(_MAP.read_text(encoding="utf-8"))["sites"].items():
        if entry["disposition"] == "literal_program":
            site = next(site for site in default_python_sites(_ROOT) if site["key"] == key)
            inline_program(str(site["command"]), str(site["file"]))


# --- the repository's launch wrapper is inventoried under its bound name, and nothing else's `.popen` is.


def _tracked_project(tmp_path: Path, files: dict[str, str]) -> Path:
    project = tmp_path / "project"
    for relative, source in files.items():
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "add", "-f", "."], cwd=project, check=True, capture_output=True)
    return project


_WRAPPER_SPELLINGS = {
    "from-tools": "from tools import process_tree\n\ndef test_a():\n    process_tree.popen([sys.executable, '-c', 'pass'])\n",
    "from-tools-as": "from tools import process_tree as pt\n\ndef test_a():\n    pt.popen([sys.executable, '-c', 'pass'])\n",
    "from-module": "from tools.process_tree import popen\n\ndef test_a():\n    popen([sys.executable, '-c', 'pass'])\n",
    "from-module-as": "from tools.process_tree import popen as start\n\ndef test_a():\n    start([sys.executable, '-c', 'pass'])\n",
    "import-module": "import tools.process_tree\n\ndef test_a():\n    tools.process_tree.popen([sys.executable, '-c', 'pass'])\n",
    "import-module-as": "import tools.process_tree as tree\n\ndef test_a():\n    tree.popen([sys.executable, '-c', 'pass'])\n",
}
_NOT_WRAPPERS = {
    "unbound-name": "def test_a():\n    process_tree.popen([sys.executable, '-c', 'pass'])\n",
    "other-popen": "import os\n\ndef test_a():\n    os.popen('dir')\n",
    "other-module": "from somewhere import process_tree\n\ndef test_a():\n    process_tree.popen([sys.executable, '-c', 'pass'])\n",
    "relative-import": "from . import process_tree\n\ndef test_a():\n    process_tree.popen([sys.executable, '-c', 'pass'])\n",
    "popen-of-other": "from tools import process_tree\n\ndef test_a():\n    other.popen([sys.executable, '-c', 'pass'])\n",
}


@pytest.mark.parametrize("spelling", sorted(_WRAPPER_SPELLINGS))
def test_the_inventory_finds_the_launch_wrapper_under_its_bound_name(tmp_path: Path, spelling: str) -> None:
    project = _tracked_project(tmp_path, {"tests/unit/test_site.py": "import sys\n" + _WRAPPER_SPELLINGS[spelling]})
    sites = launch_sites(project)
    assert [site["key"] for site in sites] == ["tests/unit/test_site.py::test_a#1"], spelling
    assert sites[0]["wrapper"] == "tools.process_tree.popen" and sites[0]["mechanism"] == "python:inline_script"


@pytest.mark.parametrize("spelling", sorted(_NOT_WRAPPERS))
def test_the_inventory_ignores_popen_attributes_that_are_not_the_bound_wrapper(tmp_path: Path, spelling: str) -> None:
    project = _tracked_project(tmp_path, {"tests/unit/test_site.py": "import sys\n" + _NOT_WRAPPERS[spelling]})
    assert launch_sites(project) == [], spelling


def test_wrapper_and_direct_launches_share_one_position_sequence(tmp_path: Path) -> None:
    """Keys count every launch in the function in source order, whichever spelling started it."""
    source = (
        "import subprocess, sys\nfrom tools import process_tree\n\n"
        "def test_a():\n    subprocess.Popen([sys.executable, '-c', 'pass'])\n    process_tree.popen([sys.executable, '-c', 'pass'])\n"
        "    subprocess.run([sys.executable, '-c', 'pass'])\n"
    )
    project = _tracked_project(tmp_path, {"tests/unit/test_site.py": source})
    sites = launch_sites(project)
    assert [(site["key"], site["wrapper"]) for site in sites] == [
        ("tests/unit/test_site.py::test_a#1", None), ("tests/unit/test_site.py::test_a#2", "tools.process_tree.popen"),
        ("tests/unit/test_site.py::test_a#3", None),
    ]


def test_the_repository_wrapper_sites_are_inventoried() -> None:
    """The nine direct test call sites of tools.process_tree.popen on this tree are found, no more, no fewer."""
    wrapper_sites = sorted(site["key"] for site in launch_sites(_ROOT) if site["wrapper"])
    assert wrapper_sites == [
        "tests/unit/guardrails/test_ci_parity.py::_run#1",
        "tests/unit/guardrails/test_ci_parity.py::test_terminate_tree_reaps_even_when_tree_kill_fails#1",
        "tests/unit/tools/test_process_tree.py::test_a_child_that_cannot_be_contained_never_runs_and_the_error_is_raised#1",
        "tests/unit/tools/test_process_tree.py::test_a_cleanup_failure_is_attached_to_the_initiating_error_and_the_root_is_still_reaped#1",
        "tests/unit/tools/test_process_tree.py::test_a_failure_after_the_child_ran_kills_its_whole_tree_and_keeps_the_error#1",
        "tests/unit/tools/test_process_tree.py::test_a_tree_child_runs_normally_and_keeps_the_callers_arguments#1",
        "tests/unit/tools/test_process_tree.py::test_kill_tree_after_the_whole_tree_exited_is_harmless#1",
        "tests/unit/tools/test_process_tree.py::test_kill_tree_kills_every_descendant_including_ones_no_parent_walk_reaches#1",
        "tests/unit/tools/test_process_tree.py::test_popen_refuses_to_share_the_callers_session#1",
    ]


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


# --- R5: a site is attributed only to its own launches, and a launch only by the child it started.

_LAUNCHING_PROGRAM = """
import os, subprocess, sys
inner = "import subprocess, sys; subprocess.run([sys.executable, '-c', 'print(11)'], check=True)"
code = "import subprocess, sys; subprocess.run([sys.executable, '-c', " + repr(inner) + "], check=True)"
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
    children = [attribution.child_record([event for event in events if event["pid"] == pid])
                for pid in {event["pid"] for event in events} - {launcher}]
    assert len(children) == 2 and all(child["ended"] and child["armed"] for child in children)
    # The site's launch binds the hooked child it created and the hooked grandchild below it: the
    # grandchild's recorded chain of identities reaches the launched process (two or four hops with
    # launchers between). Every bound child must be clean for the launch to be.
    bound, how = attribution.bound_children({**hooked, "launcher_pid": launcher}, children)
    through_launcher = started_by == "launcher" and os.name == "nt" and sys.prefix != sys.base_prefix
    assert sorted(child["pid"] for child in bound) == sorted(child["pid"] for child in children)
    assert how == ("via_ancestor" if through_launcher else "via_parent")
    near = next(child for child in children if child["launches"] == 1)
    far = next(child for child in children if child["launches"] == 0)
    assert (near["ppid"] == hooked["child"]["pid"]) is through_launcher and (near["pid"] == hooked["child"]["pid"]) is not through_launcher
    assert attribution.bound_children({**hooked, "launcher_pid": launcher}, [near])[1] == ("via_parent" if through_launcher else "identity")
    assert all(entry["creation_time"] is not None for entry in far["ancestors"]) and len(far["ancestors"]) >= 2
    assert attribution.launch_verdict({**hooked, "launcher_pid": launcher}, bound) == "clean"
    assert attribution.launch_verdict({**hooked, "launcher_pid": launcher}, [near, {**far, "ended": False}]) == "child_incomplete"
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


_CHAIN_PROGRAM = """
import json, sitecustomize as hook
normal = hook._ancestors()
hook._parent_of = lambda pid: (hook._own_creation_time() + 1, 99)
print("CHAIN=" + json.dumps({"normal": normal, "reused": hook._ancestors()}))
"""


@_ordinary
def test_the_census_hook_stops_its_ancestor_chain_at_a_reused_pid(tmp_path: Path) -> None:
    """Each link of the chain must be older than its descendant; a younger 'parent' is a reused PID and ends it."""
    completed, _events = _census_child(tmp_path, _CHAIN_PROGRAM)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    chain = json.loads(completed.stdout.split("CHAIN=", 1)[1])
    normal = chain["normal"]
    assert normal and normal[0]["pid"] and all(entry["creation_time"] is not None for entry in normal)
    assert all(older["creation_time"] <= younger["creation_time"] for younger, older in zip(normal, normal[1:], strict=False))
    assert chain["reused"] == [{"pid": normal[0]["pid"], "creation_time": None}]


def _launch(site: str, test: str, pid: int, created: int | None = 1000, *, hook_env: bool = True, launcher: int = 10) -> dict[str, object]:
    return {"site": site, "test": f"{test} (call)", "hook_env": hook_env, "launcher_pid": launcher,
            "child": {"pid": pid, "creation_time": created}}


def _child(pid: int, created: int | None = 1000, *, ppid: int = 10, parent_created: int | None = 1, armed: bool = True,
           ended: bool = True, calls: int = 0, is_pytest: bool = False, imported_unarmed: bool = False,
           ancestors: list[dict[str, object]] | None = None) -> dict[str, object]:
    chain = [{"pid": ppid, "creation_time": parent_created}] if ancestors is None else ancestors
    return {"pid": pid, "creation_time": created, "ppid": ppid, "parent_creation_time": parent_created, "ancestors": chain,
            "armed": armed, "ended": ended, "calls": calls, "is_pytest": is_pytest, "imported_unarmed": imported_unarmed,
            "test": "unused (call)"}


def test_a_launch_is_attributed_only_to_the_child_it_started() -> None:
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
                           (_child(101, is_pytest=True), "launched_and_clean"), (_child(101, calls=2), "REAL_ADAPTER_REQUESTED")):
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
    # Further down the recorded chain (a shim or launcher between): bound on the exact identity at that hop only.
    deep = _child(777, 12, ancestors=[{"pid": 600, "creation_time": 11}, {"pid": 101, "creation_time": 1000}])
    assert attribution.bound_children(launches[0], [deep]) == ([deep], "via_ancestor")
    assert attribution.bound_children(launches[0], [below, deep]) == ([below, deep], "via_ancestor")
    for broken in ([{"pid": 600, "creation_time": 11}, {"pid": 101, "creation_time": 1001}],
                   [{"pid": 600, "creation_time": 11}, {"pid": 101, "creation_time": None}],
                   [{"pid": 600, "creation_time": 11}]):
        assert attribution.bound_children(launches[0], [_child(777, 12, ancestors=broken)]) == ([], "none")
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


def test_a_launch_in_the_same_file_never_attributes_another_site() -> None:
    from tests.support.child_census import attribution

    site_map = {"a.py::test_one#1": {"disposition": "census", "proof": "p"}, "a.py::_helper#1": {"disposition": "census", "proof": "p"},
                "a.py::test_two#1": {"disposition": "census", "proof": "p"}, "b.py::test_three#1": {"disposition": "tripwire_at_site", "proof": "p"}}
    sites = [{"key": key, "file": key.split("::")[0], "function": key.split("::")[1].split("#")[0], "line": 1} for key in site_map]
    launches = [_launch("a.py::test_one#1", "a.py::test_one", 301), _launch("a.py::_helper#1", "a.py::test_four", 302, hook_env=False)]
    children = [_child(301), _child(302)]
    table = attribution.per_site_table(site_map, sites, launches, children, {"a.py::test_one", "a.py::test_four"})
    assert table["a.py::test_one#1"]["status"] == "launched_and_clean" and table["a.py::test_one#1"]["reachability"] == "collected"
    assert table["a.py::_helper#1"]["status"] == "launched_without_hook" and table["a.py::_helper#1"]["reachability"] == "helper"
    # The same file launched twice, yet the site that never launched is not attributed by either.
    assert table["a.py::test_two#1"]["status"] == "not_launched" and table["a.py::test_two#1"]["reachability"] == "not_collected"
    assert table["b.py::test_three#1"]["status"] == "proof_elsewhere"
    assert attribution.unproven(table) == ["a.py::_helper#1", "a.py::test_two#1"]
    # A child that asked for the real folders is named, not averaged away.
    children[0]["calls"] = 1
    assert attribution.per_site_table(site_map, sites, launches, children, set())["a.py::test_one#1"]["status"] == "REAL_ADAPTER_REQUESTED"
