"""Plan 11.30 Task 2: change selection — deterministic mapping, reasons and the bounded broad fallback.

Pure controls over a synthetic repository: every dependency kind the selector must follow is planted
here (imports, packages, relative imports, string imports, `-m` launches, path reads, fixtures,
declared expensive-domain inputs, prose, machine data and configuration).
"""

from __future__ import annotations

import pytest

from tools.testing import test_profiles as profiles

_SOURCES = {
    "src/pkg/__init__.py": "",
    "src/pkg/core.py": "VALUE = 1\n",
    "src/pkg/util.py": "from pkg import core\n",
    "src/pkg/sub/__init__.py": "",
    "src/pkg/sub/leaf.py": "from ..core import VALUE\n",
    "src/pkg/winonly.py": "import sys\nWINDOWS = sys.platform == 'win32'\n",
    "src/pkg/native.py": "import ctypes\n",
    "tools/__init__.py": "",
    "tools/helper.py": "TABLE = 'tests/fixtures/data/table.json'\n",
    "tests/conftest.py": "",
    "tests/unit/test_core.py": "from pkg.util import core\n",
    "tests/unit/test_leaf.py": "import pkg.sub.leaf\n",
    "tests/unit/test_strings.py": "import importlib\nMODULE = importlib.import_module('pkg.core')\n",
    "tests/unit/test_launch.py": "import subprocess, sys\nsubprocess.run([sys.executable, '-m', 'tools.helper'], check=True)\n",
    "tests/unit/test_reads.py": "from pathlib import Path\nROOT = Path(__file__).parents[2]\nTEXT = (ROOT / 'tests' / 'fixtures' / 'other.txt').read_text()\n",
    "tests/unit/test_tool.py": "from tools import helper\n",
    "tests/unit/test_docs.py": "GUIDE = 'docs/guide.md'\n",
    "tests/unit/test_gate.py": "from pathlib import Path\nROOT = Path(__file__).parents[2]\nSOURCES = ROOT / 'src'\n",
    "tests/unit/test_platform.py": "import sys\nfrom pkg import native, winonly\nWINDOWS = sys.platform == 'win32'\n",
    "tests/unit/test_audit.py": "from pkg import core\n",
    "tests/unit/test_sealed.py": "SEALED = 1\n",
    "tests/unit/test_proc.py": "from pkg import util\n",
    "tests/e2e/test_e2e.py": "E2E = 1\n",
}
_DATA = (
    "tests/fixtures/data/table.json", "tests/fixtures/other.txt", "tests/fixtures/sealed/model.json",
    "docs/guide.md", "docs/other.md", "README.md", "pyproject.toml", "reports/r.json", "reports/notes.md", "data/blob.bin",
)
_TRACKED = (*_SOURCES, *_DATA)
_NODES = tuple(f"{path}::test_a" for path in _SOURCES if "/test_" in path) + ("tests/unit/test_core.py::test_b[1]",)
_MANIFEST = '''schema = "test-profiles-v1"
[[rules]]
tier = "audit-current"
paths = ["tests/unit/test_audit.py"]
why = "measures"
[[rules]]
tier = "audit-sealed"
paths = ["tests/unit/test_sealed.py"]
why = "replays"
[[rules]]
tier = "proc"
paths = ["tests/unit/test_proc.py", "tests/unit/test_launch.py"]
why = "spawns"
[[rules]]
tier = "gates"
paths = ["tests/unit/test_docs.py", "tests/unit/test_gate.py"]
why = "guards"
[[rules]]
tier = "e2e-local"
paths = ["tests/e2e/**"]
why = "e2e"
[[tags]]
name = "platform"
paths = ["tests/unit/test_platform.py"]
why = "reads the platform"
[[tags]]
name = "concurrency"
paths = ["tests/unit/test_core.py"]
why = "races"
[selection]
broad_paths = ["pyproject.toml", "tests/conftest.py", "tests/support/**"]
prose_gates = ["tests/unit/test_docs.py"]
platform_paths = []
[[inputs]]
paths = ["tests/fixtures/sealed/**"]
tiers = ["audit-sealed"]
why = "sealed model fixtures"
'''


@pytest.fixture(scope="module")
def manifest() -> profiles.ProfileManifest:
    return profiles.load_manifest(_MANIFEST)


@pytest.fixture(scope="module")
def classification(manifest: profiles.ProfileManifest) -> profiles.Classification:
    return profiles.classify_nodes(_NODES, manifest)


@pytest.fixture(scope="module")
def dependencies(manifest: profiles.ProfileManifest) -> profiles.DependencyMap:
    return profiles.build_dependency_map(_SOURCES, _TRACKED, manifest)


def _select(
    classification: profiles.Classification, dependencies: profiles.DependencyMap, *changes: profiles.Change,
    profile: str = "commit", provisional: tuple[tuple[str, str | None], ...] = (), old_graph: bool = True,
) -> profiles.Selection:
    view = "checkpoint" if profile == "checkpoint" else "commit"
    change_set = profiles.ChangeSet(view=view, changes=changes, provisional=provisional, old_graph=old_graph)
    return profiles.select_tests(change_set, classification, dependencies, profiles.ProfileRequest(profile))


def _m(path: str) -> profiles.Change:
    return profiles.Change("M", path)


def _files(selection: profiles.Selection) -> set[str]:
    return {node.split("::", 1)[0] for node in selection.nodes}


_ALL_GATES = {"tests/unit/test_docs.py", "tests/unit/test_gate.py"}


def test_name_status_output_is_parsed_nul_safely_with_renames_and_deletes() -> None:
    raw = b"M\0src/a.py\0R087\0old name.py\0new\nname.py\0D\0gone\t.py\0A\0docs/\xc3\xa9.md\0C100\0x.py\0y.py\0"
    assert profiles.parse_name_status(raw) == (
        profiles.Change("M", "src/a.py"),
        profiles.Change("R", "new\nname.py", "old name.py"),
        profiles.Change("D", "gone\t.py"),
        profiles.Change("A", "docs/é.md"),
        profiles.Change("C", "y.py", "x.py"),
    )
    with pytest.raises(profiles.SelectionError, match="name-status"):
        profiles.parse_name_status(b"M\0src/a.py\0R087\0only-one.py\0")


def test_modules_are_named_from_their_source_roots(dependencies: profiles.DependencyMap) -> None:
    assert dependencies.module_of["src/pkg/sub/leaf.py"] == "pkg.sub.leaf"
    assert dependencies.module_of["src/pkg/sub/__init__.py"] == "pkg.sub"
    assert dependencies.module_of["tools/helper.py"] == "tools.helper"
    assert dependencies.module_of["tests/unit/test_core.py"] == "tests.unit.test_core"


