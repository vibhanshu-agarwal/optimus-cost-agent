"""MAIN-5 guard contract tests; subprocesses keep startup hooks isolated."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="MAIN-5 guard is Windows-only: it hooks _winapi and fails closed elsewhere",
)

_REPO = Path(__file__).resolve().parents[3]
_STARTUP = _REPO / "tools" / "testing" / "main5_startup"


@pytest.fixture(autouse=True)
def _local_port_guard_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit guard probes do not depend on the external kit's port guard."""
    stub = tmp_path / "port_guard_stub.py"
    stub.write_text("# Port guard is exercised by the runner's own control.\n", encoding="utf-8")
    monkeypatch.setenv("MAIN5_PORT_GUARD", str(stub))


def _guarded_probe(tmp_path: Path, probe: str) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]], Path]:
    protected = tmp_path / "protected"
    protected.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "source.txt").write_text("source", encoding="utf-8")
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(_STARTUP), str(_REPO / "src")))
    env["MAIN5_GUARD_LOG_DIR"] = str(logs_dir)
    env["MAIN5_CONTROL_PROTECTED_ROOT"] = str(protected)
    env["MAIN5_PROBE_SOURCE"] = str(outside / "source.txt")
    child = subprocess.run(
        [sys.executable, "-c", probe], env=env, capture_output=True, text=True, check=False,
    )
    rows = [
        json.loads(line)
        for path in logs_dir.glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    return child, rows, protected


@pytest.mark.parametrize(
    ("operation", "body", "expected_event"),
    [
        ("copy2", "shutil.copy2(source, target)", "_winapi.CopyFile2"),
        ("hardlink", "os.link(source, target)", "os.link"),
        ("symlink", "os.symlink(source, target)", "os.symlink"),
        ("sqlite", "sqlite3.connect(target).close()", "sqlite3.connect"),
        ("native_create_file", "handle = _winapi.CreateFile(str(target), _winapi.GENERIC_WRITE, 0, 0, 2, 0x80, 0); _winapi.CloseHandle(handle)", "_winapi.CreateFile"),
        ("native_junction", "_winapi.CreateJunction(str(source.parent), str(target))", "_winapi.CreateJunction"),
        ("extended_prefix", "target = Path('\\\\\\\\?\\\\' + str(target)); target.write_text('x')", "open"),
        ("admin_share", "target = Path('\\\\\\\\localhost\\\\' + target.drive[0] + '$' + str(target)[2:]); target.write_text('x')", "open"),
        ("extended_unc", "target = Path('\\\\\\\\?\\\\UNC\\\\localhost\\\\' + target.drive[0] + '$' + str(target)[2:]); target.write_text('x')", "open"),
    ],
)
def test_guard_blocks_censused_native_write_paths(
    tmp_path: Path, operation: str, body: str, expected_event: str,
) -> None:
    """Each observed native/audit path must be refused before a scratch-root write."""
    probe = (
        "import _winapi, os, shutil, sqlite3\n"
        "from pathlib import Path\n"
        "from contextlib import suppress\n"
        "source = Path(os.environ['MAIN5_PROBE_SOURCE'])\n"
        "target = Path(os.environ['MAIN5_CONTROL_PROTECTED_ROOT']) / 'blocked'\n"
        "with suppress(Exception):\n"
        + "\n".join("    " + line for line in body.splitlines()) + "\n"
    )
    child, rows, protected = _guarded_probe(tmp_path, probe)
    assert child.returncode == 0, child.stderr
    assert [row["code"] for row in rows] == ["MAIN5_WRITE"], (operation, rows, child.stderr)
    assert rows[0]["event"] == expected_event
    assert list(protected.iterdir()) == []


def test_guard_records_census_event_names_only(tmp_path: Path) -> None:
    """The census must expose actual interpreter events without path values."""
    child, rows, protected = _guarded_probe(
        tmp_path,
        "import os, sqlite3\nfrom pathlib import Path\n"
        "Path(os.environ['MAIN5_PROBE_SOURCE']).read_text()\n"
        "sqlite3.connect(':memory:').close()\n",
    )
    assert child.returncode == 0, child.stderr
    assert rows == [] and list(protected.iterdir()) == []
    census_files = list((tmp_path / "logs").glob("*.census"))
    assert len(census_files) == 1
    events = census_files[0].read_text(encoding="ascii").splitlines()
    assert "open" in events
    assert "sqlite3.connect/handle" in events
    assert all("\\" not in event and ":" not in event for event in events)


def test_guard_spawn_ledger_records_short_no_site_child_without_arguments(tmp_path: Path) -> None:
    """A Python child that skips sitecustomize must remain visible after exit."""
    child, rows, _ = _guarded_probe(
        tmp_path,
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-S', '-c', 'pass # SECRET_SPAWN_CANARY --token=x'], check=True)\n",
    )
    assert child.returncode == 0, child.stderr
    assert rows == []
    files = list((tmp_path / "logs").glob("*.spawn"))
    assert files
    raw = "".join(path.read_text(encoding="utf-8") for path in files)
    events = [json.loads(line) for line in raw.splitlines()]
    assert any(
        event["kind"] == "create_process"
        and isinstance(event["child_pid"], int)
        and isinstance(event["creation_time"], int)
        and event["flags"]["no_site"] is True
        and event["shape"] == "code"
        and event["image"].casefold().endswith("python.exe")
        for event in events
    )
    assert any(event["kind"] == "exit_code" and event["exit_code"] == 0 for event in events)
    assert any(event["kind"] == "audit_spawn" and event["event"] == "subprocess.Popen" for event in events)
    assert "SECRET_SPAWN_CANARY" not in raw
    assert "--token=x" not in raw


@pytest.mark.parametrize(
    ("arguments", "expected_shape", "no_site"),
    [
        (["--version"], "version_probe", False),
        (["-h"], "help_probe", False),
        (["-Sc", "pass"], "code", True),
        (["-IS", "-c", "pass"], "code", True),
    ],
)
def test_guard_spawn_ledger_classifies_python_argument_shape_without_text(
    tmp_path: Path, arguments: list[str], expected_shape: str, no_site: bool,
) -> None:
    probe = (
        "import subprocess, sys\n"
        f"subprocess.run([sys.executable, *{arguments!r}], check=True, "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
    )
    child, rows, _ = _guarded_probe(tmp_path, probe)
    assert child.returncode == 0, child.stderr
    assert rows == []
    raw = "".join(path.read_text(encoding="utf-8") for path in (tmp_path / "logs").glob("*.spawn"))
    events = [json.loads(line) for line in raw.splitlines()]
    created = [event for event in events if event["kind"] == "create_process"]
    assert len(created) == 1
    assert created[0]["shape"] == expected_shape
    assert created[0]["flags"]["no_site"] is no_site
    assert isinstance(created[0]["creation_time"], int)
    assert any(
        event["kind"] == "exit_code"
        and (event["child_pid"], event["creation_time"]) ==
        (created[0]["child_pid"], created[0]["creation_time"])
        and event["exit_code"] == 0
        for event in events
    )
    assert "pass" not in raw


def test_guard_spawn_ledger_joins_venv_launcher_to_guarded_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both guarded interpreters identify their parent without logging arguments."""
    monkeypatch.setenv("MAIN5_DIRECT_LAUNCH", "origin")
    child, rows, _ = _guarded_probe(
        tmp_path,
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-c', 'pass # SECRET_PAIR_CANARY'], check=True)\n",
    )
    assert child.returncode == 0, child.stderr
    assert rows == []
    files = list((tmp_path / "logs").glob("*.spawn"))
    events = [json.loads(line) for path in files for line in path.read_text(encoding="utf-8").splitlines()]
    starts = [event for event in events if event["kind"] == "guard_start"]
    creates = [event for event in events if event["kind"] == "create_process"]
    assert len(starts) == 2
    assert len(creates) == 1
    assert [start.get("runner_direct_role") for start in starts].count("origin") == 1
    assert [start.get("runner_direct_role") for start in starts].count(None) == 1
    assert starts[1]["parent_pid"] == creates[0]["child_pid"] or any(
        start["parent_pid"] == creates[0]["child_pid"] for start in starts
    )
    assert "SECRET_PAIR_CANARY" not in json.dumps(events)


def test_extended_device_namespace_is_refused_before_native_io(tmp_path: Path) -> None:
    """An unresolvable extended namespace must not become a cwd-relative alias."""
    child, rows, protected = _guarded_probe(
        tmp_path,
        "from contextlib import suppress\nimport sys\n"
        "with suppress(Exception):\n"
        "    sys.audit('open', r'\\\\?\\GLOBALROOT\\Device\\HarddiskVolume1\\unknown', 'w', 0)\n",
    )
    assert child.returncode == 0, child.stderr
    assert [row["code"] for row in rows] == ["MAIN5_WRITE"]
    assert list(protected.iterdir()) == []


def test_guard_allows_windows_null_logging_sink(tmp_path: Path) -> None:
    """Pytest's FileHandler opens NUL; it must not count as a root write."""
    child, rows, protected = _guarded_probe(
        tmp_path,
        "import os\nfrom pathlib import Path\n"
        "with open(Path(os.devnull).resolve(), 'a', encoding='utf-8') as stream:\n"
        "    stream.write('discarded')\n",
    )
    assert child.returncode == 0, child.stderr
    assert rows == [] and list(protected.iterdir()) == []


def test_guard_allows_named_pipe_transport_not_filesystem_write(tmp_path: Path) -> None:
    """Native CreateFile's pipe namespace is IPC, not an operator-root path."""
    child, rows, protected = _guarded_probe(
        tmp_path,
        "import sys\n"
        "sys.audit('_winapi.CreateFile', r'\\\\.\\pipe\\main5-probe', "
        "0x40000000, 0, 3, 0)\n",
    )
    assert child.returncode == 0, child.stderr
    assert rows == [] and list(protected.iterdir()) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows snapshot script")
def test_snapshot_has_stable_bytes_across_powershell_processes(tmp_path: Path) -> None:
    """A full projection must be byte-comparable across separate interpreters."""
    local = tmp_path / "Local"
    roaming = tmp_path / "Roaming"
    program = tmp_path / "Program"
    for root in (local, roaming, program):
        (root / "optimus-cost-agent").mkdir(parents=True)
        (root / "optimus-cost-agent" / "marker").write_text("x", encoding="utf-8")
    env = os.environ.copy()
    env.update({"LOCALAPPDATA": str(local), "APPDATA": str(roaming), "ProgramData": str(program)})
    script = _REPO / "tools" / "testing" / "main5_snapshot.ps1"
    outputs = [tmp_path / "first.json", tmp_path / "second.json"]
    for output in outputs:
        child = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(script), "-OutputFile", str(output)],
            env=env, capture_output=True, text=True, check=False,
        )
        assert child.returncode == 0, child.stderr + child.stdout
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert len(json.loads(outputs[0].read_text(encoding="utf-8"))["roots"]) == 4


