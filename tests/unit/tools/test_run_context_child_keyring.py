"""Every default-selection child launch site carries a keyring verdict that holds (#540, the child residual of #538).

The root conftest keeps the pytest process off the host's credential store; a child resolves its own backend. Each
site in `run_context_child_sites.json` therefore says, under `keyring`, why its child cannot reach the host store:
the control is in its environment, or its import closure never reaches keyring, or the site's run-context proof
already rules it out. This module checks every verdict against the code, keeps the launch sites that start no
Python accounted for, and shows the control works in a real child. No child here touches the host store: every
child that imports keyring has a non-host backend selected in its own environment.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support import child_keyring, child_tripwire
from tests.support.child_launch_inventory import default_python_sites, launch_sites
from tests.unit.tools.test_run_context_child_sites import _node_binds as node_binds
from tests.unit.tools.test_run_context_child_sites import module_constant

_ROOT = Path(__file__).resolve().parents[3]
_MAP = Path(__file__).with_name("run_context_child_sites.json")
# A verdict that restates the site's run-context proof is held to that disposition, which the site map test checks.
_DISPOSITION_FOR = {"non_python": {"non_python"}, "literal_program": {"literal_program"}, "reviewed_program": {"reviewed_program"},
                    "not_in_default_run": {"runner_only_plant"}, "nested_pytest": {"nested_pytest", "nested_pytest_passive"}}


def _document() -> dict:
    return json.loads(_MAP.read_text(encoding="utf-8"))


def _functions(relative: str, name: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse((_ROOT / relative).read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]


def _calls(relative: str, name: str) -> set[str]:
    return {ast.unparse(node.func) for function in _functions(relative, name) for node in ast.walk(function) if isinstance(node, ast.Call)}


def _file_calls(relative: str) -> set[str]:
    return {ast.unparse(node.func) for node in ast.walk(ast.parse((_ROOT / relative).read_text(encoding="utf-8"))) if isinstance(node, ast.Call)}


def _helper_calls(relative: str, name: str) -> set[str]:
    """Calls made by the module-level functions `name` calls directly, one level down."""
    module_functions = {node.name for node in ast.parse((_ROOT / relative).read_text(encoding="utf-8")).body
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {call for helper in _calls(relative, name) & module_functions for call in _calls(relative, helper)}


def _is_control(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Call) and ast.unparse(node.func) in child_keyring.CONTROL_CALLS


def _launch_call(site: dict[str, object]) -> ast.Call:
    tree = ast.parse((_ROOT / str(site["file"])).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and node.lineno == site["line"]]
    assert calls, f"{site['key']}: no launch call at line {site['line']}"
    return calls[0]


def assert_control_reaches_the_launch(site: dict[str, object], control_in: str | None) -> None:
    """The environment the launch call passes is the control's result, not merely a control call somewhere nearby
    (Codex round 1, finding 1): the `env=` value is a control call; or a name every binding of which in the launching
    function is one; or, when `control_in` names the helper that builds it, a call of that helper every `return` of
    which returns one; or `**kwargs` whose `"env"` item the function sets to one."""
    key, function = site["key"], str(site["function"])
    launch = _launch_call(site)
    value = next((keyword.value for keyword in launch.keywords if keyword.arg == "env"), None)
    functions = _functions(str(site["file"]), function)
    if value is None and any(keyword.arg is None for keyword in launch.keywords):
        stores = [node for f in functions for node in ast.walk(f) if isinstance(node, ast.Assign) and len(node.targets) == 1
                  and isinstance(node.targets[0], ast.Subscript) and ast.unparse(node.targets[0].slice) == "'env'"]
        assert stores and all(_is_control(node.value) for node in stores), f"{key}: **kwargs carry no controlled env"
        return
    assert value is not None, f"{key}: the launch passes no env, so the child inherits this process's environment"
    if _is_control(value):
        return
    if isinstance(value, ast.Name):
        bindings = [node for f in functions for node in ast.walk(f) if node is not f and node_binds(node, value.id)]
        controlled = bindings and all(isinstance(node, ast.Assign) and _is_control(node.value) for node in bindings)
        assert controlled, f"{key}: {value.id} is bound to something other than the control"
        return
    assert control_in and isinstance(value, ast.Call), f"{key}: the env passed is not the control's result"
    relative, _, helper = control_in.partition("::")
    assert ast.unparse(value.func).split(".")[-1] == helper, f"{key}: the env comes from {ast.unparse(value.func)}, not {helper}"
    returns = [node for f in _functions(relative, helper) for node in ast.walk(f) if isinstance(node, ast.Return)]
    assert returns and all(_is_control(node.value) for node in returns), f"{key}: {helper} returns an uncontrolled env"


def site_program(site: dict[str, object]) -> str:
    """The `-c` program of a launch, read from the call in the source: a string literal or a module string constant."""
    tree = ast.parse((_ROOT / str(site["file"])).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and node.lineno == site["line"] and node.args]
    assert calls, f"{site['key']}: no launch call at line {site['line']}"
    command = calls[0].args[0]
    assert isinstance(command, (ast.List, ast.Tuple)), f"{site['key']}: the command is not a literal list"
    texts = [ast.unparse(element) for element in command.elts]
    assert "'-c'" in texts, f"{site['key']}: the command has no -c program"
    program = command.elts[texts.index("'-c'") + 1]
    if isinstance(program, ast.Constant) and isinstance(program.value, str):
        return program.value
    assert isinstance(program, ast.Name), f"{site['key']}: the program is neither a literal nor a named constant"
    local = [node for function in _functions(str(site["file"]), str(site["function"])) for node in ast.walk(function)
             if node is not function and node_binds(node, program.id)]
    if not local:
        return module_constant(str(site["file"]), program.id)
    # A name the launching function binds: exactly one plain assignment of a string constant, nothing else.
    assert len(local) == 1 and isinstance(local[0], ast.Assign) and isinstance(local[0].value, ast.Constant) \
        and isinstance(local[0].value.value, str), f"{site['key']}: {program.id} is not one plain string assignment"
    return local[0].value.value


def closure_entries(site: dict[str, object], entries: list[str]) -> list[str]:
    """The map's entries as `child_keyring.import_closure` takes them."""
    resolved = []
    for entry in entries:
        kind, _, value = entry.partition(":")
        if kind == "program":
            resolved.append("-c:" + site_program(site))
        elif kind == "constant":
            relative, _, name = value.rpartition(":")
            resolved.append("-c:" + module_constant(relative, name))
        else:
            # Read from what the child runs, never a hand-written module list (Codex round 1, finding 3).
            assert kind == "file" and (_ROOT / value).is_file(), f"an entry is the program, a constant or a file: {entry}"
            resolved.append(value)
    return resolved