def test_a_module_change_selects_its_transitive_relative_and_string_importers(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    found = _select(classification, dependencies, _m("src/pkg/core.py"))
    assert _files(found) == {
        "tests/unit/test_core.py", "tests/unit/test_leaf.py", "tests/unit/test_strings.py", "tests/unit/test_proc.py",
        *_ALL_GATES,
    }
    assert found.fallback == () and found.label == "selected"
    assert "tests/unit/test_audit.py::test_a" not in found.nodes  # R5: current audits are checkpoint-only at commit
    assert found.reasons["tests/unit/test_core.py::test_b[1]"].startswith("depends on src/pkg/core.py")


def test_a_package_init_change_selects_everything_under_the_package(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    found = _select(classification, dependencies, _m("src/pkg/sub/__init__.py"))
    assert _files(found) - _ALL_GATES == {"tests/unit/test_leaf.py"}


def test_a_renamed_or_deleted_module_selects_the_importers_of_its_old_name(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    renamed = _select(classification, dependencies, profiles.Change("R", "src/pkg/util2.py", "src/pkg/util.py"))
    assert _files(renamed) - _ALL_GATES == {"tests/unit/test_core.py", "tests/unit/test_proc.py"}
    deleted = _select(classification, dependencies, profiles.Change("D", "src/pkg/sub/leaf.py"))
    assert _files(deleted) - _ALL_GATES == {"tests/unit/test_leaf.py"}


def test_data_launch_and_tool_reads_select_their_readers(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    joined = _select(classification, dependencies, _m("tests/fixtures/other.txt"))
    assert _files(joined) - _ALL_GATES == {"tests/unit/test_reads.py"}
    through_tool = _select(classification, dependencies, _m("tests/fixtures/data/table.json"))
    assert _files(through_tool) - _ALL_GATES == {"tests/unit/test_tool.py", "tests/unit/test_launch.py"}
    launched = _select(classification, dependencies, _m("tools/helper.py"))
    assert _files(launched) - _ALL_GATES == {"tests/unit/test_tool.py", "tests/unit/test_launch.py"}
    gate = _select(classification, dependencies, _m("src/pkg/winonly.py"))
    assert "tests/unit/test_gate.py" in _files(gate)


def test_a_declared_input_selects_its_expensive_domain_and_says_why(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    found = _select(classification, dependencies, _m("tests/fixtures/sealed/model.json"))
    assert "tests/unit/test_sealed.py::test_a" in found.nodes
    assert found.domains["audit-sealed"].startswith("included")
    assert found.domains["e2e-local"].startswith("omitted")
    assert found.fallback == ()


@pytest.mark.parametrize("path", ["docs/guide.md", "docs/new-page.md", "README.md", "reports/notes.md", "docs/architecture-new.pdf"])
def test_prose_selects_docs_gates_and_its_readers_and_never_falls_back(
    classification: profiles.Classification, dependencies: profiles.DependencyMap, path: str,
) -> None:
    found = _select(classification, dependencies, profiles.Change("A" if "new" in path else "M", path))
    assert found.fallback == ()
    assert _files(found) == {"tests/unit/test_docs.py"}  # not every gate, no cost tier


@pytest.mark.parametrize("path", ["reports/r.json", "data/blob.bin", "tests/fixtures/new.json", "docs/reviews/new-manifest.json"])
def test_unmapped_machine_data_takes_the_bounded_broad_path(
    classification: profiles.Classification, dependencies: profiles.DependencyMap, path: str,
) -> None:
    found = _select(classification, dependencies, profiles.Change("A" if "new" in path else "M", path))
    assert found.fallback == (f"unmapped: {path}",)


def test_prose_in_a_scanned_folder_selects_the_gates_that_scan_it_and_no_cost_tier_scanner(manifest: profiles.ProfileManifest) -> None:
    """A docs folder that holds code is read whole by its scanners: a prose change there, even a new document,
    runs the gates among them (v4: all known gates that read those documents), never the cost-tier scanners."""
    scan = "from pathlib import Path\nROOT = Path(__file__).parents[2]\nDOCS = ROOT / 'docs'\n"
    sources = {**_SOURCES, "docs/sources/tool.py": "TOOL = 1\n", "tests/unit/test_gate.py": scan, "tests/unit/test_core.py": scan}
    dependencies = profiles.build_dependency_map(sources, (*_TRACKED, "docs/sources/tool.py"), manifest)
    found = _select(profiles.classify_nodes(_NODES, manifest), dependencies, profiles.Change("A", "docs/new-topic.md"))
    assert found.fallback == ()
    assert _files(found) == {"tests/unit/test_docs.py", "tests/unit/test_gate.py"}
    assert found.reasons["tests/unit/test_gate.py::test_a"] == "prose: gate scans the folder of docs/new-topic.md"


def test_prose_in_a_folder_a_tool_scans_selects_the_gates_that_use_the_tool(manifest: profiles.ProfileManifest) -> None:
    """The scan can sit in a tool (`tools/doc_paths.py` reads every document): the gates importing it read a new
    document too, and are selected; cost-tier tests importing the same tool are not."""
    sources = {
        **_SOURCES, "docs/sources/tool.py": "TOOL = 1\n",
        "tools/scan.py": "from pathlib import Path\nROOT = Path(__file__).parents[1]\nDOCS = ROOT / 'docs'\n",
        "tests/unit/test_gate.py": "from tools import scan\n", "tests/unit/test_core.py": "from tools import scan\n",
    }
    dependencies = profiles.build_dependency_map(sources, (*_TRACKED, "docs/sources/tool.py", "tools/scan.py"), manifest)
    found = _select(profiles.classify_nodes(_NODES, manifest), dependencies, profiles.Change("A", "docs/new-topic.md"))
    assert found.fallback == ()
    assert _files(found) == {"tests/unit/test_docs.py", "tests/unit/test_gate.py"}
    assert found.reasons["tests/unit/test_gate.py::test_a"] == "prose: gate scans the folder of docs/new-topic.md"


def test_a_source_only_scanned_by_whole_folder_gates_is_still_unmapped(manifest: profiles.ProfileManifest) -> None:
    """`ROOT / "src"` readers run for every src change, but they exercise no behaviour of a module nobody imports."""
    sources = {**_SOURCES, "src/pkg/orphan.py": "ORPHAN = 1\n"}
    dependencies = profiles.build_dependency_map(sources, (*_TRACKED, "src/pkg/orphan.py"), manifest)
    classification = profiles.classify_nodes(_NODES, manifest)
    found = _select(classification, dependencies, _m("src/pkg/orphan.py"))
    assert found.fallback == ("unmapped: src/pkg/orphan.py",)
    assert "tests/unit/test_gate.py::test_a" in found.nodes


def test_naming_a_folder_of_code_scans_it_and_does_not_depend_on_its_files(manifest: profiles.ProfileManifest) -> None:
    """A runner that names `tests/unit` runs those tests; its own tests do not consume their bytes."""
    sources = {**_SOURCES, "src/pkg/runner.py": "TARGETS = 'tests/unit'\n", "tests/unit/test_runner.py": "from pkg import runner\n"}
    dependencies = profiles.build_dependency_map(sources, (*_TRACKED, "src/pkg/runner.py", "tests/unit/test_runner.py"), manifest)
    classification = profiles.classify_nodes((*_NODES, "tests/unit/test_runner.py::test_a"), manifest)
    found = _select(classification, dependencies, _m("tests/unit/test_leaf.py"))
    assert _files(found) - _ALL_GATES == {"tests/unit/test_leaf.py"}


def test_a_change_that_reaches_no_test_is_unmapped(manifest: profiles.ProfileManifest) -> None:
    sources = {**_SOURCES, "src/pkg/internal.py": "INTERNAL = 1\n", "src/pkg/user.py": "from pkg import internal\n"}
    dependencies = profiles.build_dependency_map(sources, (*_TRACKED, "src/pkg/internal.py", "src/pkg/user.py"), manifest)
    found = _select(profiles.classify_nodes(_NODES, manifest), dependencies, _m("src/pkg/internal.py"))
    assert found.fallback == ("unmapped: src/pkg/internal.py",)


def test_a_module_only_a_conftest_imports_is_unmapped_and_one_with_tests_is_dependency_selected(manifest: profiles.ProfileManifest) -> None:
    """Conftest-imported code runs inside every selected session, so it is not broad by itself: with test
    dependents it is selected through them; reached by no test, it is unmapped and takes the broad path."""
    sources = {
        **_SOURCES, "tests/conftest.py": "from tools import harness\nfrom pkg import core\n", "tools/harness.py": "HARNESS = 1\n",
    }
    dependencies = profiles.build_dependency_map(sources, (*_TRACKED, "tools/harness.py"), manifest)
    classification = profiles.classify_nodes(_NODES, manifest)
    assert _select(classification, dependencies, _m("tools/harness.py")).fallback == ("unmapped: tools/harness.py",)
    assert _select(classification, dependencies, _m("src/pkg/core.py")).fallback == ()


@pytest.mark.parametrize("path", ["pyproject.toml", "tests/conftest.py", "tests/support/helpers.py"])
def test_common_configuration_selects_broad_core_gates_and_platform_but_no_undeclared_expensive_domain(
    classification: profiles.Classification, dependencies: profiles.DependencyMap, path: str,
) -> None:
    found = _select(classification, dependencies, _m(path))
    assert found.fallback == (f"broad: {path}",)
    tiers = {classification.tiers[node] for node in found.nodes}
    assert tiers == {"core", "gates"}
    assert set(profiles.profile_members(classification, "core")) <= set(found.nodes)
    assert "tests/unit/test_platform.py::test_a" in found.nodes and found.platform_triggers
    assert found.obligations == ("wsl-platform: next checkpoint",)
    for domain in ("proc", "audit-sealed", "audit-current", "e2e-local"):
        assert found.domains[domain].startswith("omitted"), found.domains


def test_no_single_change_turns_a_commit_into_the_full_suite(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    for path in _TRACKED:
        found = _select(classification, dependencies, _m(path))
        assert set(found.nodes) < set(_NODES), path
        assert "tests/unit/test_audit.py::test_a" not in found.nodes, path
        if not path.startswith("tests/e2e/"):
            assert "tests/e2e/test_e2e.py::test_a" not in found.nodes, path


def test_a_platform_source_triggers_native_platform_nodes_and_a_wsl_obligation(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    for path in ("src/pkg/winonly.py", "src/pkg/native.py"):
        found = _select(classification, dependencies, _m(path))
        assert "tests/unit/test_platform.py::test_a" in found.nodes, path
        assert found.platform_triggers == (path,)
        assert found.obligations == ("wsl-platform: next checkpoint",)
    quiet = _select(classification, dependencies, _m("src/pkg/core.py"))
    assert quiet.platform_triggers == () and quiet.obligations == ()


def test_a_checkpoint_adds_all_gates_and_full_depth_current_audits_even_for_prose(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    found = _select(classification, dependencies, _m("docs/guide.md"), profile="checkpoint")
    assert {"tests/unit/test_audit.py::test_a", *(f"{gate}::test_a" for gate in _ALL_GATES)} <= set(found.nodes)
    assert found.audit_depth == "full"
    repeats = _select(classification, dependencies, _m("src/pkg/core.py"), profile="checkpoint")
    assert set(repeats.concurrency) == {"tests/unit/test_core.py::test_a", "tests/unit/test_core.py::test_b[1]"}
    assert _select(classification, dependencies, _m("docs/guide.md"), profile="checkpoint").concurrency == ()


def test_quick_is_change_selected_core_only(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    found = _select(classification, dependencies, _m("src/pkg/core.py"), profile="quick")
    assert _files(found) == {"tests/unit/test_core.py", "tests/unit/test_leaf.py", "tests/unit/test_strings.py"}
    broad = _select(classification, dependencies, _m("pyproject.toml"), profile="quick")
    assert set(broad.nodes) == set(profiles.profile_members(classification, "core"))


def test_an_empty_commit_is_no_commit_input_not_a_pass(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    found = _select(classification, dependencies)
    assert (found.label, found.nodes) == ("no-commit-input", ())


def test_provisional_unstaged_divergence_is_carried_and_selected(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    provisional = (("src/pkg/core.py", "a" * 64),)
    found = _select(classification, dependencies, _m("src/pkg/core.py"), provisional=provisional)
    assert found.provisional == provisional


def test_an_unavailable_old_view_takes_the_broad_path(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    found = _select(classification, dependencies, _m("src/pkg/core.py"), old_graph=False)
    assert found.fallback == ("old view unavailable",)


def test_selection_is_deterministic_and_every_node_has_a_reason(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    changes = (_m("src/pkg/core.py"), _m("tests/fixtures/sealed/model.json"), _m("docs/guide.md"))
    first = _select(classification, dependencies, *changes)
    second = _select(classification, dependencies, *reversed(changes))
    assert first == second
    assert list(first.nodes) == sorted(first.nodes)
    assert set(first.reasons) == set(first.nodes) and all(first.reasons.values())


def test_static_profiles_are_not_change_selected(
    classification: profiles.Classification, dependencies: profiles.DependencyMap,
) -> None:
    with pytest.raises(profiles.SelectionError, match="core"):
        _select(classification, dependencies, _m("src/pkg/core.py"), profile="core")


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        ('[selection]\nbroad_paths = "x"\n', "broad_paths"),
        ('[selection]\nunknown = []\n', "unknown"),
        ('[[inputs]]\npaths = ["x/**"]\nwhy = "w"\n', "exactly one of"),
        ('[[inputs]]\npaths = ["x/**"]\ntiers = ["fast"]\nwhy = "w"\n', "tier"),
        ('[[inputs]]\npaths = []\ntiers = ["proc"]\nwhy = "w"\n', "empty"),
    ],
)
def test_a_malformed_selection_section_is_refused(body: str, complaint: str) -> None:
    with pytest.raises(profiles.ManifestError, match=complaint):
        profiles.load_manifest('schema = "test-profiles-v1"\n' + body)


def test_relative_imports_resolve_from_the_importing_module_or_package(manifest: profiles.ProfileManifest) -> None:
    sources = {
        **_SOURCES,
        "src/pkg/sub/__init__.py": "from . import leaf\n",  # a package: `.` is the package itself
        "src/pkg/sibling.py": "from . import core\nfrom .sub import leaf\n",  # a module: `.` is its package
    }
    dependencies = profiles.build_dependency_map(sources, (*_TRACKED, "src/pkg/sibling.py"), manifest)
    assert "src/pkg/sub/__init__.py" in dependencies.importers["pkg.sub.leaf"]
    assert "src/pkg/sibling.py" in dependencies.importers["pkg.core"]
    assert "src/pkg/sibling.py" in dependencies.importers["pkg.sub.leaf"]
    assert "src/pkg/sub/leaf.py" in dependencies.importers["pkg.core"]  # `..core` from pkg.sub.leaf