def test_real_known_folder_adapter_is_refused_and_recorded(tmp_path: Path) -> None:
    """A real adapter lookup must leave a violation even if its error is caught."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(_STARTUP), str(_REPO / "src")))
    env["MAIN5_GUARD_LOG_DIR"] = str(tmp_path)
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from optimus.acp.trusted_paths import _real_windows_known_folders\n"
            "try:\n"
            "    _real_windows_known_folders()\n"
            "except Exception:\n"
            "    pass\n",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    logs = list(tmp_path.glob("*.jsonl"))
    assert len(logs) == 1, child.stderr
    rows = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
    assert [row["code"] for row in rows] == ["MAIN5_REAL_ADAPTER"]
    assert rows[0].get("test", "").startswith("tests/unit/acp/test_main5_guard.py::test_real_known_folder_adapter")
    assert "path" not in rows[0] and "content" not in rows[0]


def test_guard_does_not_import_optimus_before_the_test(tmp_path: Path) -> None:
    """A fresh measurement child must be free to select its own source tree."""
    child, rows, _ = _guarded_probe(
        tmp_path,
        "import sys\n"
        "assert 'optimus' not in sys.modules\n"
        "assert 'optimus.acp' not in sys.modules\n"
        "assert 'optimus.acp.trusted_paths' not in sys.modules\n",
    )
    assert child.returncode == 0, child.stderr
    assert rows == []


def test_guard_patches_the_source_tree_selected_after_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lazy hook must not pin a measurement child to the checkout's package."""
    source = tmp_path / "alternate-src"
    package = source / "optimus" / "acp"
    package.mkdir(parents=True)
    (source / "optimus" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "trusted_paths.py").write_text(
        "def _real_windows_known_folders():\n    return 'UNPATCHED'\n", encoding="utf-8",
    )
    monkeypatch.setenv("MAIN5_ALTERNATE_SOURCE", str(source))
    child, rows, _ = _guarded_probe(
        tmp_path,
        "import os, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, os.environ['MAIN5_ALTERNATE_SOURCE'])\n"
        "import optimus.acp.trusted_paths as trusted\n"
        "assert Path(trusted.__file__).resolve().is_relative_to(Path(os.environ['MAIN5_ALTERNATE_SOURCE']))\n"
        "try:\n"
        "    trusted._real_windows_known_folders()\n"
        "except RuntimeError as exc:\n"
        "    assert str(exc) == 'MAIN5_REAL_ADAPTER'\n"
        "else:\n"
        "    raise AssertionError('adapter escaped lazy patch')\n",
    )
    assert child.returncode == 0, child.stderr
    assert [row["code"] for row in rows] == ["MAIN5_REAL_ADAPTER"]