def test_every_default_launch_site_has_a_keyring_verdict_that_holds() -> None:
    document = _document()
    found = {str(site["key"]): site for site in default_python_sites(_ROOT)}
    assert set(found) == set(document["sites"]), "the site map test keeps the map complete; run it first"
    for key, entry in document["sites"].items():
        site, keyring = found[key], entry.get("keyring")
        assert keyring and keyring["verdict"] in document["keyring_verdicts"], f"{key}: no keyring verdict (#540)"
        verdict = keyring["verdict"]
        if verdict in _DISPOSITION_FOR:
            assert entry["disposition"] in _DISPOSITION_FOR[verdict], f"{key}: {verdict} needs disposition {_DISPOSITION_FOR[verdict]}"
        elif verdict == "import_closure":
            closure = child_keyring.import_closure(closure_entries(site, keyring["entries"]))
            assert closure["keyring_importers"] == [], f"{key}: the child's closure imports keyring: {closure['keyring_importers']}"
            assert closure["unbounded"] == [], f"{key}: the child's closure imports by computed name: {closure['unbounded']}"
        else:
            assert verdict == "fail_backend_in_child_env", key
            try:
                assert_control_reaches_the_launch(site, keyring.get("control_in"))
                continue
            except AssertionError:
                if entry["disposition"] != "tripwire_at_site":
                    raise
            # Runtime control: the tripwire's environments carry the selection, the tripwire refuses to start the child's
            # program without it, and the site's proof requires the child's record of it.
            proof_file, _, proof = str(entry["proof"]).partition("::")
            proof = proof.split("[")[0]
            calls = _file_calls(str(site["file"])) | _file_calls(proof_file)
            assert calls & {"child_tripwire.environment", "child_tripwire.hooked_environment"}, f"{key}: no tripwire environment"
            proof_calls = _calls(proof_file, proof) | _helper_calls(proof_file, proof)
            assert "child_tripwire.assert_no_real_adapter_access" in proof_calls, f"{key}: its proof never checks the child's record"


def test_every_default_launch_site_that_starts_no_python_is_accounted_for() -> None:
    """A launch of a tool, not Python, reaches keyring only if that tool runs this repository's Python: each mechanism or
    site here is one that does not, and a new kind of tool launch fails until it is classified."""
    tools = _document()["keyring_tools"]
    python = {str(site["key"]) for site in default_python_sites(_ROOT)}
    others = [site for site in launch_sites(_ROOT) if not site["excluded_by_marker"] and str(site["key"]) not in python]
    unclassified = sorted(str(site["key"]) for site in others
                          if site["mechanism"] not in tools["mechanisms"] and str(site["key"]) not in tools["sites"])
    assert unclassified == [], "classify each tool launch under keyring_tools in run_context_child_sites.json"
    assert sorted(set(tools["sites"]) - {str(site["key"]) for site in others}) == [], "keyring_tools lists sites that no longer exist"


# Host-safe even under mutation: unless keyring's fail or null backend is named exactly, the child stops before it
# imports keyring, so no mutation of the control can let it resolve or read the host's store.
_REPORT_BACKEND = (
    "import os, sys\n"
    "if os.environ.get('PYTHON_KEYRING_BACKEND') not in {'keyring.backends.fail.Keyring', 'keyring.backends.null.Keyring'}:\n"
    "    print('NO_SELECTION')\n"
    "    sys.exit(0)\n"
    "import keyring\n"
    "backend = keyring.get_keyring()\n"
    "print(type(backend).__module__ + '.' + type(backend).__name__)\n"
    "try:\n"
    "    keyring.get_password('optimus-test-540', 'no-such-entry')\n"
    "    print('READ')\n"
    "except Exception as error:\n"
    "    print('REFUSED=' + type(error).__name__)\n"
)


def _backend_child(tmp_path: Path, variable: str | None = None, *, tripwire: bool = True) -> tuple[subprocess.CompletedProcess[str], Path]:
    """A child launched with the tripwire's environment, which carries the control; `variable` replaces the selection,
    and without `tripwire` the program runs without the tripwire's prelude."""
    record = tmp_path / "tripwire.jsonl"
    environment = child_tripwire.environment(dict(os.environ), record)
    if variable is not None:
        environment[child_keyring.VARIABLE] = variable
    completed = subprocess.run(
        [sys.executable, "-c", (child_tripwire.PRELUDE if tripwire else "") + _REPORT_BACKEND], cwd=_ROOT,
        capture_output=True, text=True, timeout=120, check=False, env=environment,
    )
    return completed, record


