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
    assert len(local) == 1 and isinstance(local[0], ast.Assign) and isinstance(local[0].value, ast.Constant)         and isinstance(local[0].value.value, str), f"{site['key']}: {program.id} is not one plain string assignment"
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
        elif kind == "file":
            assert (_ROOT / value).is_file(), entry
            resolved.append(value)
        else:
            assert kind == "module", entry
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
            relative, _, function = str(keyring.get("control_in", f"{site['file']}::{site['function']}")).partition("::")
            if set(child_keyring.CONTROL_CALLS) & _calls(relative, function):
                continue
            # A tripwire site may build the environment in the test that calls the launching helper: the tripwire's
            # environments carry the control, the child records it, and the parent's check requires that record.
            assert entry["disposition"] == "tripwire_at_site", f"{key}: {relative}::{function} applies no control"
            calls = {ast.unparse(node.func) for node in ast.walk(ast.parse((_ROOT / str(site["file"])).read_text(encoding="utf-8")))
                     if isinstance(node, ast.Call)}
            assert calls & {"child_tripwire.environment", "child_tripwire.hooked_environment"}, f"{key}: no tripwire environment"
            assert "child_tripwire.assert_no_real_adapter_access" in calls, f"{key}: the parent never checks the child's record"


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


# Host-safe even under mutation: with no backend named, the child stops before importing keyring.
_REPORT_BACKEND = (
    "import os, sys\n"
    "if not os.environ.get('PYTHON_KEYRING_BACKEND'):\n"
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


def _backend_child(tmp_path: Path, variable: str | None = None) -> tuple[list[str], Path]:
    """A child launched with the tripwire's environment, which carries the control; `variable` replaces the selection."""
    record = tmp_path / "tripwire.jsonl"
    environment = child_tripwire.environment(dict(os.environ), record)
    if variable is not None:
        environment[child_keyring.VARIABLE] = variable
    completed = subprocess.run(
        [sys.executable, "-c", child_tripwire.PRELUDE + _REPORT_BACKEND], cwd=_ROOT, capture_output=True, text=True,
        timeout=120, check=True, env=environment,
    )
    return completed.stdout.split(), record


def test_a_child_given_the_control_resolves_keyrings_fail_backend_and_its_record_proves_it(tmp_path: Path) -> None:
    lines, record = _backend_child(tmp_path)
    assert lines == [child_keyring.FAIL_BACKEND, "REFUSED=NoKeyringError"]
    assert child_tripwire.assert_no_real_adapter_access(record)["keyring_fail_selected"] == 1


def test_the_childs_own_variable_decides_its_backend_and_the_record_check_notices_another(tmp_path: Path) -> None:
    """Mutation control: with another non-host backend named in the child's variable, the child resolves that one, and
    the parent's check refuses the record. The host backend is never resolved: a backend is always named."""
    lines, record = _backend_child(tmp_path, "keyring.backends.null.Keyring")
    assert lines[0] == "keyring.backends.null.Keyring"
    with pytest.raises(AssertionError, match="did not select keyring's fail backend"):
        child_tripwire.assert_no_real_adapter_access(record)


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
