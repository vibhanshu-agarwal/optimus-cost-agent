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
        if entry["disposition"] == "runner_only_plant":
            # The plant really is skipped in an ordinary run, and its program is a literal.
            source = (_ROOT / str(found[key]["file"])).read_text(encoding="utf-8")
            assert f"def {found[key]['function']}() -> None:\n    _main5_runner_probe(" in source, key


def _census_child(tmp_path: Path, program: str, *, hooked: bool = True) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
    """Launch `python -c` with the census hook on PYTHONPATH, the way a census run exposes every child."""
    rows = tmp_path / "rows"
    rows.mkdir(exist_ok=True)
    environment = {name: value for name, value in os.environ.items() if name != "OPTIMUS_TEST_CHILD_CENSUS_DIR"}
    environment["PYTHONPATH"] = os.pathsep.join([str(_HOOK), str(_ROOT / "src"), str(_ROOT)])
    if hooked:
        environment["OPTIMUS_TEST_CHILD_CENSUS_DIR"] = str(rows)
    completed = subprocess.run(
        [sys.executable, "-c", program], cwd=_ROOT, env=environment, capture_output=True, text=True, timeout=120, check=False,
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
    assert none == [] and unhooked.stdout.strip() == "optimus.acp.trusted_paths", unhooked.stdout + unhooked.stderr