def test_a_child_given_the_control_resolves_keyrings_fail_backend_and_its_record_proves_it(tmp_path: Path) -> None:
    completed, record = _backend_child(tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.split() == [child_keyring.FAIL_BACKEND, "REFUSED=NoKeyringError"]
    assert child_tripwire.assert_no_real_adapter_access(record)["keyring_fail_selected"] == 1


@pytest.mark.parametrize("variable", ["keyring.backends.null.Keyring", ""])
def test_a_tripwire_child_without_the_fail_selection_never_runs_its_program(tmp_path: Path, variable: str) -> None:
    """Mutation control: the tripwire refuses before the child's own program runs, and the parent's check fails."""
    completed, record = _backend_child(tmp_path, variable)
    assert completed.returncode != 0 and completed.stdout == "", completed.stdout
    assert child_tripwire.KEYRING_REFUSAL in completed.stderr
    with pytest.raises(AssertionError):
        child_tripwire.assert_no_real_adapter_access(record)


def test_the_childs_own_variable_decides_its_backend(tmp_path: Path) -> None:
    """Without the tripwire, a child whose variable names another non-host backend resolves that one: the selection in
    the child's own environment is what decides."""
    completed, _ = _backend_child(tmp_path, "keyring.backends.null.Keyring", tripwire=False)
    assert completed.stdout.split()[0] == "keyring.backends.null.Keyring", completed.stderr


def test_the_probe_names_no_backend_it_was_not_given(tmp_path: Path) -> None:
    """The probe itself stops before keyring for any other value, so it can never resolve a host backend."""
    completed, _ = _backend_child(tmp_path, "keyring.backends.Windows.WinVaultKeyring", tripwire=False)
    assert completed.stdout.split() == ["NO_SELECTION"], completed.stderr


def test_the_control_adds_only_the_backend_selection() -> None:
    base = {"PATH": "x", child_keyring.VARIABLE: "keyring.backends.null.Keyring"}
    assert child_keyring.environment(base) == {"PATH": "x", child_keyring.VARIABLE: child_keyring.FAIL_BACKEND}
    assert base[child_keyring.VARIABLE] == "keyring.backends.null.Keyring", "the base mapping is not changed"


@pytest.mark.parametrize(
    ("entries", "importers", "unbounded"),
    [
        (["-c:import os, sys"], [], []),
        (["-c:import keyring"], ["<program>"], []),
        (["-c:def later():\n    from keyring import get_password\n"], ["<program>"], []),
        (["-c:import importlib\nimportlib.import_module(name)"], [], ["<program>:2: importlib.import_module"]),
        (["-c:exec(text)"], [], ["<program>:1: exec"]),
        (["optimus.acp.launch_gate"], ["optimus.acp.launch_gate"], None),
        (["optimus.acp.server"], ["optimus.acp.launch_gate", "optimus.acp.local_gateway_secrets"], None),
    ],
)
def test_the_import_closure_finds_lazy_keyring_imports_and_fails_closed_on_computed_names(entries, importers, unbounded) -> None:
    closure = child_keyring.import_closure(entries)
    assert set(importers) <= set(closure["keyring_importers"]), closure["keyring_importers"]
    if not importers:
        assert closure["keyring_importers"] == []
    if unbounded is not None:
        assert closure["unbounded"] == unbounded


@pytest.mark.parametrize(
    ("entries", "unbounded"),
    [
        (["-c:from importlib import import_module as load\nload(name)"], ["<program>:1: from importlib import import_module"]),
        (["-c:import importlib\nloader = importlib.import_module"], ["<program>:2: importlib.import_module"]),
        (["-c:import tools.no_such_module_540"], ["<program>: unresolved tools.no_such_module_540"]),
        (["-c:import no_such_top_level_540"], ["<program>: unresolved no_such_top_level_540"]),
    ],
)
def test_the_import_closure_fails_closed_on_aliases_and_unresolved_names(entries, unbounded) -> None:
    assert child_keyring.import_closure(entries)["unbounded"] == unbounded


def test_the_import_closure_walks_namespace_packages() -> None:
    """`tools` and `tests` have no `__init__.py`; the walk still reaches their modules (Codex round 1, finding 2)."""
    closure = child_keyring.import_closure(["-c:import tools.testing.run_profile"])
    assert {"tools", "tools.testing", "tools.testing.run_profile"} <= set(closure["modules"])
    assert "optimus.acp.launch_gate" in child_keyring.import_closure(["-c:import tests.integration.acp.test_server_stream"])["modules"]


def test_every_nested_pytest_verdict_loads_the_root_conftest() -> None:
    """A nested session that chooses its own configuration or root, or skips conftests, would not install fail."""
    found = {str(site["key"]): site for site in default_python_sites(_ROOT)}
    for key, entry in _document()["sites"].items():
        if entry["keyring"]["verdict"] == "nested_pytest":
            command = ast.unparse(_launch_call(found[key]).args[0]) if _launch_call(found[key]).args else ""
            # The pytest arguments: after `-m pytest`, or the inline program that calls pytest.main.
            arguments = command.split("'pytest'", 1)[1] if "'-m', 'pytest'" in command else site_program(found[key])
            assert not any(flag in arguments for flag in ("'-c'", '"-c"', "--rootdir", "--noconftest", "--confcutdir")), f"{key}: {arguments}"


def test_every_test_that_drives_a_measurement_controls_the_measurement_child() -> None:
    """The audit tool launches measurement children itself; a test module that reaches that launch in-process applies
    `child_keyring.control_measurement_children` (Codex round 1, finding 4)."""
    missing = []
    for path in sorted((_ROOT / "tests").rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        if names & set(child_keyring.MEASUREMENT_CALLS) and "control_measurement_children" not in names:
            missing.append(path.relative_to(_ROOT).as_posix())
    assert missing == []


def test_the_measurement_control_reaches_the_measurement_childs_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.plan1126_runtime_audit import measurement

    assert child_keyring.VARIABLE not in measurement.fresh_child_environment(tmp_path) or child_keyring.VARIABLE in os.environ
    child_keyring.control_measurement_children(monkeypatch)
    assert measurement.fresh_child_environment(tmp_path)[child_keyring.VARIABLE] == child_keyring.FAIL_BACKEND
