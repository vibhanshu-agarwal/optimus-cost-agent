"""Opt-in runner integration checks; outside pytest's default testpaths."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from coverage import CoverageData

_REPO = Path(__file__).resolve().parents[2]
_KIT_V3_MANIFEST_SHA256 = "A8C4244DF233C42446C498AE4C2AA5C859304D33CB1B740FD3275FAED6D2B75B"  # pragma: allowlist secret - kit v3 manifest identity pin


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell scored environment")
@pytest.mark.parametrize("powershell", ["powershell.exe", "pwsh.exe"])
@pytest.mark.parametrize("previous", ["present", "absent"])
def test_runner_scored_environment_selects_guarded_venv_and_preserves_cache_controls(
    tmp_path: Path, previous: str, powershell: str,
) -> None:
    # A leaked prefix changes the measurement controls; a missing override launches
    # shared-venv Python. The native child observes both, not a source-text pattern.
    observed = tmp_path / "observed.json"
    code = (
        "import json,os,sys; from pathlib import Path; "
        "Path(os.environ['MAIN5_ENV_OBSERVED']).write_text(json.dumps(dict("
        "venv=os.getenv('OPTIMUS_TEST_VENV'),prefix=os.getenv('PYTHONPYCACHEPREFIX'),"
        "prefix_present='PYTHONPYCACHEPREFIX' in os.environ,"
        "runtime_prefix=sys.pycache_prefix,no_bytecode=sys.dont_write_bytecode))); "
        "sys.exit(3)"
    )
    script = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Main5ScoredLane'},$true)
if(-not $function){throw 'SCORED_LANE_ENVIRONMENT_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
if($env:MAIN5_PREVIOUS_ENV -ceq 'present'){
  $env:OPTIMUS_TEST_VENV='prior-fixture-venv'; $env:PYTHONPYCACHEPREFIX='prior-fixture-prefix'
}else{
  Remove-Item Env:OPTIMUS_TEST_VENV -ErrorAction SilentlyContinue
  Remove-Item Env:PYTHONPYCACHEPREFIX -ErrorAction SilentlyContinue
}
$env:PYTHONDONTWRITEBYTECODE='prior-fixture-value'
function Assert-Restored {
  if($env:MAIN5_PREVIOUS_ENV -ceq 'present'){
    if($env:OPTIMUS_TEST_VENV -cne 'prior-fixture-venv' -or $env:PYTHONPYCACHEPREFIX -cne 'prior-fixture-prefix'){throw 'PREVIOUS_ENVIRONMENT_LOST'}
  }elseif((Test-Path Env:OPTIMUS_TEST_VENV) -or (Test-Path Env:PYTHONPYCACHEPREFIX)){throw 'ABSENT_ENVIRONMENT_NOT_RESTORED'}
  if($env:PYTHONDONTWRITEBYTECODE -cne 'prior-fixture-value'){throw 'BYTECODE_SETTING_NOT_RESTORED'}
}
$nativeExit=Invoke-Main5ScoredLane -Python $env:MAIN5_TEST_PYTHON -Venv $env:MAIN5_OWN_VENV -Arguments @('-c',$env:MAIN5_ENV_CODE) -Output $env:MAIN5_ENV_STDOUT
if($nativeExit -ne 3){throw 'NATIVE_EXIT_NOT_PRESERVED'}
Assert-Restored
try{
  Invoke-Main5ScoredLane -Python 'main5-deliberately-missing-program.exe' -Venv $env:MAIN5_OWN_VENV -Arguments @() -Output $env:MAIN5_ENV_STDOUT | Out-Null
  throw 'MISSING_PROGRAM_ACCEPTED'
}catch{if($_.Exception.Message -ceq 'MISSING_PROGRAM_ACCEPTED'){throw}}
Assert-Restored
'SCORED_ENVIRONMENT_PASS'
"""
    result = _runner_function_probe(
        script, powershell=powershell, MAIN5_PREVIOUS_ENV=previous, MAIN5_TEST_PYTHON=sys.executable,
        MAIN5_OWN_VENV=str(tmp_path / "attempt-venv"), MAIN5_ENV_CODE=code,
        MAIN5_ENV_OBSERVED=str(observed), MAIN5_ENV_STDOUT=str(tmp_path / "native.txt"),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(observed.read_text())
    assert payload == {
        "venv": "prior-fixture-venv" if previous == "present" else None, "prefix": None,
        "prefix_present": False, "runtime_prefix": None, "no_bytecode": True,
    }
    assert "SCORED_ENVIRONMENT_PASS" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell non-Python process gate")
@pytest.mark.parametrize("channel", ["ledger", "census"])
@pytest.mark.parametrize("case", ["foreign", "case_foreign", "own", "normalized_own", "self_own", "case_self_own", "nonvenv", "empty"])
def test_runner_rejects_foreign_venv_launchers_from_each_evidence_source(
    tmp_path: Path, channel: str, case: str,
) -> None:
    # Missing either join used to let pre-commit.exe launch shared-venv Python.
    own = tmp_path / "own"
    foreign = tmp_path / "own-shadow"
    self_own = tmp_path / "self-own"
    cache = tmp_path / "precommit-cache"
    for root in (own, foreign, self_own, cache):
        (root / "Scripts").mkdir(parents=True)
    for root in (own, foreign, self_own):
        (root / "pyvenv.cfg").write_text("home = synthetic-runtime\n")
    image = {
        "foreign": str(foreign / "Scripts" / "launcher.exe"),
        "case_foreign": str(foreign / "Scripts" / "launcher.exe").upper(),
        "own": str(own / "Scripts" / "launcher.exe"),
        "normalized_own": str(own / "Scripts" / ".." / "Scripts" / "launcher.exe"),
        "self_own": str(self_own / "Scripts" / "launcher.exe"),
        "case_self_own": str(self_own / "Scripts" / "launcher.exe").upper(),
        "nonvenv": str(cache / "Scripts" / "node.exe"),
        "empty": "",
    }[case]
    expected = "outside_attempt_venv" if case in {"foreign", "case_foreign"} else "unknown"
    script = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
foreach($name in @('Get-Main5NonPythonClassification','Get-Main5NonPythonDescendants')){
  $function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
  if($function){Invoke-Expression $function.Extent.Text}
}
$venv=$env:MAIN5_OWN_VENV
$selfTestVenv=$env:MAIN5_SELF_VENV
$created=@(); $ownRows=@(); $failures=@()
if($env:MAIN5_EVIDENCE_CHANNEL -ceq 'ledger'){
  $created=@([pscustomobject]@{kind='create_process';child_pid=123;parent_pid=100;creation_time=123456;image=$env:MAIN5_IMAGE;shape='script';flags=@{no_site=$false;isolated=$false;ignore_environment=$false}})
}else{
  $ownRows=@([pscustomobject]@{pid=123;ppid=100;image='launcher.exe';executable=$env:MAIN5_IMAGE;created_at='2026-09-30T00:00:00Z';tree_member=$true})
}
$assignment=$ast.Find({param($node) $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and $node.Left.Extent.Text -ceq '$nonPython'},$true)
if(-not $assignment){throw 'NON_PYTHON_CLASSIFICATION_MISSING'}
Invoke-Expression $assignment.Extent.Text
if($nonPython.Count -ne 1){throw 'EVIDENCE_ROW_NOT_CLASSIFIED'}
if($nonPython[0].classification -cne $env:MAIN5_EXPECTED_CLASS){throw ('WRONG_CLASS:'+ $nonPython[0].classification)}
$gate=$ast.Find({param($node) $node -is [System.Management.Automation.Language.IfStatementAst] -and $node.Extent.Text.StartsWith('if (@($nonPython')},$true)
if($gate){Invoke-Expression $gate.Extent.Text}
$tree=$ast.Find({param($node) $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and $node.Left.Extent.Text -ceq '$treeStatus'},$true)
Invoke-Expression $tree.Extent.Text
if($treeStatus -cne $env:MAIN5_EXPECTED_GATE){throw 'FOREIGN_LAUNCHER_GATE_NOT_ENFORCED'}
'NON_PYTHON_GATE_PASS'
"""
    result = _runner_function_probe(
        script, MAIN5_OWN_VENV=str(own), MAIN5_SELF_VENV=str(self_own), MAIN5_IMAGE=image,
        MAIN5_EVIDENCE_CHANNEL=channel, MAIN5_EXPECTED_CLASS=expected,
        MAIN5_EXPECTED_GATE="FAIL" if expected == "outside_attempt_venv" else "PASS",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "NON_PYTHON_GATE_PASS" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell combined coverage gate")
def test_runner_combines_lane_coverage_before_threshold(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text("".join(f"line_{index} = {index}\n" for index in range(10)), encoding="utf-8")
    config = tmp_path / ".coveragerc"
    config.write_text(f"[run]\nsource = {tmp_path}\n[report]\nfail_under = 80\n", encoding="utf-8")
    for name, lines in (("scored-coverage.data", {1}), ("self-test-coverage.data", {2})):
        data = CoverageData(basename=str(tmp_path / name))
        data.add_lines({str(source): lines})
        data.write()
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Main5CombinedCoverage'},$true)
if(-not $function){throw 'COMBINED_COVERAGE_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
$result=Invoke-Main5CombinedCoverage -Python $env:MAIN5_TEST_PYTHON -Attempt $env:MAIN5_COVERAGE_TEST_ROOT
if($result.combine_exit -ne 0 -or $result.report_exit -ne 2 -or $result.total -ge 80){throw 'LOW_COMBINED_COVERAGE_ACCEPTED'}
'COMBINED_COVERAGE_RED_GREEN_PASS'
"""
    result = _runner_function_probe(
        script,
        MAIN5_TEST_PYTHON=sys.executable,
        MAIN5_COVERAGE_TEST_ROOT=str(tmp_path),
        COVERAGE_RCFILE=str(config),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "COMBINED_COVERAGE_RED_GREEN_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell coverage role")
def test_runner_marks_coverage_helpers_and_restores_role(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text("value = 1\n", encoding="utf-8")
    config = tmp_path / ".coveragerc"
    config.write_text(f"[run]\nsource = {tmp_path}\n", encoding="utf-8")
    for name in ("scored-coverage.data", "self-test-coverage.data"):
        data = CoverageData(basename=str(tmp_path / name))
        data.add_lines({str(source): {1}})
        data.write()
    (tmp_path / "sitecustomize.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "with Path(os.environ['MAIN5_ROLE_LOG']).open('a', encoding='utf-8') as stream:\n"
        "    stream.write(os.environ.get('MAIN5_DIRECT_LAUNCH', '<missing>') + '\\n')\n",
        encoding="utf-8",
    )
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Main5CombinedCoverage'},$true)
if(-not $function){throw 'COMBINED_COVERAGE_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
$env:MAIN5_DIRECT_LAUNCH='before'
$result=Invoke-Main5CombinedCoverage -Python $env:MAIN5_TEST_PYTHON -Attempt $env:MAIN5_COVERAGE_TEST_ROOT
if($result.combine_exit -ne 0 -or $result.report_exit -ne 0){throw 'COMBINED_COVERAGE_FAILED'}
if($env:MAIN5_DIRECT_LAUNCH -cne 'before'){throw 'COVERAGE_ROLE_NOT_RESTORED'}
$roles=@(Get-Content -LiteralPath $env:MAIN5_ROLE_LOG)
if($roles.Count -ne 2 -or $roles[0] -cne 'coverage' -or $roles[1] -cne 'coverage'){throw 'COVERAGE_ROLE_MISSING'}
'COVERAGE_ROLE_PASS'
"""
    role_log = tmp_path / "roles.txt"
    result = _runner_function_probe(
        script,
        MAIN5_TEST_PYTHON=sys.executable,
        MAIN5_COVERAGE_TEST_ROOT=str(tmp_path),
        MAIN5_ROLE_LOG=str(role_log),
        COVERAGE_RCFILE=str(config),
        PYTHONPATH=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "COVERAGE_ROLE_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell coverage attribution")
def test_runner_attribution_allows_coverage_only_in_coverage_mode() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-Main5ScoredLedgerAttribution'},$true)
if(-not $function){throw 'LEDGER_ATTRIBUTION_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
$row=[pscustomobject]@{kind='guard_start';pid=10;creation_time=100;runner_direct_role=$null}
if(Test-Main5ScoredLedgerAttribution -SpawnRows @($row) -GuardRows @() -Mode Coverage){throw 'UNMARKED_COVERAGE_ACCEPTED'}
$row.runner_direct_role='coverage'
if(-not(Test-Main5ScoredLedgerAttribution -SpawnRows @($row) -GuardRows @() -Mode Coverage)){throw 'MARKED_COVERAGE_REJECTED'}
if(Test-Main5ScoredLedgerAttribution -SpawnRows @($row) -GuardRows @() -Mode Discover){throw 'COVERAGE_ROLE_ACCEPTED_IN_DISCOVER'}
'COVERAGE_ATTRIBUTION_PASS'
"""
    result = _runner_function_probe(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "COVERAGE_ATTRIBUTION_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows kit startup")
def test_port_guard_startup_log_redacts_arguments_and_redis_password(tmp_path: Path) -> None:
    """The versioned kit logs only a command shape and Redis endpoint."""
    kit = Path(os.environ["MAIN5_KIT_DIR"])
    log = tmp_path / "port-guard.jsonl"
    env = {
        **os.environ,
        "PYTHONPATH": str(kit / "port-guard"),
        "X1_GUARD_LOG": str(log),
        "OPTIMUS_REDIS_URL": "redis://:pw@h:1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", "pass", "--token=x"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    raw = log.read_text(encoding="utf-8")
    assert "--token=x" not in raw
    assert "pw" not in raw
    rows = [json.loads(line) for line in raw.splitlines()]
    start = next(row for row in rows if row["event"] == "process-start")
    assert start["argv0"] == "-c"
    assert start["shape"] == "code"
    assert (start["redis_scheme"], start["redis_host"], start["redis_port"]) == ("redis", "h", "1")
    assert "argv" not in start and "redis_url" not in start


def _runner(tmp_path: Path, mode: str, target: str = "") -> Path:
    kit = os.environ.get("MAIN5_KIT_DIR")
    assert kit, "Set MAIN5_KIT_DIR to the separately sealed sandbox review kit"
    attempt = tmp_path / "attempt"
    command = [
        "powershell.exe", "-NoProfile", "-File",
        str(_REPO / "tools" / "testing" / "run_main5_guarded_suite.ps1"),
        "-Mode", mode, "-AttemptDirectory", str(attempt), "-KitDirectory", kit,
    ]
    if target:
        command += ["-PytestTarget", target]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    return attempt


def _runner_function_probe(script: str, *, powershell: str = "powershell.exe", **extra_env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [powershell, "-NoProfile", "-Command", script],
        env={
            **os.environ,
            "MAIN5_RUNNER_SOURCE": str(_REPO / "tools/testing/run_main5_guarded_suite.ps1"),
            **extra_env,
        },
        capture_output=True, text=True, check=False,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell kit pin")
def test_runner_rejects_unpinned_or_changed_kit(tmp_path: Path) -> None:
    v3 = Path(os.environ["MAIN5_KIT_DIR"])
    assert v3.name == "main5-port-kit-v3-20260929"
    altered = tmp_path / "altered-v3"
    shutil.copytree(v3, altered)
    with (altered / "docker-shim" / "docker.cmd").open("ab") as stream:
        stream.write(b"x")
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
foreach($name in @('Get-Main5Sha256','Assert-Main5PinnedKit')){
  $function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
  if(-not $function){throw ('KIT_PIN_FUNCTION_MISSING:'+ $name)}
  Invoke-Expression $function.Extent.Text
}
foreach($bad in @($env:MAIN5_V1_KIT,$env:MAIN5_ALTERED_KIT)){
  try { Assert-Main5PinnedKit $bad | Out-Null; throw 'BAD_KIT_ACCEPTED' }
  catch { if($_.Exception.Message -cne 'MAIN5_KIT_NOT_PINNED'){throw} }
}
$pinned=Assert-Main5PinnedKit $env:MAIN5_KIT_DIR
if($pinned.manifest_sha256 -cne '__KIT_V3_SHA__' -or $pinned.entry_count -ne 17){throw 'GOOD_KIT_REJECTED'}
'KIT_PIN_PASS'
""".replace("__KIT_V3_SHA__", _KIT_V3_MANIFEST_SHA256)
    result = _runner_function_probe(
        script, MAIN5_KIT_DIR=str(v3), MAIN5_V1_KIT=str(v3.parents[1]),
        MAIN5_ALTERED_KIT=str(altered),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "KIT_PIN_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell collection result")
def test_runner_records_empty_and_interrupted_collection(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "missing").mkdir()
    (empty / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["missing"]\n', encoding="utf-8",
    )
    interrupted = tmp_path / "interrupted"
    interrupted.mkdir()
    (interrupted / "test_one.py").write_text("def test_one(): pass\n", encoding="utf-8")
    (interrupted / "conftest.py").write_text(
        "def pytest_collection(session):\n    raise KeyboardInterrupt()\n", encoding="utf-8",
    )
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Main5FullCollection'},$true)
if(-not $function){throw 'COLLECTION_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
foreach($case in @(@{Name='empty';Exit=5},@{Name='interrupted';Exit=2})){
  $caseRoot=Join-Path $env:MAIN5_COLLECTION_FIXTURE $case.Name
  $attempt=Join-Path $caseRoot 'attempt'
  New-Item -ItemType Directory -Path $attempt | Out-Null
  Push-Location -LiteralPath $caseRoot
  try {
    try { Invoke-Main5FullCollection -Python $env:MAIN5_TEST_PYTHON -Attempt $attempt -Arguments @('-m','pytest','-p','no:cacheprovider','--collect-only','-q') | Out-Null; throw 'BAD_COLLECTION_ACCEPTED' }
    catch { if($_.Exception.Message -cne ('MAIN5_FULL_COLLECTION_FAILED:'+ $case.Exit)){throw} }
  } finally { Pop-Location }
  $record=Get-Content -LiteralPath (Join-Path $attempt 'collection.json') -Raw | ConvertFrom-Json
  if($record.exit_code -ne $case.Exit -or $record.duration_seconds -lt 0 -or -not (Test-Path -LiteralPath $record.stderr_file)){throw 'COLLECTION_RECORD_WRONG'}
}
'COLLECTION_DIAGNOSTICS_PASS'
"""
    result = _runner_function_probe(
        script, MAIN5_COLLECTION_FIXTURE=str(tmp_path), MAIN5_TEST_PYTHON=sys.executable,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "COLLECTION_DIAGNOSTICS_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows per-run venv guard")
def test_runner_uses_attempt_venv_not_shared_venv(tmp_path: Path) -> None:
    """The runner must load this checkout's source from its attempt venv."""
    attempt = _runner(tmp_path, "Control")
    site_dir = attempt / "venv" / "Lib" / "site-packages"
    kit_paths = (site_dir / "main5-kit.pth").read_text(encoding="utf-8").splitlines()
    assert len(kit_paths) == 4
    assert not any(str(_REPO / ".venv").casefold() in path.casefold() for path in kit_paths)
    assert (site_dir / "sitecustomize.py").is_file()
    activation = site_dir / "00-main5-guard.pth"
    assert activation.is_file()
    assert activation.read_text(encoding="utf-8").strip().startswith("import os,sys; exec(")
    assert (site_dir / "main5_activate.py").is_file()
    config = json.loads((site_dir / "main5-config.json").read_text(encoding="utf-8"))
    assert set(config) >= {"log_dir", "control_protected_root", "port_guard", "X1_GUARD_LOG", "KEYRING_AUDIT_LOG"}
    assert "PYTHON_KEYRING_BACKEND" not in config
    assert not (site_dir / "main5-dependencies.pth").exists()
    assert not (_REPO / ".venv" / "Lib" / "site-packages" / "main5-dependencies.pth").exists()
    metadata = json.loads((attempt / "metadata.json").read_text(encoding="utf-8-sig"))
    assert Path(metadata["resolved_bash"]).name.casefold() == "bash.exe"
    assert "windows\\system32" not in metadata["resolved_bash"].casefold()
    assert Path(metadata["resolved_uv"]).name.casefold() == "uv.exe"
    assert Path(metadata["origins"]["optimus"]).resolve().is_relative_to(_REPO / "src")
    assert Path(metadata["origins"]["pydantic"]).resolve().is_relative_to(site_dir)
    assert Path(metadata["origins"]["zr_marker"]).resolve().is_relative_to(Path(os.environ["MAIN5_KIT_DIR"]))
    cache = Path(metadata["pycache_prefix"]).resolve()
    assert cache == Path(metadata["work_roots"]["collection_pycache"]).resolve()
    assert cache.parent == Path(metadata["short_work_root"]).resolve()
    assert not any(str(_REPO / ".venv").casefold() in path.casefold() for path in metadata["sys_path"])
    git_status = subprocess.run(
        ["git", "-C", str(_REPO), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    )
    assert metadata["worktree_clean"] is (not git_status.stdout.strip())
    assert metadata["worktree_entry_count"] == len(git_status.stdout.splitlines())
    assert metadata["control_guard_config_sha256"] == hashlib.sha256(
        (attempt / "control-config.json").read_bytes()
    ).hexdigest().upper()
    assert metadata["attempt_guard_config_sha256"] == hashlib.sha256(
        (attempt / "attempt-config.json").read_bytes()
    ).hexdigest().upper()
    control_rows = [
        json.loads(line)
        for path in (attempt / "control-logs").glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert sorted((row["test"], row["code"]) for row in control_rows) == sorted(
        (test, code)
        for test in ("MAIN5_CONTROL_PARENT", "MAIN5_CONTROL_CHILD")
        for code in ("MAIN5_REAL_ADAPTER", "MAIN5_WRITE")
    )
    assert not any(
        json.loads(line).get("test", "").startswith("MAIN5_CONTROL")
        for path in (attempt / "logs").glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows root projection")
def test_runner_compares_full_roots_for_a_safe_target(tmp_path: Path) -> None:
    """A selected guarded suite must prove root invariance, not just test pass."""
    attempt = _runner(tmp_path, "Suite", "tests/unit/telemetry/test_jsonl.py")
    result_data = json.loads((attempt / "result.json").read_text(encoding="utf-8-sig"))
    assert result_data["suite_exit"] == 0
    assert result_data["roots_unchanged"] is True
    assert result_data["violation_count"] == 0
    assert len(json.loads((attempt / "before.json").read_text(encoding="utf-8-sig"))["roots"]) == 4


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process census")
def test_runner_records_foreign_optimus_pytest_without_failing(tmp_path: Path) -> None:
    """A sibling test is attribution evidence, not a process-tree failure."""
    kit = os.environ.get("MAIN5_KIT_DIR")
    assert kit
    attempt = tmp_path / "attempt"
    foreign = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(90)  # optimus pytest SECRET_CENSUS_CANARY"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.2)
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(_REPO / "tools" / "testing" / "run_main5_guarded_suite.ps1"),
             "-Mode", "Control", "-AttemptDirectory", str(attempt), "-KitDirectory", kit],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        verdict = json.loads((attempt / "result.json").read_text(encoding="utf-8-sig"))
        assert verdict["process_tree_status"] == "PASS"
        assert verdict["foreign_process_count"] >= 1
        raw_census = (attempt / "process-census.jsonl").read_text(encoding="utf-8")
        assert "SECRET_CENSUS_CANARY" not in raw_census
        census = [json.loads(line) for line in raw_census.splitlines()]
        assert any(
            row.get("foreign") is True and row.get("pid") == foreign.pid
            and row.get("match_reason") == "optimus_pytest"
            and all(key in row for key in ("ppid", "image", "executable", "created_at", "worktree_root"))
            for snapshot in census for row in snapshot["processes"]
        )
        assert all("command_line" not in row and "argv" not in row for snapshot in census for row in snapshot["processes"])
    finally:
        foreign.terminate()
        foreign.wait(timeout=10)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process census")
def test_runner_fails_short_no_site_python_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing the spawn-ledger join must let this no-site child escape."""
    kit = os.environ["MAIN5_KIT_DIR"]
    attempt = tmp_path / "attempt"
    monkeypatch.setenv("MAIN5_RUNNER_PROBE", "no_site")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(_REPO / "tools/testing/run_main5_guarded_suite.ps1"),
         "-Mode", "Suite", "-AttemptDirectory", str(attempt), "-KitDirectory", kit,
         "-PytestTarget", "tests/unit/acp/test_stdio_ndjson.py::test_main5_runner_no_site_probe"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    verdict = json.loads((attempt / "result.json").read_text(encoding="utf-8-sig"))
    assert verdict["suite_exit"] == 0
    assert verdict["process_tree_status"] == "FAIL"
    assert "no_site" in verdict["process_tree_failures"]
    assert verdict["violation_count"] == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process ledger")
@pytest.mark.parametrize(
    ("probe", "expected_status", "expected_class", "expected_failure"),
    [
        ("version", "PASS", "no_code_probe", None),
        ("guard_exit_86", "PASS", "launcher_pair", None),
        ("combined_no_site", "FAIL", "no_site", "no_site"),
        ("base_interpreter", "FAIL", "outside_attempt_venv", "outside_attempt_venv"),
    ],
)
def test_runner_classifies_no_code_and_failed_python_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    probe: str, expected_status: str, expected_class: str, expected_failure: str | None,
) -> None:
    kit = os.environ["MAIN5_KIT_DIR"]
    attempt = tmp_path / "attempt"
    monkeypatch.setenv("MAIN5_RUNNER_PROBE", probe)
    command = [
        "powershell.exe", "-NoProfile", "-File", str(_REPO / "tools/testing/run_main5_guarded_suite.ps1"),
        "-Mode", "Suite", "-AttemptDirectory", str(attempt), "-KitDirectory", kit,
        "-PytestTarget", f"tests/unit/acp/test_stdio_ndjson.py::test_main5_runner_{probe}_probe",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    verdict = json.loads((attempt / "result.json").read_text(encoding="utf-8-sig"))
    metadata = json.loads((attempt / "metadata.json").read_text(encoding="utf-8-sig"))
    archive = metadata["scored_basetemp_archive"]
    assert archive["basetemp_created"] is False
    assert hashlib.sha256(Path(archive["path"]).read_bytes()).hexdigest().upper() == archive["sha256"]
    import zipfile

    with zipfile.ZipFile(archive["path"]) as zipped:
        assert zipped.namelist() == []
    assert verdict["suite_exit"] == 0, result.stdout + result.stderr
    assert verdict["process_tree_status"] == expected_status
    assert (result.returncode == 0) is (expected_status == "PASS")
    assert any(row["classification"] == expected_class for row in verdict["python_classifications"])
    if expected_failure:
        assert expected_failure in verdict["process_tree_failures"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process census")
def test_runner_counts_guarded_launcher_pair_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The venv redirector must not count as an unguarded interpreter."""
    monkeypatch.setenv("MAIN5_RUNNER_PROBE", "guarded_pair")
    attempt = _runner(tmp_path, "Suite", "tests/unit/acp/test_stdio_ndjson.py::test_main5_runner_guarded_pair_probe")
    verdict = json.loads((attempt / "result.json").read_text(encoding="utf-8-sig"))
    assert verdict["process_tree_status"] == "PASS"
    assert verdict["launcher_pair_count"] >= 2  # suite root plus the planted child
    assert verdict["guard_process_count"] == verdict["guarded_execution_count"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process census")
def test_runner_fails_suppressed_real_root_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A swallowed write error still fails the own-tree safety verdict."""
    kit = os.environ["MAIN5_KIT_DIR"]
    attempt = tmp_path / "attempt"
    monkeypatch.setenv("MAIN5_RUNNER_PROBE", "real_root_write")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(_REPO / "tools/testing/run_main5_guarded_suite.ps1"),
         "-Mode", "Suite", "-AttemptDirectory", str(attempt), "-KitDirectory", kit,
         "-PytestTarget", "tests/unit/acp/test_stdio_ndjson.py::test_main5_runner_real_root_write_probe"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    verdict = json.loads((attempt / "result.json").read_text(encoding="utf-8-sig"))
    assert verdict["suite_exit"] == 0
    assert verdict["violation_count"] >= 1
    assert verdict["root_status"] == "CLEAN"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell verdict helper")
def test_root_verdict_distinguishes_foreign_confounding_from_own_write() -> None:
    """The actual runner verdict must treat shared-root deltas as attribution."""
    runner = _REPO / "tools/testing/run_main5_guarded_suite.ps1"
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-Main5RootVerdict'},$true)
if(-not $function){throw 'ROOT_VERDICT_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
@(
  (Get-Main5RootVerdict $false $true 0),
  (Get-Main5RootVerdict $false $false 0),
  (Get-Main5RootVerdict $true $true 1),
  (Get-Main5RootVerdict $true $false 0)
) -join ','
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        env={**os.environ, "MAIN5_RUNNER_SOURCE": str(runner)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CONFOUNDED,FAIL,CLEAN,CLEAN"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell process identity")
def test_process_identity_does_not_conflate_reused_pids() -> None:
    """A PID reused later is a second execution, not the first child's log."""
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-Main5IdentityKey'},$true)
if(-not $function){throw 'PROCESS_IDENTITY_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
$first=Get-Main5IdentityKey 4100 100000
$second=Get-Main5IdentityKey 4100 200000
if($first -eq $second){throw 'REUSED_PID_CONFLATED'}
try { Get-Main5IdentityKey 4100 $null | Out-Null; throw 'MISSING_TIME_ACCEPTED' }
catch { if($_.Exception.Message -eq 'MISSING_TIME_ACCEPTED'){throw} }
'IDENTITY_PASS'
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        env={**os.environ, "MAIN5_RUNNER_SOURCE": str(_REPO / "tools/testing/run_main5_guarded_suite.ps1")},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "IDENTITY_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell child verdict")
def test_unlogged_child_verdict_requires_observed_no_code_exit() -> None:
    """A process killed before site with no observed exit stays fatal."""
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-Main5UnloggedVerdict'},$true)
if(-not $function){throw 'UNLOGGED_VERDICT_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
@(
  (Get-Main5UnloggedVerdict 'version_probe' 0),
  (Get-Main5UnloggedVerdict 'help_probe' 0),
  (Get-Main5UnloggedVerdict 'code' 86),
  (Get-Main5UnloggedVerdict 'code' $null),
  (Get-Main5UnloggedVerdict 'code' 0)
) -join ','
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        env={**os.environ, "MAIN5_RUNNER_SOURCE": str(_REPO / "tools/testing/run_main5_guarded_suite.ps1")},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "no_code_probe,no_code_probe,nonzero_exit,exit_unobserved,unlogged_python"
    )

@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lane partition")
def test_runner_partitions_the_collected_suite_exactly_once() -> None:
    """The whole MAIN-5 guard file is the sole self-test lane."""
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-Main5LanePartition'},$true)
if(-not $function){throw 'LANE_PARTITION_FUNCTION_MISSING'}
$overlap=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-Main5LaneOverlap'},$true)
if(-not $overlap){throw 'LANE_OVERLAP_FUNCTION_MISSING'}
Invoke-Expression $overlap.Extent.Text
Invoke-Expression $function.Extent.Text
$full=@('tests/unit/acp/test_main5_guard.py::guard_a','tests/unit/acp/test_main5_guard.py::guard_b','tests/unit/acp/test_stdio_ndjson.py::stdio_a')
$partition=Get-Main5LanePartition -FullNodeIds $full -SelfTestFile 'tests/unit/acp/test_main5_guard.py'
$partition | ConvertTo-Json -Compress -Depth 4
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        env={**os.environ, "MAIN5_RUNNER_SOURCE": str(_REPO / "tools/testing/run_main5_guarded_suite.ps1")},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    partition = json.loads(result.stdout.strip())
    assert partition["full_count"] == 3
    assert partition["self_test_nodeids"] == [
        "tests/unit/acp/test_main5_guard.py::guard_a",
        "tests/unit/acp/test_main5_guard.py::guard_b",
    ]
    assert partition["scored_nodeids"] == ["tests/unit/acp/test_stdio_ndjson.py::stdio_a"]


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lane partition")
def test_runner_partition_rejects_duplicate_nodeids_and_missing_self_test() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-Main5LanePartition'},$true)
if(-not $function){throw 'LANE_PARTITION_FUNCTION_MISSING'}
$overlap=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-Main5LaneOverlap'},$true)
if(-not $overlap){throw 'LANE_OVERLAP_FUNCTION_MISSING'}
Invoke-Expression $overlap.Extent.Text
Invoke-Expression $function.Extent.Text
foreach($case in @(
  @{ Full=@('tests/unit/acp/test_main5_guard.py::x','tests/unit/acp/test_main5_guard.py::x'); Expected='MAIN5_DUPLICATE_NODEID' },
  @{ Full=@('tests/unit/acp/test_stdio_ndjson.py::x'); Expected='MAIN5_SELF_TEST_FILE_MISSING' }
)){
  try { Get-Main5LanePartition -FullNodeIds $case.Full -SelfTestFile 'tests/unit/acp/test_main5_guard.py' | Out-Null; throw 'BAD_PARTITION_ACCEPTED' }
  catch { if($_.Exception.Message -cne $case.Expected){throw} }
}
'PARTITION_REJECTIONS_PASS'
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        env={**os.environ, "MAIN5_RUNNER_SOURCE": str(_REPO / "tools/testing/run_main5_guarded_suite.ps1")},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PARTITION_REJECTIONS_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lane partition")
def test_runner_partition_preserves_case_distinct_nodeids_and_file_prefix() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-Main5LanePartition'},$true)
$overlap=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-Main5LaneOverlap'},$true)
if(-not $overlap){throw 'LANE_OVERLAP_FUNCTION_MISSING'}
Invoke-Expression $overlap.Extent.Text
Invoke-Expression $function.Extent.Text
$full=@('tests/unit/acp/test_main5_guard.py::answer[y]','tests/unit/acp/test_main5_guard.py::answer[Y]','tests/unit/acp/test_main5_guard.py::answer[yes]','tests/unit/acp/test_main5_guard.py::answer[YES]','tests/unit/acp/TEST_MAIN5_GUARD.py::answer[y]')
$partition=Get-Main5LanePartition -FullNodeIds $full -SelfTestFile 'tests/unit/acp/test_main5_guard.py'
if($partition.full_count -ne 5 -or $partition.self_test_nodeids.Count -ne 4 -or $partition.scored_nodeids.Count -ne 1){throw 'CASE_DISTINCT_PARTITION_FAILED'}
if($partition.scored_nodeids[0] -cne 'tests/unit/acp/TEST_MAIN5_GUARD.py::answer[y]'){throw 'CASE_VARIANT_PREFIX_JOINED_SELF_TEST'}
'CASE_DISTINCT_PARTITION_PASS'
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        env={**os.environ, "MAIN5_RUNNER_SOURCE": str(_REPO / "tools/testing/run_main5_guarded_suite.ps1")},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CASE_DISTINCT_PARTITION_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lane partition")
def test_runner_partition_overlap_is_case_sensitive() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-Main5LaneOverlap'},$true)
if(-not $function){throw 'LANE_OVERLAP_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
$self=@('tests/unit/acp/test_main5_guard.py::answer[y]')
$caseVariant=@('tests/unit/acp/TEST_MAIN5_GUARD.py::answer[y]')
if(Test-Main5LaneOverlap -Scored $caseVariant -SelfTest $self){throw 'CASE_VARIANT_OVERLAP'}
if(-not (Test-Main5LaneOverlap -Scored $self -SelfTest $self)){throw 'EXACT_OVERLAP_MISSED'}
'ORDINAL_OVERLAP_PASS'
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        env={**os.environ, "MAIN5_RUNNER_SOURCE": str(_REPO / "tools/testing/run_main5_guarded_suite.ps1")},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ORDINAL_OVERLAP_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell target resolution")
def test_runner_resolves_only_delimited_collected_targets() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-Main5TargetNodeIds'},$true)
if(-not $function){throw 'TARGET_RESOLVER_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
$file='tests/unit/tools/test_example.py'
$self='tests/unit/acp/test_main5_guard.py'
$full=@(
  ($file+'::test_func[normal-start]'),
  ($file+'::test_func[delayed-start]'),
  ($file+'::test_func_longer'),
  ($file+'::test_func_longer[one]'),
  ($file+'::TestGroup::test_one'),
  ($file+'::TestGroup::test_two'),
  ($self+'::test_guard_one'),
  ($self+'::test_guard_two')
)
$selfIds=@($full | Where-Object { $_.StartsWith($self+'::',[StringComparison]::Ordinal) })
function Resolve([string]$target){
  return @(Get-Main5TargetNodeIds -FullNodeIds $full -Target $target -SelfTestFile $self -SelfTestNodeIds $selfIds)
}
$param=@(Resolve ($file+'::test_func'))
if($param.Count -ne 2 -or $param[0] -cne ($file+'::test_func[normal-start]') -or $param[1] -cne ($file+'::test_func[delayed-start]')){throw 'PARAM_TARGET_WRONG'}
$wholeFile=@(Resolve $file)
if($wholeFile.Count -ne 6){throw 'FILE_TARGET_WRONG'}
$group=@(Resolve ($file+'::TestGroup'))
if($group.Count -ne 2){throw 'CLASS_TARGET_WRONG'}
$longer=@(Resolve ($file+'::test_func_longer'))
if($longer.Count -ne 2){throw 'LONGER_TARGET_WRONG'}
$selfWhole=@(Resolve $self)
if($selfWhole.Count -ne 2){throw 'SELF_TEST_WHOLE_FILE_WRONG'}
foreach($case in @(
  @{Target=($file+'::missing');Expected='MAIN5_TARGET_NOT_COLLECTED'},
  @{Target=($file+'::TEST_FUNC');Expected='MAIN5_TARGET_NOT_COLLECTED'},
  @{Target=($self+'::test_guard_one');Expected='MAIN5_SELF_TEST_TARGET_MUST_BE_WHOLE_FILE'}
)){
  try { Resolve $case.Target | Out-Null; throw 'BAD_TARGET_ACCEPTED' }
  catch { if($_.Exception.Message -cne $case.Expected){throw} }
}
'TARGET_RESOLUTION_PASS'
"""
    result = _runner_function_probe(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "TARGET_RESOLUTION_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell working-root bound")
def test_runner_rejects_deep_windows_working_roots() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Assert-Main5WorkRoots'},$true)
if(-not $function){throw 'WORK_ROOT_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
$short=@{scored_basetemp='C:\worktrees\m5t\12345678\s';self_test_basetemp='C:\worktrees\m5t\12345678\t';collection_pycache='C:\worktrees\m5t\12345678\pc'}
$result=Assert-Main5WorkRoots -Roots $short -LongPathsEnabled 0
if($result.scored_basetemp -gt 40 -or $result.self_test_basetemp -gt 40){throw 'SHORT_ROOT_LENGTH_WRONG'}
$deep=@{scored_basetemp=('C:\' + ('x' * 137));self_test_basetemp=$short.self_test_basetemp;collection_pycache=$short.collection_pycache}
try{Assert-Main5WorkRoots -Roots $deep -LongPathsEnabled 0 | Out-Null;throw 'DEEP_ROOT_ACCEPTED'}
catch{if($_.Exception.Message -cne 'MAIN5_WORK_ROOT_TOO_DEEP'){throw}}
$enabled=Assert-Main5WorkRoots -Roots $deep -LongPathsEnabled 1
if($enabled.scored_basetemp -le 60){throw 'LONG_PATH_SETTING_IGNORED'}
'WORK_ROOT_BOUND_PASS'
"""
    result = _runner_function_probe(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "WORK_ROOT_BOUND_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell basetemp archive")
def test_runner_archives_basetemp_without_removing_short_root(tmp_path: Path) -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
foreach($name in @('Get-Main5Sha256','Save-Main5BasetempArchive')){
  $function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
  if(-not $function){throw ('ARCHIVE_FUNCTION_MISSING:'+$name)}
  Invoke-Expression $function.Extent.Text
}
$attempt=$env:MAIN5_ARCHIVE_TEST_ROOT
$base=Join-Path $attempt 's'
New-Item -ItemType Directory -Path $base | Out-Null
[IO.File]::WriteAllText((Join-Path $base '.hidden'),'evidence')
$result=Save-Main5BasetempArchive -Basetemp $base -Attempt $attempt -Lane 'scored'
if(-not(Test-Path -LiteralPath $base)){throw 'SHORT_ROOT_REMOVED'}
if((Get-Main5Sha256 $result.path) -cne $result.sha256){throw 'ARCHIVE_HASH_WRONG'}
if(-not $result.basetemp_created){throw 'EXISTING_BASETEMP_NOT_RECORDED'}
$zip=[IO.Compression.ZipFile]::OpenRead($result.path)
try{if(-not @($zip.Entries | Where-Object {$_.FullName.Replace('\','/') -ceq 's/.hidden'}).Count){throw 'HIDDEN_EVIDENCE_MISSING'}}
finally{$zip.Dispose()}
'BASETEMP_ARCHIVE_PASS'
"""
    result = _runner_function_probe(script, MAIN5_ARCHIVE_TEST_ROOT=str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "BASETEMP_ARCHIVE_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell multi-target resolution")
def test_runner_resolves_ordinal_multi_target_union() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
foreach($name in @('Get-Main5TargetNodeIds','Resolve-Main5TargetSet')){
  $function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
  if(-not $function){throw ('TARGET_FUNCTION_MISSING:'+$name)}
  Invoke-Expression $function.Extent.Text
}
$a='tests/unit/tools/test_one.py'
$b='tests/unit/tools/test_two.py'
$self='tests/unit/acp/test_main5_guard.py'
$full=@(($a+'::test_first'),($a+'::test_second'),($b+'::test_third'),($self+'::test_guard'))
$selfIds=@(($self+'::test_guard'))
function Resolve([string[]]$targets){return @(Resolve-Main5TargetSet -FullNodeIds $full -Targets $targets -SelfTestFile $self -SelfTestNodeIds $selfIds)}
$selected=@(Resolve @(($a+'::test_first'),($b+'::test_third')))
if($selected.Count -ne 2 -or $selected[0] -cne ($a+'::test_first') -or $selected[1] -cne ($b+'::test_third')){throw 'MULTI_TARGET_WRONG'}
foreach($case in @(
  @{Targets=@(($a+'::test_first'),($a+'::test_first'));Expected='MAIN5_DUPLICATE_TEST_TARGET'},
  @{Targets=@($a,($a+'::test_first'));Expected='MAIN5_DUPLICATE_TEST_TARGET'},
  @{Targets=@(($a+'::test_first'),($b+'::missing'));Expected='MAIN5_TARGET_NOT_COLLECTED'}
)){
  try{Resolve $case.Targets | Out-Null;throw 'BAD_TARGETS_ACCEPTED'}
  catch{if($_.Exception.Message -cne $case.Expected){throw}}
}
'MULTI_TARGET_PASS'
"""
    result = _runner_function_probe(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "MULTI_TARGET_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell launcher verdict")
def test_runner_classifies_the_four_observed_launchers_by_runtime() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-Main5LauncherVerdict'},$true)
if(-not $function){throw 'RUNTIME_VERDICT_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
function Launcher($procId,$created,$shape){[pscustomobject]@{child_pid=$procId;creation_time=$created;shape=$shape;flags=[pscustomobject]@{no_site=$false}}}
function Runtime($kind,$procId,$created,$parent,$parentCreated){[pscustomobject]@{kind=$kind;pid=$procId;creation_time=$created;parent_pid=$parent;parent_creation_time=$parentCreated}}
function Check($create,$begins,$starts,$exitCode,$want,$runtimePid){
  $got=Get-Main5LauncherVerdict -Create $create -Begins $begins -Starts $starts -ObservedExit $exitCode -HasRefusal $false
  if($got.classification -cne $want -or $got.runtime_pid -ne $runtimePid){throw ('WRONG_RUNTIME_VERDICT '+$create.child_pid+' '+$got.classification)}
}
$c40220=Launcher 40220 ([long]134351722784387018) 'script'
$b50996=Runtime 'guard_begin' 50996 ([long]134351722784699885) 40220 ([long]134351722784387018)
$s50996=Runtime 'guard_start' 50996 ([long]134351722784699885) 40220 ([long]134351722784387018)
Check $c40220 @($b50996) @($s50996) 0 'launcher_pair' 50996
$c31484=Launcher 31484 ([long]134351722809218684) 'script'
$b44116=Runtime 'guard_begin' 44116 ([long]134351722809493204) 31484 ([long]134351722809218684)
$s44116=Runtime 'guard_start' 44116 ([long]134351722809493204) 31484 ([long]134351722809218684)
Check $c31484 @($b44116) @($s44116) 1 'launcher_pair' 44116
$c15184=Launcher 15184 ([long]134351722819219278) 'code'
$b29740=Runtime 'guard_begin' 29740 ([long]134351722819459771) 15184 ([long]134351722819219278)
Check $c15184 @($b29740) @() $null 'killed_in_guard_setup' 29740
$c5412=Launcher 5412 ([long]134351722224113205) 'code'
$b47708=Runtime 'guard_begin' 47708 ([long]134351722224382237) 5412 ([long]134351722224113205)
$s47708=Runtime 'guard_start' 47708 ([long]134351722224382237) 5412 ([long]134351722224113205)
Check $c5412 @($b47708) @($s47708) 0 'launcher_pair' 47708
Check (Launcher 11 ([long]110) 'code') @() @() 0 'activation_bypassed' $null
Check (Launcher 12 ([long]120) 'code') @((Runtime 'guard_begin' 21 ([long]210) 12 ([long]120)),(Runtime 'guard_begin' 22 ([long]220) 12 ([long]120))) @() 1 'ambiguous_runtime' $null
Check (Launcher 13 ([long]130) 'code') @((Runtime 'guard_begin' 23 ([long]230) 13 ([long]130))) @() 0 'activation_bypassed' 23
Check (Launcher 14 ([long]140) 'code') @() @() 1 'no_site_reached' $null
Check (Launcher 15 ([long]150) 'version_probe') @() @() 0 'no_code_probe' $null
$noSite=Launcher 16 ([long]160) 'code'
$noSite.flags.no_site=$true
if((Get-Main5LauncherVerdict -Create $noSite -Begins @() -Starts @() -ObservedExit 1 -HasRefusal $false).classification -cne 'no_site'){throw 'NO_SITE_PRECEDENCE_LOST'}
if((Get-Main5LauncherVerdict -Create $c40220 -Begins @($b50996) -Starts @($s50996) -ObservedExit 0 -HasRefusal $true).classification -cne 'guard_refusal'){throw 'REFUSAL_PRECEDENCE_LOST'}
'RUNTIME_VERDICTS_PASS'
"""
    result = _runner_function_probe(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "RUNTIME_VERDICTS_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell ledger attribution")
def test_runner_rejects_control_rows_in_the_scored_ledger() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-Main5ScoredLedgerAttribution'},$true)
if(-not $function){throw 'LEDGER_ATTRIBUTION_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
$spawn=@(
  [pscustomobject]@{kind='guard_start';pid=10;creation_time=100;runner_direct_role='suite'},
  [pscustomobject]@{kind='create_process';parent_pid=10;parent_creation_time=100;child_pid=20;creation_time=200},
  [pscustomobject]@{kind='guard_begin';pid=30;creation_time=300;parent_pid=20;parent_creation_time=200},
  [pscustomobject]@{kind='guard_start';pid=30;creation_time=300;parent_pid=20;parent_creation_time=200}
)
$good=@([pscustomobject]@{pid=30;creation_time=300;code='MAIN5_WRITE'})
if(-not (Test-Main5ScoredLedgerAttribution -SpawnRows $spawn -GuardRows $good)){throw 'GOOD_LEDGER_REJECTED'}
$bad=@($good)+@([pscustomobject]@{pid=40;creation_time=400;code='MAIN5_WRITE';test='MAIN5_CONTROL_PARENT'})
if(Test-Main5ScoredLedgerAttribution -SpawnRows $spawn -GuardRows $bad){throw 'CONTROL_ROW_ATTRIBUTED'}
'LEDGER_ATTRIBUTION_PASS'
"""
    result = _runner_function_probe(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "LEDGER_ATTRIBUTION_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell control ledger")
def test_runner_requires_all_four_control_codes(tmp_path: Path) -> None:
    parent = tmp_path / "parent.jsonl"
    child = tmp_path / "child.jsonl"
    for path, identity in ((parent, "PARENT"), (child, "CHILD")):
        path.write_text(
            "".join(
                json.dumps({"pid": 1 if identity == "PARENT" else 2, "test": f"MAIN5_CONTROL_{identity}", "code": code}) + "\n"
                for code in ("MAIN5_REAL_ADAPTER", "MAIN5_WRITE")
            ),
            encoding="utf-8",
        )
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-Main5ControlLedger'},$true)
if(-not $function){throw 'CONTROL_LEDGER_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
if(-not (Test-Main5ControlLedger -Directory $env:MAIN5_CONTROL_FIXTURE)){throw 'CONTROL_LEDGER_REJECTED'}
Remove-Item -LiteralPath (Join-Path $env:MAIN5_CONTROL_FIXTURE 'child.jsonl')
if(Test-Main5ControlLedger -Directory $env:MAIN5_CONTROL_FIXTURE){throw 'MISSING_CONTROL_ACCEPTED'}
'CONTROL_LIVENESS_PASS'
"""
    result = _runner_function_probe(script, MAIN5_CONTROL_FIXTURE=str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CONTROL_LIVENESS_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell classification summary")
def test_runner_class_counts_match_classification_rows() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-Main5ClassCounts'},$true)
if(-not $function){throw 'CLASS_COUNTS_FUNCTION_MISSING'}
Invoke-Expression $function.Extent.Text
$rows=@([pscustomobject]@{classification='launcher_pair'},[ordered]@{classification='launcher_pair'},[pscustomobject]@{classification='killed_in_guard_setup'})
$counts=@(Get-Main5ClassCounts -Classifications $rows)
if($counts.Count -ne 2 -or @($counts | Where-Object { $_.classification -eq 'launcher_pair' -and $_.count -eq 2 }).Count -ne 1 -or @($counts | Where-Object { $_.classification -eq 'killed_in_guard_setup' -and $_.count -eq 1 }).Count -ne 1){throw 'CLASS_COUNTS_WRONG'}
'CLASS_COUNTS_PASS'
"""
    result = _runner_function_probe(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CLASS_COUNTS_PASS"

@pytest.mark.skipif(sys.platform != "win32", reason="Windows activation and config ownership")
def test_attempt_activation_is_unshadowable_idempotent_and_config_owned(tmp_path: Path) -> None:
    attempt = _runner(tmp_path, "Control")
    site = attempt / "venv" / "Lib" / "site-packages"
    activation_file = site / "00-main5-guard.pth"
    helper = site / "main5_activate.py"
    helper_source = helper.read_text(encoding="utf-8")
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    marker = tmp_path / "shadow-ran.txt"
    (shadow / "sitecustomize.py").write_text(
        "import os\nfrom pathlib import Path\nPath(os.environ['MAIN5_ACTIVATION_MARKER']).write_text('loaded')\n",
        encoding="utf-8",
    )
    diverted_port = tmp_path / "diverted-port.jsonl"
    diverted_keyring = tmp_path / "diverted-keyring.jsonl"
    env = {
        **os.environ,
        "PYTHONPATH": str(shadow),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_KEYRING_BACKEND": "counting_keyring.CountingKeyring",
        "MAIN5_ACTIVATION_MARKER": str(marker),
        "MAIN5_GUARD_LOG_DIR": str(attempt / "control-logs"),
        "MAIN5_CONTROL_PROTECTED_ROOT": str(tmp_path / "wrong-protected-root"),
        "MAIN5_PORT_GUARD": str(tmp_path / "missing-port-guard.py"),
        "X1_GUARD_LOG": str(diverted_port),
        "KEYRING_AUDIT_LOG": str(diverted_keyring),
    }
    config_path = site / "main5-config.json"
    marker_target = (attempt / "control-protected" / "blocked-by-override-test").as_posix()
    probe = (
        "import json,os,sys,keyring\n"
        "from pathlib import Path\n"
        f"line=Path({str(activation_file)!r}).read_text(encoding='utf-8')\n"
        "exec(line, {})\nexec(line, {})\n"
        "keyring.get_password('main5-activation','probe')\n"
        f"config=json.loads(Path({str(config_path)!r}).read_text(encoding='utf-8'))\n"
        f"target=Path({marker_target!r})\n"
        "try: target.write_text('blocked',encoding='utf-8')\n"
        "except PermissionError as exc: assert str(exc)=='MAIN5_WRITE'\n"
        "else: raise AssertionError('attempt config protection was diverted')\n"
        "print(os.getpid())\n"
    )
    child = subprocess.run(
        [str(site.parent.parent / "Scripts" / "python.exe"), "-c", probe],
        env=env, capture_output=True, text=True, check=False,
    )
    assert child.returncode == 0, child.stderr
    assert marker.read_text(encoding="utf-8") == "loaded"
    pid = int(child.stdout.strip())
    spawn_files = list((attempt / "logs").glob(f"{pid}-*.spawn"))
    assert len(spawn_files) == 1
    events = [json.loads(line) for line in spawn_files[0].read_text(encoding="utf-8").splitlines()]
    assert [event["kind"] for event in events].count("guard_begin") == 1
    starts = [event for event in events if event["kind"] == "guard_start"]
    assert len(starts) == 1 and starts[0]["env_override_ignored"] is True
    port_rows = [json.loads(line) for line in (attempt / "port-guard.jsonl").read_text(encoding="utf-8").splitlines()]
    keyring_rows = [json.loads(line) for line in (attempt / "keyring-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row["pid"] == pid and row["event"] == "process-start" for row in port_rows)
    assert any(row["pid"] == pid for row in keyring_rows)
    assert not diverted_port.exists() and not diverted_keyring.exists()
    with (attempt / "logs" / f"{pid}-{spawn_files[0].stem.split('-', 1)[1]}.jsonl").open(encoding="utf-8") as stream:
        assert any(json.loads(line).get("code") == "MAIN5_WRITE" for line in stream)

    helper.write_text("raise RuntimeError('PLANTED_ACTIVATION')\n", encoding="utf-8")
    failed_marker = tmp_path / "activation-user-code-ran.txt"
    failed_env = {**env, "MAIN5_ACTIVATION_MARKER": str(failed_marker)}
    failed = subprocess.run(
        [str(site.parent.parent / "Scripts" / "python.exe"), "-c", "from pathlib import Path; Path(r'" + str(failed_marker) + "').write_text('ran')"],
        env=failed_env, capture_output=True, text=True, check=False,
    )
    helper.write_text(helper_source, encoding="utf-8")
    assert failed.returncode in {86, 87}
    assert not failed_marker.exists()
    refusal_rows = [
        json.loads(line)
        for path in (attempt / "logs").glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(row.get("kind") == "guard_refusal" and row.get("code") == "activation_failure" for row in refusal_rows)
    assert "PLANTED_ACTIVATION" not in "".join(path.read_text(encoding="utf-8") for path in (attempt / "logs").glob("*.jsonl"))


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell guarded untraced classification")
def test_runner_accepts_only_scored_guarded_untraced_identities() -> None:
    script = r"""
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
foreach($name in @('Get-Main5GuardedUntracedClassification','Test-Main5ScoredLedgerAttribution')) {
    $function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
    if(-not $function){throw 'GUARDED_UNTRACED_CLASSIFIER_MISSING'}
    Invoke-Expression $function.Extent.Text
}
$base='C:\Python\python.exe'
$root=[pscustomobject]@{kind='guard_start';pid=10;creation_time=100;runner_direct_role='suite'}
$begin=[pscustomobject]@{kind='guard_begin';pid=30;creation_time=300;parent_pid=20;parent_creation_time=200;image=$base;flags=[pscustomobject]@{no_site=$false}}
$start=[pscustomobject]@{kind='guard_start';pid=30;creation_time=300;parent_pid=20;parent_creation_time=200;image=$base;flags=[pscustomobject]@{no_site=$false}}
$rows=@($root,$begin,$start)
$classes=@()
if(-not(Test-Main5ScoredLedgerAttribution -SpawnRows $rows -GuardRows @() -BasePython $base -ScoredStart 250 -ScoredEnd 350 -GuardedUntraced ([ref]$classes))){throw 'IN_WINDOW_REJECTED'}
if($classes.Count -ne 1 -or $classes[0].classification -cne 'guarded_untraced' -or $classes[0].pid -ne 30){throw 'IN_WINDOW_NOT_CLASSIFIED'}
foreach($window in @(@(301,350),@(250,299))) {
    if(Test-Main5ScoredLedgerAttribution -SpawnRows $rows -GuardRows @() -BasePython $base -ScoredStart $window[0] -ScoredEnd $window[1]){throw 'OUTSIDE_WINDOW_ACCEPTED'}
}
$refusal=[pscustomobject]@{kind='guard_refusal';pid=30;creation_time=300;code='MAIN5_REFUSAL'}
if(Test-Main5ScoredLedgerAttribution -SpawnRows $rows -GuardRows @($refusal) -BasePython $base -ScoredStart 250 -ScoredEnd 350){throw 'REFUSAL_ACCEPTED'}
if(Test-Main5ScoredLedgerAttribution -SpawnRows @($root,$start) -GuardRows @() -BasePython $base -ScoredStart 250 -ScoredEnd 350){throw 'MISSING_BEGIN_ACCEPTED'}
if(Test-Main5ScoredLedgerAttribution -SpawnRows @($root,$begin) -GuardRows @() -BasePython $base -ScoredStart 250 -ScoredEnd 350){throw 'MISSING_START_ACCEPTED'}
if(Test-Main5ScoredLedgerAttribution -SpawnRows $rows -GuardRows @() -BasePython 'C:\Other\python.exe' -ScoredStart 250 -ScoredEnd 350){throw 'WRONG_RUNTIME_ACCEPTED'}
$start.flags.no_site=$true
if(Test-Main5ScoredLedgerAttribution -SpawnRows $rows -GuardRows @() -BasePython $base -ScoredStart 250 -ScoredEnd 350){throw 'NO_SITE_ACCEPTED'}
$start.flags.no_site=$false
$traced=@($rows)+@([pscustomobject]@{kind='create_process';parent_pid=10;parent_creation_time=100;child_pid=20;creation_time=200})
$classes=@()
if(-not(Test-Main5ScoredLedgerAttribution -SpawnRows $traced -GuardRows @() -BasePython $base -ScoredStart 250 -ScoredEnd 350 -GuardedUntraced ([ref]$classes))){throw 'TRACED_LEDGER_CHANGED'}
if($classes.Count -ne 0){throw 'TRACED_IDENTITY_RECLASSIFIED'}
'GUARDED_UNTRACED_RED_GREEN_PASS'
"""
    result = _runner_function_probe(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "GUARDED_UNTRACED_RED_GREEN_PASS"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell runner working directory")
def test_runner_collection_ignores_foreign_caller_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    foreign = tmp_path / "foreign"
    repo.mkdir()
    foreign.mkdir()
    (repo / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (repo / "test_owned.py").write_text("def test_owned(): pass\n", encoding="utf-8")
    (foreign / "test_foreign.py").write_text("def test_foreign(): pass\n", encoding="utf-8")
    script = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$source=Get-Content -LiteralPath $env:MAIN5_RUNNER_SOURCE -Raw
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Main5FullCollection'},$true)
Invoke-Expression $function.Extent.Text
$begin=$source.IndexOf('$repo = (Resolve-Path')
$end=$source.IndexOf('$kitValue =', $begin)
$prefix=$source.Substring($begin,$end-$begin)
$firstLine=$prefix.IndexOf("`n")
$prefix='$repo = $env:MAIN5_FIXTURE_REPO' + "`n" + $prefix.Substring($firstLine+1)
$attempt=Join-Path $env:MAIN5_FIXTURE_REPO 'attempt'
New-Item -ItemType Directory -Path $attempt | Out-Null
Push-Location -LiteralPath $env:MAIN5_FOREIGN_DIRECTORY
try {
  $caller=(Get-Location).Path
  $probe=$prefix + @'
Invoke-Main5FullCollection -Python $env:MAIN5_TEST_PYTHON -Attempt $attempt -Arguments @('-m','pytest','-p','no:cacheprovider','--rootdir='+$repo,'--collect-only','-q') | Out-Null
'@
  if($prefix -match 'try\s*\{'){$probe += "`n} finally { Pop-Location }"}
  Invoke-Expression $probe
  if((Get-Location).Path -cne $caller){throw 'CALLER_DIRECTORY_NOT_RESTORED'}
} finally { Pop-Location }
$collected=Get-Content -LiteralPath (Join-Path $attempt 'full-collection.txt') -Raw
if($collected -notmatch 'test_owned.py::test_owned' -or $collected -match 'test_foreign'){throw 'FOREIGN_COLLECTION_NOT_EXCLUDED'}
if($source -notmatch '(?s)finally\s*\{\s*Pop-Location\s*\}\s*$'){throw 'OUTERMOST_LOCATION_RESTORE_MISSING'}
foreach($name in @('collectArgs','scoredArgs','selfArgs')){
  $assignment=($source -split "`n" | Where-Object { $_ -match ('^\s*\$'+$name+' = @') }) -join "`n"
  if($assignment -notmatch '--rootdir='){throw ('PYTEST_ROOT_NOT_PINNED:'+ $name)}
}
'FOREIGN_COLLECTION_EXCLUDED'
"""
    result = _runner_function_probe(
        script, MAIN5_FIXTURE_REPO=str(repo), MAIN5_FOREIGN_DIRECTORY=str(foreign),
        MAIN5_TEST_PYTHON=sys.executable,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stdout.strip().endswith("FOREIGN_COLLECTION_EXCLUDED")


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell collection classification")
@pytest.mark.parametrize("kind", ["syntax", "interrupt"])
def test_runner_distinguishes_collection_error_from_interrupt(tmp_path: Path, kind: str) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    if kind == "syntax":
        (tmp_path / "test_broken.py").write_text("def broken(:\n", encoding="utf-8")
    else:
        (tmp_path / "test_one.py").write_text("def test_one(): pass\n", encoding="utf-8")
        (tmp_path / "conftest.py").write_text(
            "def pytest_collection(session):\n    raise KeyboardInterrupt()\n", encoding="utf-8",
        )
    script = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Main5FullCollection'},$true)
Invoke-Expression $function.Extent.Text
$attempt=Join-Path $env:MAIN5_COLLECTION_FIXTURE 'attempt'
New-Item -ItemType Directory -Path $attempt | Out-Null
Push-Location -LiteralPath $env:MAIN5_COLLECTION_FIXTURE
try {
  try { Invoke-Main5FullCollection -Python $env:MAIN5_TEST_PYTHON -Attempt $attempt -Arguments @('-m','pytest','-p','no:cacheprovider','--collect-only','-q',('--rootdir='+$env:MAIN5_COLLECTION_FIXTURE)) | Out-Null; throw 'BAD_COLLECTION_ACCEPTED' }
  catch { if($_.Exception.Message -cne 'MAIN5_FULL_COLLECTION_FAILED:2'){throw} }
} finally { Pop-Location }
$record=Get-Content -LiteralPath (Join-Path $attempt 'collection.json') -Raw | ConvertFrom-Json
$state=Get-Content -LiteralPath (Join-Path $attempt 'attempt-status.json') -Raw | ConvertFrom-Json
if($record.exit_code -ne 2 -or $record.status -cne $env:MAIN5_EXPECTED_CLASS){throw 'COLLECTION_CLASS_WRONG'}
if($state.status -cne $env:MAIN5_EXPECTED_STATE){throw 'ATTEMPT_STATE_WRONG'}
if($record.status -ceq 'COLLECTION_ERROR' -and (Get-Content -LiteralPath $record.stdout_file -Raw) -notmatch 'ERROR collecting'){throw 'ERROR_TEXT_NOT_RETAINED'}
'COLLECTION_CLASS_PASS'
"""
    result = _runner_function_probe(
        script, MAIN5_COLLECTION_FIXTURE=str(tmp_path), MAIN5_TEST_PYTHON=sys.executable,
        MAIN5_EXPECTED_CLASS="COLLECTION_ERROR" if kind == "syntax" else "INTERRUPTED",
        MAIN5_EXPECTED_STATE="FAILED" if kind == "syntax" else "INTERRUPTED",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stdout.strip() == "COLLECTION_CLASS_PASS"



@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell absent basetemp")
def test_runner_archives_absent_basetemp_but_requires_work_root(tmp_path: Path) -> None:
    script = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
foreach($name in @('Get-Main5Sha256','Save-Main5BasetempArchive')){
  $function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
  Invoke-Expression $function.Extent.Text
}
$attempt=$env:MAIN5_ARCHIVE_TEST_ROOT
$base=Join-Path $attempt 'unused'
$result=Save-Main5BasetempArchive -Basetemp $base -Attempt $attempt -Lane 'empty'
if($result.basetemp_created -or (Test-Path -LiteralPath $base)){throw 'ABSENT_BASETEMP_MISRECORDED'}
if((Get-Main5Sha256 $result.path) -cne $result.sha256){throw 'EMPTY_ARCHIVE_HASH_WRONG'}
$zip=[IO.Compression.ZipFile]::OpenRead($result.path)
try{if($zip.Entries.Count -ne 0){throw 'EMPTY_ARCHIVE_NOT_EMPTY'}}finally{$zip.Dispose()}
try{Save-Main5BasetempArchive -Basetemp $base -Attempt $attempt -Lane 'empty';throw 'EXISTING_ARCHIVE_ACCEPTED'}
catch{if($_.Exception.Message -cne 'MAIN5_BASETEMP_ARCHIVE_EXISTS'){throw}}
try{Save-Main5BasetempArchive -Basetemp (Join-Path $attempt 'missing-root/s') -Attempt $attempt -Lane 'missing';throw 'MISSING_WORK_ROOT_ACCEPTED'}
catch{if($_.Exception.Message -cne 'MAIN5_SHORT_WORK_ROOT_MISSING'){throw}}
'ABSENT_BASETEMP_RED_GREEN_PASS'
"""
    result = _runner_function_probe(script, MAIN5_ARCHIVE_TEST_ROOT=str(tmp_path))
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stdout.strip() == "ABSENT_BASETEMP_RED_GREEN_PASS"



@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell non-venv classification")
@pytest.mark.parametrize("exit_code", [0, 1, None])
def test_runner_labels_non_venv_non_probe_for_any_exit(exit_code: int | None) -> None:
    script = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'RUNNER_PARSE_FAILED'}
$branch=$ast.Find({param($node) $node -is [System.Management.Automation.Language.IfStatementAst] -and $node.Extent.Text -match '^if\s*\(\$isAttemptImage\)'},$true)
if(-not $branch -or -not $branch.ElseClause){throw 'NON_VENV_BRANCH_MISSING'}
$body=$branch.ElseClause.Extent.Text
$body=$body.Substring(1,$body.Length-2)
$startByIdentity=@{}; $beginByIdentity=@{}; $refusalByIdentity=@{}; $refusalPids=@{}
$childKey='7:70'
$create=[pscustomobject]@{child_pid=7;shape='code';flags=[pscustomobject]@{no_site=$false}}
$observedExit=if($env:MAIN5_SYNTHETIC_EXIT -ceq 'null'){$null}else{[int]$env:MAIN5_SYNTHETIC_EXIT}
Invoke-Expression $body
if($classification -cne 'outside_attempt_venv'){throw ('WRONG_NON_VENV_LABEL:'+ $classification)}
# Preserve the existing precedence and limit no-code acceptance to exit-zero probes.
$create.flags.no_site=$true; $observedExit=87
Invoke-Expression $body
if($classification -cne 'no_site'){throw 'NO_SITE_PRECEDENCE_LOST'}
$create.flags.no_site=$false
Invoke-Expression $body
if($classification -cne 'guard_refusal'){throw 'EXIT87_REFUSAL_LOST'}
$observedExit=0; $refusalPids['7']=$true
Invoke-Expression $body
if($classification -cne 'guard_refusal'){throw 'RECORDED_REFUSAL_LOST'}
$refusalPids.Clear(); $startByIdentity[$childKey]=$true; $beginByIdentity[$childKey]=$true
Invoke-Expression $body
if($classification -cne 'guarded'){throw 'GUARDED_CLASSIFICATION_LOST'}
$startByIdentity.Clear(); $beginByIdentity.Clear()
foreach($shape in @('version_probe','help_probe')){
  $create.shape=$shape; $observedExit=0
  Invoke-Expression $body
  if($classification -cne 'no_code_probe'){throw 'EXIT_ZERO_PROBE_REJECTED'}
  $observedExit=1
  Invoke-Expression $body
  if($classification -cne 'outside_attempt_venv'){throw 'FAILED_PROBE_ACCEPTED'}
}
'NON_VENV_EXIT_CLASSIFICATION_PASS'
"""
    result = _runner_function_probe(script, MAIN5_SYNTHETIC_EXIT="null" if exit_code is None else str(exit_code))
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stdout.strip() == "NON_VENV_EXIT_CLASSIFICATION_PASS"


def _write_scoped_plugin(tmp_path: Path) -> tuple[Path, Path]:
    site = tmp_path / "site"
    attempt = tmp_path / "attempt"
    site.mkdir()
    attempt.mkdir()
    script = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Initialize-Main5ScoredPlugin'},$true)
if(-not $function){throw 'SCOPED_PLUGIN_WRITER_MISSING'}
Invoke-Expression $function.Extent.Text
Initialize-Main5ScoredPlugin -Site $env:MAIN5_PLUGIN_SITE -Venv $env:MAIN5_PLUGIN_VENV -Attempt $env:MAIN5_PLUGIN_ATTEMPT
"""
    result = _runner_function_probe(
        script, MAIN5_PLUGIN_SITE=str(site), MAIN5_PLUGIN_VENV=sys.prefix,
        MAIN5_PLUGIN_ATTEMPT=str(attempt),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return site, attempt


def _scoped_session(root: Path, site: Path, *, preset: bool = False) -> subprocess.CompletedProcess[str]:
    config = root / "pytest.ini"
    config.write_text("[pytest]\n")
    env = {**os.environ, "PYTHONPATH": str(site), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    env.pop("OPTIMUS_TEST_VENV", None)
    if preset:
        env["OPTIMUS_TEST_VENV"] = "pre-set-fixture"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "main5_scored_scope", "-c", str(config),
         f"--rootdir={root}", "-q", "-p", "no:cacheprovider"],
        cwd=root, env=env, capture_output=True, text=True, timeout=60,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Runner-written scored pytest plugin")
@pytest.mark.parametrize("failing", [False, True])
def test_scoped_plugin_wraps_consumer_protocol_and_module_fixtures(tmp_path: Path, failing: bool) -> None:
    site, _ = _write_scoped_plugin(tmp_path)
    project = tmp_path / "project"
    for name in ("test_ci_parity.py", "test_local_secret_scan_encoding.py", "test_ci_parity_longer.py"):
        path = project / "tests/unit/guardrails" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        consumer = name != "test_ci_parity_longer.py"
        predicate = "os.environ.get('OPTIMUS_TEST_VENV') == sys.prefix" if consumer else "'OPTIMUS_TEST_VENV' not in os.environ"
        should_fail = failing and name == "test_ci_parity.py"
        path.write_text(
            "import os,sys,pytest\n"
            "@pytest.fixture(scope='module',autouse=True)\n"
            f"def scoped_fixture():\n    assert {predicate}\n    yield\n    assert {predicate}\n"
            f"def test_first():\n    assert {predicate}\n    assert {not should_fail!r}\n"
            f"def test_second():\n    assert {predicate}\n",
        )
    # Explicit order places a non-consumer after the failing consumer module.
    result = _scoped_session(project, site)
    assert result.returncode == (1 if failing else 0), result.stdout + result.stderr
    assert ("1 failed, 5 passed" if failing else "6 passed") in result.stdout
    assert "ERROR" not in result.stdout + result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Runner-written scored pytest plugin")
def test_scoped_plugin_rejects_preexisting_override(tmp_path: Path) -> None:
    site, _ = _write_scoped_plugin(tmp_path)
    root = tmp_path / "project"
    root.mkdir()
    (root / "test_other.py").write_text("def test_other():\n    pass\n")
    result = _scoped_session(root, site, preset=True)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "MAIN5_SCOPED_OVERRIDE_LEAK" in result.stdout + result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Runner-written scored pytest plugin")
@pytest.mark.parametrize("fault", ["missing", "invalid_json", "relative_venv", "bad_consumers", "extra_field"])
def test_scoped_plugin_refuses_invalid_configuration_at_load(tmp_path: Path, fault: str) -> None:
    site, _ = _write_scoped_plugin(tmp_path)
    path = site / "main5-scored-scope.json"
    config = json.loads(path.read_text())
    if fault == "missing":
        path.unlink()
    elif fault == "invalid_json":
        path.write_text("{")
    else:
        if fault == "relative_venv":
            config["venv"] = "relative-venv"
        elif fault == "bad_consumers":
            config["consumer_paths"] = ["tests/unit/acp/test_main_wiring.py"]
        else:
            config["extra_field"] = "unapproved"
        path.write_text(json.dumps(config))
    root = tmp_path / "project"
    root.mkdir()
    (root / "test_other.py").write_text("def test_other():\n    pass\n")
    result = _scoped_session(root, site)
    assert result.returncode != 0
    assert "MAIN5_SCOPED_CONFIG_INVALID" in result.stdout + result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Runner-written shutdown failure diagnostic")
@pytest.mark.parametrize("case", ["failed_exact", "passed_exact", "failed_other"])
def test_scoped_plugin_records_only_shutdown_probe_tokens(tmp_path: Path, case: str) -> None:
    site, attempt = _write_scoped_plugin(tmp_path)
    root = tmp_path / "project"
    path = root / "tests/unit/acp/test_plan1126_shutdown.py"
    path.parent.mkdir(parents=True)
    name = "test_shutdown_causes_repeat_100_with_control_allowlist"
    if case == "failed_other":
        name += "_longer"
    observations = [
        {"cause_effect": "cancel:probe_error:TimeoutError", "private": "DO_NOT_RECORD"},
        {"cause_effect": "cancel:probe_error:TimeoutError"},
        {"cause_effect": "shutdown:probe_error:RuntimeError"},
        {"cause_effect": "cancel:probe_error:DO_NOT_RECORD-123"},
        {"cause_effect": "cancel:probe_error:TimeoutError\nDO_NOT_RECORD"},
        {"cause_effect": "cancel:prepared"},
        {"cause_effect": {"private": "DO_NOT_RECORD"}},
    ]
    path.write_text(f"def {name}():\n    observations = {observations!r}\n    assert {case == 'passed_exact'!r}\n")
    result = _scoped_session(root, site)
    assert result.returncode == (0 if case == "passed_exact" else 1), result.stdout + result.stderr
    diagnostic = attempt / "shutdown-probe-errors.json"
    if case == "failed_exact":
        assert json.loads(diagnostic.read_text()) == {
            "cancel:probe_error:TimeoutError": 2, "shutdown:probe_error:RuntimeError": 1,
        }
        assert "DO_NOT_RECORD" not in diagnostic.read_text()
    else:
        assert not diagnostic.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process creation identity")
@pytest.mark.parametrize("case", ["older_child", "normal", "equal_time", "missing_time", "older_ancestor"])
def test_census_rejects_parent_pid_reuse_by_creation_time(case: str) -> None:
    script = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$tokens,[ref]$errors)
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Descends'},$true)
if(-not $function){throw 'CENSUS_MEMBERSHIP_MISSING'}
Invoke-Expression $function.Extent.Text
$parents=@{100=0;200=100;300=200}
$created=@{100=100;200=200;300=300}
switch($env:MAIN5_CENSUS_CASE){
  'older_child' {$created[300]=50}
  'equal_time' {$created[300]=200}
  'missing_time' {$created[200]=$null}
  'older_ancestor' {$created[200]=50}
}
$actual=Descends 300 100 $parents $created
if($actual -ne ($env:MAIN5_EXPECT_MEMBER -ceq 'true')){throw 'PID_REUSED_PARENT_LINK_ACCEPTED_OR_NORMAL_CHILD_LOST'}
'CENSUS_IDENTITY_PASS'
"""
    result = _runner_function_probe(
        script, MAIN5_CENSUS_CASE=case, MAIN5_EXPECT_MEMBER="true" if case in {"normal", "equal_time"} else "false",
    )
    assert result.returncode == 0, result.stderr + result.stdout



def test_runner_has_no_present_empty_environment_clear_idioms() -> None:
    """Required static backstop; the scored child tests the actual absence contract."""
    source = (_REPO / "tools/testing/run_main5_guarded_suite.ps1").read_text()
    assert not re.search(r"SetEnvironmentVariable\([^)]*,\s*\$null", source)
    assert not re.search(r"\$env:[A-Za-z_]\w*\s*=\s*(['\"])\1", source)



@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell native argument contract")
@pytest.mark.parametrize("powershell", ["powershell.exe", "pwsh.exe"])
def test_runner_null_target_never_reaches_native_argv(tmp_path: Path, powershell: str) -> None:
    script = r"""
$ErrorActionPreference='Stop'
$t=$null; $e=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$t,[ref]$e)
$targets=if($false){@('tests/example.py')}else{@()}
$normalizer=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Get-Main5NormalizedTargets'},$true)
if($normalizer){
  Invoke-Expression $normalizer.Extent.Text
  $scoredTargets=@(Get-Main5NormalizedTargets -Targets $targets)
}else{
  $assignment=$ast.Find({param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -ceq '$scoredTargets'},$true)
  $scoredTargets=& {param([string[]]$PytestTarget=@()) Invoke-Expression $assignment.Extent.Text; return ,$scoredTargets} -PytestTarget $targets
}
$lane=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Invoke-Main5ScoredLane'},$true)
Invoke-Expression $lane.Extent.Text
$argsToPass=@('-c','import json,sys; print(json.dumps(sys.argv[1:]))','FIXED')
if($scoredTargets.Count){$argsToPass += $scoredTargets}
$code=Invoke-Main5ScoredLane -Python $env:MAIN5_TEST_PYTHON -Venv 'fixture' -Arguments $argsToPass -Output $env:MAIN5_ARG_OUTPUT
if($code -ne 0){throw 'ARGV_PROBE_FAILED'}
Get-Content -LiteralPath $env:MAIN5_ARG_OUTPUT
"""
    result = _runner_function_probe(script, powershell=powershell, MAIN5_TEST_PYTHON=sys.executable, MAIN5_ARG_OUTPUT=str(tmp_path / "argv.json"))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip()) == ["FIXED"]


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell target validation")
@pytest.mark.parametrize("powershell", ["powershell.exe", "pwsh.exe"])
@pytest.mark.parametrize("target", ["", "   "])
def test_runner_rejects_blank_target_at_entry(tmp_path: Path, powershell: str, target: str) -> None:
    script = r"""
$ErrorActionPreference='Stop'
$badTarget=if($env:MAIN5_BAD_TARGET -ceq 'spaces'){'   '}else{''}
try{
 & $env:MAIN5_RUNNER_SOURCE -Mode Discover -AttemptDirectory $env:MAIN5_UNUSED_ATTEMPT -PytestTarget @($badTarget)
 throw 'EMPTY_TARGET_ACCEPTED'
}catch{
 if($_.Exception.Message -cne 'MAIN5_INVALID_TEST_TARGET'){throw}
 'INVALID_TARGET_PASS'
}
"""
    result = _runner_function_probe(
        script, powershell=powershell, MAIN5_BAD_TARGET="spaces" if target else "empty",
        MAIN5_UNUSED_ATTEMPT=str(tmp_path / "never-created"), MAIN5_KIT_DIR="",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "INVALID_TARGET_PASS" in result.stdout
    assert not (tmp_path / "never-created").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell lane argument validation")
@pytest.mark.parametrize("powershell", ["powershell.exe", "pwsh.exe"])
@pytest.mark.parametrize("lane", ["Scored", "SelfTest"])
def test_runner_rejects_blank_lane_arguments_before_python(tmp_path: Path, powershell: str, lane: str) -> None:
    script = r"""
$ErrorActionPreference='Stop'
$t=$null; $e=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$t,[ref]$e)
$name='Invoke-Main5'+$env:MAIN5_LANE+'Lane'
$f=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $name},$true)
if($f){Invoke-Expression $f.Extent.Text}else{function Invoke-Main5SelfTestLane([string]$Python,[string[]]$Arguments,[string]$Output){& $Python @Arguments *> $Output; return $LASTEXITCODE}}
foreach($bad in @('', '  ')){
 $arguments=@('-c','from pathlib import Path; import os; Path(os.environ["MAIN5_NEVER_LAUNCHED"]).touch()', $bad)
 try{
   if($env:MAIN5_LANE -ceq 'Scored'){Invoke-Main5ScoredLane -Python $env:MAIN5_TEST_PYTHON -Venv 'fixture' -Arguments $arguments -Output $env:MAIN5_NATIVE_OUT | Out-Null}
   else{Invoke-Main5SelfTestLane -Python $env:MAIN5_TEST_PYTHON -Arguments $arguments -Output $env:MAIN5_NATIVE_OUT | Out-Null}
   throw 'EMPTY_ARGUMENT_ACCEPTED'
 }catch{if($_.Exception.Message -cne 'MAIN5_EMPTY_PYTEST_ARGUMENT'){throw}}
}
'EMPTY_ARGUMENT_PASS'
"""
    launched = tmp_path / "launched"
    result = _runner_function_probe(
        script, powershell=powershell, MAIN5_LANE=lane, MAIN5_TEST_PYTHON=sys.executable,
        MAIN5_NEVER_LAUNCHED=str(launched), MAIN5_NATIVE_OUT=str(tmp_path / "stdout.txt"),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert not launched.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell ordinal executed-ID contract")
@pytest.mark.parametrize("powershell", ["powershell.exe", "pwsh.exe"])
@pytest.mark.parametrize("case", ["match", "extra", "case_extra", "missing", "no_identity"])
def test_runner_checks_executed_lane_against_partition(powershell: str, case: str) -> None:
    script = r"""
$ErrorActionPreference='Stop'
$t=$null; $e=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:MAIN5_RUNNER_SOURCE,[ref]$t,[ref]$e)
$f=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Get-Main5ExecutedLaneVerdict'},$true)
if(-not $f){throw 'EXECUTED_LANE_CHECK_MISSING'}
Invoke-Expression $f.Extent.Text
$rows=@([pscustomobject]@{event='audit-start';pid=100},[pscustomobject]@{event='test-start';pid=100;nodeid='tests/example.py::test_a[y]'})
# Other pytest PIDs are deliberately outside this lane's executed-ID comparison.
$rows += [pscustomobject]@{event='test-start';pid=200;nodeid='tools/foreign.py::test_child'}
switch($env:MAIN5_LEDGER_CASE){
 'extra' {$rows += [pscustomobject]@{event='test-start';pid=100;nodeid='tools/foreign.py::test_extra'}}
 'case_extra' {$rows += [pscustomobject]@{event='test-start';pid=100;nodeid='tests/example.py::test_a[Y]'}}
 'missing' {$rows=@([pscustomobject]@{event='audit-start';pid=100})}
 'no_identity' {$rows=@()}
}
$actual=Get-Main5ExecutedLaneVerdict -Rows $rows -ExpectedNodeIds @('tests/example.py::test_a[y]')
$expected=if($env:MAIN5_LEDGER_CASE -ceq 'match'){'PASS'}else{'FAIL'}
if($actual.status -cne $expected){throw 'EXECUTED_PARTITION_VERDICT_WRONG'}
if($env:MAIN5_LEDGER_CASE -cin @('extra','case_extra') -and $actual.failures -cnotcontains 'lane_executed_outside_partition'){throw 'EXTRA_NODE_REASON_MISSING'}
if($env:MAIN5_LEDGER_CASE -cne 'no_identity' -and $actual.pytest_pid -ne 100){throw 'LANE_PID_WRONG'}
'EXECUTED_PARTITION_PASS'
"""
    result = _runner_function_probe(script, powershell=powershell, MAIN5_LEDGER_CASE=case)
    assert result.returncode == 0, result.stderr + result.stdout