def test_guard_preserves_trusted_paths_loader_introspection(tmp_path: Path) -> None:
    """The patching loader must preserve source inspection for tooling."""
    child, rows, _ = _guarded_probe(
        tmp_path,
        "import inspect\n"
        "import optimus.acp.trusted_paths as trusted\n"
        "source = inspect.getsource(trusted.resolve_trusted_operator_roots)\n"
        "assert 'def resolve_trusted_operator_roots(' in source\n"
        "module_source = trusted.__loader__.get_source('optimus.acp.trusted_paths')\n"
        "assert 'def resolve_trusted_operator_roots(' in module_source\n",
    )
    assert child.returncode == 0, child.stderr
    assert rows == []


def test_guard_exits_if_lazy_adapter_patch_is_skipped(tmp_path: Path) -> None:
    """A skipped post-import assignment must fail closed, not expose real lookup."""
    startup = tmp_path / "startup-mutant"
    startup.mkdir()
    for name in ("sitecustomize.py", "main5_guard_impl.py"):
        (startup / name).write_bytes((_STARTUP / name).read_bytes())
    guard_file = startup / "main5_guard_impl.py"
    original = guard_file.read_text(encoding="utf-8")
    anchor = "module._real_windows_known_folders = _refuse_real_known_folders"
    assert original.count(anchor) == 1
    guard_file.write_text(original.replace(anchor, "pass  # planted skipped patch"), encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(startup), str(_REPO / "src")))
    env["MAIN5_GUARD_LOG_DIR"] = str(logs)
    child = subprocess.run(
        [sys.executable, "-c", "import optimus.acp.trusted_paths; print('UNPATCHED_CHILD_RAN')"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert child.returncode == 86, child.stderr
    assert "UNPATCHED_CHILD_RAN" not in child.stdout


def test_guard_record_works_when_json_dumps_is_monkeypatched(tmp_path: Path) -> None:
    """A test changing json.dumps must not disable violation evidence."""
    child, rows, _ = _guarded_probe(
        tmp_path,
        "import json\n"
        "json.dumps = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('patched'))\n"
        "from optimus.acp.trusted_paths import _real_windows_known_folders\n"
        "try:\n"
        "    _real_windows_known_folders()\n"
        "except RuntimeError:\n"
        "    pass\n",
    )
    assert child.returncode == 0, child.stderr
    assert [row["code"] for row in rows] == ["MAIN5_REAL_ADAPTER"]


def test_explicit_fake_known_folder_adapter_succeeds_without_violation(tmp_path: Path) -> None:
    """The same guarded interpreter admits explicitly injected temporary roots."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(_STARTUP), str(_REPO / "src")))
    env["MAIN5_GUARD_LOG_DIR"] = str(tmp_path)
    env["MAIN5_FAKE_FOLDER_BASE"] = str(tmp_path / "fake")
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os\n"
            "from pathlib import Path\n"
            "from types import SimpleNamespace\n"
            "from optimus.acp.trusted_paths import resolve_trusted_operator_roots\n"
            "base=Path(os.environ['MAIN5_FAKE_FOLDER_BASE'])\n"
            "folders=SimpleNamespace(roaming_appdata=base/'Roaming',local_appdata=base/'Local')\n"
            "roots=resolve_trusted_operator_roots(platform_name='win32',windows_known_folders=folders)\n"
            "assert roots.approval_runtime_root==folders.local_appdata/'optimus-cost-agent'\n",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    logs = list(tmp_path.glob("*.jsonl"))
    assert len(logs) == 1
    assert logs[0].read_text(encoding="utf-8") == ""


def test_suppressed_write_violation_is_recorded_without_writing(tmp_path: Path) -> None:
    """A swallowed audit exception must still leave evidence of the attempt."""
    protected = tmp_path / "protected"
    protected.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(_STARTUP), str(_REPO / "src")))
    env["MAIN5_GUARD_LOG_DIR"] = str(logs_dir)
    env["MAIN5_CONTROL_PROTECTED_ROOT"] = str(protected)
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from contextlib import suppress\n"
            "from pathlib import Path\n"
            "import os\n"
            "with suppress(Exception):\n"
            "    (Path(os.environ['MAIN5_CONTROL_PROTECTED_ROOT']) / 'blocked').write_text('x')\n",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    assert not (protected / "blocked").exists()
    logs = list(logs_dir.glob("*.jsonl"))
    assert len(logs) == 1, child.stderr
    rows = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
    assert [row["code"] for row in rows] == ["MAIN5_WRITE"]


def test_ambiguous_directory_descriptor_is_refused_and_recorded(tmp_path: Path) -> None:
    """A relative path with an unclassified dir_fd cannot bypass the hook."""
    protected = tmp_path / "protected"
    protected.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(_STARTUP), str(_REPO / "src")))
    env["MAIN5_GUARD_LOG_DIR"] = str(logs_dir)
    env["MAIN5_CONTROL_PROTECTED_ROOT"] = str(protected)
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from contextlib import suppress\n"
            "import sys\n"
            "with suppress(Exception):\n"
            "    sys.audit('os.rename','relative-source','relative-dest',91,-1)\n",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    rows = [json.loads(line) for path in logs_dir.glob("*.jsonl") for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["code"] for row in rows] == ["MAIN5_WRITE"]
    assert list(protected.iterdir()) == []


def test_failed_guard_startup_stops_child(tmp_path: Path) -> None:
    """An unavailable log sink cannot leave a live, unguarded interpreter."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(_STARTUP), str(_REPO / "src")))
    env["MAIN5_GUARD_LOG_DIR"] = str(tmp_path / "missing")
    child = subprocess.run(
        [sys.executable, "-c", "print('UNGUARDED_CHILD_RAN')"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 86
    assert "UNGUARDED_CHILD_RAN" not in child.stdout


def test_guard_refusal_row_has_fixed_code_and_process_identity_only(tmp_path: Path) -> None:
    """A startup refusal records no raw argument, path or content."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(_STARTUP), str(_REPO / "src")))
    env["MAIN5_GUARD_LOG_DIR"] = str(logs_dir)
    env["MAIN5_PORT_GUARD"] = str(tmp_path / "missing-port-guard.py")
    child = subprocess.run(
        [sys.executable, "-c", "print('SECRET_REFUSAL_CANARY')"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert child.returncode == 86
    assert "SECRET_REFUSAL_CANARY" not in child.stdout
    files = list(logs_dir.glob("*.jsonl"))
    assert len(files) == 1
    raw = files[0].read_text(encoding="utf-8")
    rows = [json.loads(line) for line in raw.splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == {"kind", "pid", "creation_time", "code"}
    assert row["kind"] == "guard_refusal"
    assert row["code"] == "port_guard_missing"
    assert isinstance(row["pid"], int) and row["pid"] > 0
    assert isinstance(row["creation_time"], int) and row["creation_time"] > 0
    assert "SECRET_REFUSAL_CANARY" not in raw
    assert str(tmp_path) not in raw


def test_audit_guard_allows_pipe_file_descriptors(tmp_path: Path) -> None:
    """Classified OS pipes are not filesystem writes beneath operator roots."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(_STARTUP), str(_REPO / "src")))
    env["MAIN5_GUARD_LOG_DIR"] = str(tmp_path)
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import subprocess,sys\n"
            "p=subprocess.Popen([sys.executable,'-c','print(42)'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)\n"
            "out,_=p.communicate()\n"
            "assert p.returncode==0 and out.strip()==b'42'\n",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    rows = [json.loads(line) for path in tmp_path.glob("*.jsonl") for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == []
