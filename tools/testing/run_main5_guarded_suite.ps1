param(
    [Parameter(Mandatory=$true)][ValidateSet('Control','Discover','Suite','Coverage')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$AttemptDirectory,
    [string[]]$PytestTarget = @(),
    [string]$KitDirectory = '',
    [string]$DependencyPython = '',
    [string]$PreCommitHome = '',
    [switch]$RequireClean
)

$ErrorActionPreference = 'Stop'
function Invoke-Main5ScoredLane([string]$Python, [string]$Venv, [string[]]$Arguments, [string]$Output) {
    $names = @('PYTHONPYCACHEPREFIX','PYTHONDONTWRITEBYTECODE')
    $previous = @{}
    foreach ($name in $names) {
        $previous[$name] = @{exists=(Test-Path -LiteralPath ("Env:{0}" -f $name));value=[Environment]::GetEnvironmentVariable($name,'Process')}
    }
    try {
        [Environment]::SetEnvironmentVariable('PYTHONPYCACHEPREFIX',$null,'Process')
        $env:PYTHONDONTWRITEBYTECODE = '1'
        & $Python @Arguments *> $Output
        return [int]$LASTEXITCODE
    } finally {
        foreach ($name in $names) {
            $value = if ($previous[$name].exists) { $previous[$name].value } else { $null }
            [Environment]::SetEnvironmentVariable($name,$value,'Process')
        }
    }
}
function Initialize-Main5ScoredPlugin([string]$Site, [string]$Venv, [string]$Attempt) {
    $config = [ordered]@{
        venv = [IO.Path]::GetFullPath($Venv)
        consumer_paths = @('tests/unit/guardrails/test_ci_parity.py','tests/unit/guardrails/test_local_secret_scan_encoding.py')
        attempt_directory = [IO.Path]::GetFullPath($Attempt)
    }
    [IO.File]::WriteAllText((Join-Path $Site 'main5-scored-scope.json'),($config | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    $plugin = @'
import json
import os
import re
from collections import Counter
from pathlib import Path

import pytest

_NAME = "OPTIMUS_TEST_VENV"
_SUPPORTED = frozenset({
    "tests/unit/guardrails/test_ci_parity.py",
    "tests/unit/guardrails/test_local_secret_scan_encoding.py",
})
try:
    _CONFIG = json.loads(Path(__file__).with_name("main5-scored-scope.json").read_text(encoding="utf-8"))
    if not isinstance(_CONFIG, dict) or set(_CONFIG) != {"venv", "consumer_paths", "attempt_directory"}:
        raise ValueError("config fields")
    for _key in ("venv", "attempt_directory"):
        if not isinstance(_CONFIG[_key], str) or not os.path.isabs(_CONFIG[_key]):
            raise ValueError("absolute directory required")
    _paths = _CONFIG["consumer_paths"]
    if not isinstance(_paths, list) or len(_paths) != 2 or any(not isinstance(p, str) for p in _paths):
        raise ValueError("consumer paths")
    if frozenset(_paths) != _SUPPORTED:
        raise ValueError("unsupported consumer")
except Exception:
    raise RuntimeError("MAIN5_SCOPED_CONFIG_INVALID") from None

_CONSUMERS = frozenset(_CONFIG["consumer_paths"])
_VENV = _CONFIG["venv"]
_DIAGNOSTIC = Path(_CONFIG["attempt_directory"]) / "shutdown-probe-errors.json"
_SHUTDOWN = "tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist"
_TOKEN = re.compile(r"^[a-z_]+:probe_error:[A-Za-z_]+$")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    if _NAME in os.environ:
        raise RuntimeError("MAIN5_SCOPED_OVERRIDE_LEAK")
    if item.nodeid.split("::", 1)[0] not in _CONSUMERS:
        return (yield)
    os.environ[_NAME] = _VENV
    try:
        return (yield)
    finally:
        os.environ.pop(_NAME, None)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if item.nodeid == _SHUTDOWN and report.failed and call.when == "call" and call.excinfo is not None:
        observations = None
        for entry in reversed(call.excinfo.traceback):
            candidate = entry.frame.f_locals.get("observations")
            if isinstance(candidate, list):
                observations = candidate
                break
        if observations is not None:
            counts = Counter()
            for observation in observations:
                if not isinstance(observation, dict):
                    continue
                token = observation.get("cause_effect")
                if isinstance(token, str) and _TOKEN.fullmatch(token):
                    counts[token] += 1
            _DIAGNOSTIC.write_text(json.dumps(dict(sorted(counts.items()))) + "\n", encoding="utf-8")
    return report
'@
    [IO.File]::WriteAllText((Join-Path $Site 'main5_scored_scope.py'),$plugin,[Text.UTF8Encoding]::new($false))
}

function Get-Main5NonPythonClassification([string]$Image, [string]$Venv, [string]$SelfTestVenv) {
    if ([string]::IsNullOrWhiteSpace($Image)) { return 'unknown' }
    try {
        $fullImage = [IO.Path]::GetFullPath($Image)
        $scripts = [IO.Path]::GetDirectoryName($fullImage)
        if ([IO.Path]::GetFileName($scripts) -ieq 'Scripts') {
            $root = [IO.Path]::GetDirectoryName($scripts)
            $own = $false
            foreach ($directory in @($Venv,$SelfTestVenv)) {
                if ([string]::IsNullOrWhiteSpace($directory)) { continue }
                $ownRoot = [IO.Path]::GetFullPath($directory).TrimEnd([char[]]'\/')
                if ([string]::Equals($root,$ownRoot,[StringComparison]::OrdinalIgnoreCase)) { $own = $true }
            }
            if (-not $own -and
                (Test-Path -LiteralPath (Join-Path $root 'pyvenv.cfg') -PathType Leaf)) {
                return 'outside_attempt_venv'
            }
        }
    } catch { return 'unknown' }
    if ([IO.Path]::GetFileName($fullImage) -match '(?i)^(?:git|bash|uv|cmd|powershell|pwsh|docker|conhost|timeout)\.exe$') { return 'known' }
    return 'unknown'
}
function Get-Main5NonPythonDescendants([object[]]$Rows, [object[]]$Created, [string]$Venv, [string]$SelfTestVenv) {
    foreach ($row in @($Rows | Sort-Object pid,created_at,executable -Unique)) {
        if ($row.image -match '(?i)^python(?:w)?\.exe$') { continue }
        [ordered]@{pid=$row.pid;ppid=$row.ppid;image=$row.image;executable=$row.executable;created_at=$row.created_at;classification=(Get-Main5NonPythonClassification -Image $row.executable -Venv $Venv -SelfTestVenv $SelfTestVenv);source='census'}
    }
    foreach ($row in $Created) {
        $imageName = [IO.Path]::GetFileName([string]$row.image)
        if ($imageName -match '(?i)^python(?:w)?\.exe$') { continue }
        [ordered]@{pid=$row.child_pid;ppid=$row.parent_pid;image=$imageName;executable=$row.image;created_at=if ($null -ne $row.creation_time) { [DateTime]::FromFileTimeUtc([long]$row.creation_time).ToString('o') } else { $null };classification=(Get-Main5NonPythonClassification -Image $row.image -Venv $Venv -SelfTestVenv $SelfTestVenv);source='ledger'}
    }
}
function Get-Main5Sha256([string]$FilePath) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($FilePath)
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $sha.Dispose() }
}
function Invoke-Main5CombinedCoverage([string]$Python, [string]$Attempt) {
    $combined = Join-Path $Attempt 'combined-coverage.data'
    $scored = Join-Path $Attempt 'scored-coverage.data'
    $selfTest = Join-Path $Attempt 'self-test-coverage.data'
    $combineOutput = Join-Path $Attempt 'combined-coverage-combine.txt'
    $combineError = Join-Path $Attempt 'combined-coverage-combine-stderr.txt'
    $reportOutput = Join-Path $Attempt 'combined-coverage-report.txt'
    $reportError = Join-Path $Attempt 'combined-coverage-report-stderr.txt'
    $previousErrorAction = $ErrorActionPreference
    $previousDirectRole = $env:MAIN5_DIRECT_LAUNCH
    try {
        $ErrorActionPreference = 'Continue'
        $env:MAIN5_DIRECT_LAUNCH = 'coverage'
        & $Python -m coverage combine --keep "--data-file=$combined" $scored $selfTest 1> $combineOutput 2> $combineError
        $combineExit = $LASTEXITCODE
        $reportExit = $null
        [double]$total = 0
        $hasTotal = $false
        if ($combineExit -eq 0) {
            & $Python -m coverage report --fail-under=80 --format=total "--data-file=$combined" 1> $reportOutput 2> $reportError
            $reportExit = $LASTEXITCODE
            if (Test-Path -LiteralPath $reportOutput -PathType Leaf) {
                $rawTotal = (Get-Content -LiteralPath $reportOutput -Raw).Trim()
                $hasTotal = [double]::TryParse($rawTotal,[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$total)
            }
        }
        return [pscustomobject]@{combine_exit=$combineExit;report_exit=$reportExit;total=if ($hasTotal) { $total } else { $null }}
    } finally {
        $ErrorActionPreference = $previousErrorAction
        $env:MAIN5_DIRECT_LAUNCH = $previousDirectRole
    }
}
function Assert-Main5PinnedKit([string]$Directory) {
    try {
        $resolved = [IO.Path]::GetFullPath($Directory)
        $manifest = Join-Path $resolved 'MANIFEST-v3.txt'
        if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { throw 'missing manifest' }
        $expectedManifest = 'A8C4244DF233C42446C498AE4C2AA5C859304D33CB1B740FD3275FAED6D2B75B' # pragma: allowlist secret - kit v3 manifest identity pin
        $actualManifest = Get-Main5Sha256 $manifest
        if ($actualManifest -cne $expectedManifest) { throw 'wrong manifest' }
        $entries = @(Get-Content -LiteralPath $manifest -Encoding utf8)
        if ($entries.Count -ne 17) { throw 'wrong entry count' }
        $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in $entries) {
            if ($entry -cnotmatch '^([0-9a-fA-F]{64})  ([^\r\n]+)$') { throw 'bad entry' }
            $expected = $Matches[1].ToUpperInvariant()
            $relative = $Matches[2]
            $parts = $relative -split '[/\\]'
            if ([IO.Path]::IsPathRooted($relative) -or $parts -contains '..' -or $parts -contains '.' -or -not $seen.Add($relative)) {
                throw 'unsafe entry'
            }
            $path = [IO.Path]::GetFullPath((Join-Path $resolved $relative))
            if (-not $path.StartsWith($resolved + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'entry escaped kit' }
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'missing entry' }
            if ((Get-Main5Sha256 $path) -cne $expected) { throw 'changed entry' }
        }
        return [pscustomobject]@{directory=$resolved;manifest_sha256=$actualManifest;entry_count=$entries.Count}
    } catch { throw 'MAIN5_KIT_NOT_PINNED' }
}
function Invoke-Main5FullCollection([string]$Python, [string]$Attempt, [string[]]$Arguments) {
    $stdout = Join-Path $Attempt 'full-collection.txt'
    $stderr = Join-Path $Attempt 'full-collection-stderr.txt'
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $previousErrorAction = $ErrorActionPreference
    $previousDirectRole = $env:MAIN5_DIRECT_LAUNCH
    $exitCode = $null
    try {
        $ErrorActionPreference = 'Continue'
        $env:MAIN5_DIRECT_LAUNCH = 'collect'
        & $Python @Arguments 1> $stdout 2> $stderr
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $clock.Stop()
        $ErrorActionPreference = $previousErrorAction
        $env:MAIN5_DIRECT_LAUNCH = $previousDirectRole
        $collectionOutput = ''
        foreach ($file in @($stdout,$stderr)) {
            if (Test-Path -LiteralPath $file -PathType Leaf) { $collectionOutput += Get-Content -LiteralPath $file -Raw }
        }
        $status = if ($exitCode -eq 2 -and $collectionOutput -match 'errors during collection|ERROR collecting') {
            'COLLECTION_ERROR'
        } elseif ($null -eq $exitCode -or $exitCode -eq 2) { 'INTERRUPTED' } elseif ($exitCode -eq 0) { 'PASS' } else { 'FAILED' }
        [ordered]@{exit_code=$exitCode;duration_seconds=$clock.Elapsed.TotalSeconds;stderr_file=$stderr;stdout_file=$stdout;status=$status} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Attempt 'collection.json') -Encoding utf8
        if ($status -ne 'PASS') {
            @{status=if ($status -eq 'INTERRUPTED') { 'INTERRUPTED' } else { 'FAILED' };phase='collection';collection_exit_code=$exitCode;collection_status=$status} |
                ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Attempt 'attempt-status.json') -Encoding utf8
        }
    }
    if ($exitCode -ne 0) { throw ('MAIN5_FULL_COLLECTION_FAILED:{0}' -f $exitCode) }
    return $stdout
}
function Get-Main5IdentityKey([object]$ProcessId, [object]$CreationTime) {
    if ($null -eq $ProcessId -or $null -eq $CreationTime) { throw 'MAIN5_IDENTITY_INCOMPLETE' }
    return ('{0}:{1}' -f $ProcessId,$CreationTime)
}
function Get-Main5UnloggedVerdict([string]$Shape, [object]$ExitCode) {
    if ($null -eq $ExitCode) { return 'exit_unobserved' }
    if ($ExitCode -eq 87) { return 'guard_exit_87' }
    if ($Shape -in @('version_probe','help_probe') -and $ExitCode -eq 0) { return 'no_code_probe' }
    if ($ExitCode -eq 0) { return 'unlogged_python' }
    return 'nonzero_exit'
}
function Test-Main5LaneOverlap([string[]]$Scored, [string[]]$SelfTest) {
    foreach ($nodeId in $Scored) {
        if ($SelfTest -ccontains $nodeId) { return $true }
    }
    return $false
}
function Get-Main5LanePartition([string[]]$FullNodeIds, [string]$SelfTestFile) {
    $full = @($FullNodeIds)
    if ($full.Count -eq 0) { throw 'MAIN5_EMPTY_COLLECTION' }
    $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($nodeId in $full) {
        if (-not $seen.Add($nodeId)) { throw 'MAIN5_DUPLICATE_NODEID' }
    }
    $prefix = $SelfTestFile + '::'
    $selfTest = @($full | Where-Object { $_.StartsWith($prefix,[StringComparison]::Ordinal) } | Sort-Object -CaseSensitive)
    $scored = @($full | Where-Object { -not $_.StartsWith($prefix,[StringComparison]::Ordinal) } | Sort-Object -CaseSensitive)
    if ($selfTest.Count -eq 0) { throw 'MAIN5_SELF_TEST_FILE_MISSING' }
    if ($scored.Count + $selfTest.Count -ne $full.Count) { throw 'MAIN5_PARTITION_COUNT_MISMATCH' }
    if (Test-Main5LaneOverlap -Scored $scored -SelfTest $selfTest) { throw 'MAIN5_PARTITION_OVERLAP' }
    return [pscustomobject]@{
        full_count=$full.Count
        scored_nodeids=[string[]]$scored
        self_test_nodeids=[string[]]$selfTest
    }
}
function Get-Main5TargetNodeIds([string[]]$FullNodeIds, [string]$Target, [string]$SelfTestFile, [string[]]$SelfTestNodeIds) {
    if (-not $Target) { return @() }
    $namespacePrefix = $Target.TrimEnd('/') + '::'
    $parameterPrefix = $Target + '['
    $selected = @($FullNodeIds | Where-Object {
        $_ -ceq $Target -or
        $_.StartsWith($namespacePrefix,[StringComparison]::Ordinal) -or
        $_.StartsWith($parameterPrefix,[StringComparison]::Ordinal)
    })
    if ($selected.Count -eq 0) { throw 'MAIN5_TARGET_NOT_COLLECTED' }
    $selfTestPrefix = $SelfTestFile + '::'
    $selectsSelfTest = @($selected | Where-Object { $_.StartsWith($selfTestPrefix,[StringComparison]::Ordinal) }).Count -gt 0
    if ($selectsSelfTest -and ($Target -cne $SelfTestFile -or $selected.Count -ne $SelfTestNodeIds.Count)) {
        throw 'MAIN5_SELF_TEST_TARGET_MUST_BE_WHOLE_FILE'
    }
    return $selected
}
function Resolve-Main5TargetSet([string[]]$FullNodeIds, [string[]]$Targets, [string]$SelfTestFile, [string[]]$SelfTestNodeIds) {
    $seenTargets = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $seenNodeIds = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $selected = [System.Collections.Generic.List[string]]::new()
    foreach ($target in $Targets) {
        if (-not $target -or $target -cnotmatch '^tests[/\\][A-Za-z0-9_./\\:-]+$' -or $target.Contains('..')) {
            throw 'MAIN5_INVALID_TEST_TARGET'
        }
        if (-not $seenTargets.Add($target)) { throw 'MAIN5_DUPLICATE_TEST_TARGET' }
        foreach ($nodeId in @(Get-Main5TargetNodeIds -FullNodeIds $FullNodeIds -Target $target -SelfTestFile $SelfTestFile -SelfTestNodeIds $SelfTestNodeIds)) {
            if (-not $seenNodeIds.Add($nodeId)) { throw 'MAIN5_DUPLICATE_TEST_TARGET' }
            $selected.Add($nodeId)
        }
    }
    return $selected.ToArray()
}
function Assert-Main5WorkRoots([System.Collections.IDictionary]$Roots, [object]$LongPathsEnabled) {
    $lengths = [ordered]@{}
    foreach ($entry in $Roots.GetEnumerator()) {
        $length = [IO.Path]::GetFullPath([string]$entry.Value).Length
        $lengths[[string]$entry.Key] = $length
        if ($LongPathsEnabled -ne 1 -and $length -gt 60) { throw 'MAIN5_WORK_ROOT_TOO_DEEP' }
    }
    return $lengths
}
function Save-Main5BasetempArchive([string]$Basetemp, [string]$Attempt, [string]$Lane) {
    $workRoot = Split-Path -Path $Basetemp -Parent
    if (-not (Test-Path -LiteralPath $workRoot -PathType Container)) { throw 'MAIN5_SHORT_WORK_ROOT_MISSING' }
    $basetempCreated = Test-Path -LiteralPath $Basetemp -PathType Container
    if ((Test-Path -LiteralPath $Basetemp) -and -not $basetempCreated) { throw 'MAIN5_BASETEMP_NOT_DIRECTORY' }
    $zip = Join-Path $Attempt ('pytest-tmp-{0}.zip' -f $Lane)
    if (Test-Path -LiteralPath $zip) { throw 'MAIN5_BASETEMP_ARCHIVE_EXISTS' }
    Add-Type -AssemblyName System.IO.Compression -ErrorAction Stop
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
    if ($basetempCreated) {
        [IO.Compression.ZipFile]::CreateFromDirectory($Basetemp,$zip,[IO.Compression.CompressionLevel]::Optimal,$true)
    } else {
        $empty = [IO.Compression.ZipFile]::Open($zip,[IO.Compression.ZipArchiveMode]::Create)
        $empty.Dispose()
    }
    return [pscustomobject]@{path=$zip;sha256=(Get-Main5Sha256 $zip);basetemp_created=[bool]$basetempCreated}
}
function Get-Main5LauncherVerdict([object]$Create, [object[]]$Begins, [object[]]$Starts, [object]$ObservedExit, [bool]$HasRefusal) {
    $runtimes = @{}
    foreach ($row in @($Begins) + @($Starts)) {
        if ($null -eq $row -or $null -eq $row.parent_creation_time -or $null -eq $row.creation_time) { continue }
        if ($row.parent_pid -ne $Create.child_pid -or $row.parent_creation_time -ne $Create.creation_time) { continue }
        $key = '{0}:{1}' -f $row.pid,$row.creation_time
        if (-not $runtimes.ContainsKey($key)) {
            $runtimes[$key] = [pscustomobject]@{pid=$row.pid;creation_time=$row.creation_time;began=$false;started=$false}
        }
        if ($row.kind -eq 'guard_begin') { $runtimes[$key].began = $true }
        if ($row.kind -eq 'guard_start') { $runtimes[$key].started = $true }
    }
    $runtime = if ($runtimes.Count -eq 1) { @($runtimes.Values)[0] } else { $null }
    $classification = 'activation_bypassed'
    if ($Create.flags.no_site) { $classification = 'no_site' }
    elseif ($HasRefusal -or $ObservedExit -eq 87) { $classification = 'guard_refusal' }
    elseif ($runtimes.Count -gt 1) { $classification = 'ambiguous_runtime' }
    elseif ($null -ne $runtime) {
        if ($runtime.started -and $runtime.began) { $classification = 'launcher_pair' }
        elseif ($runtime.began -and ($null -eq $ObservedExit -or $ObservedExit -ne 0)) { $classification = 'killed_in_guard_setup' }
    } elseif ($null -eq $ObservedExit -or $ObservedExit -ne 0) { $classification = 'no_site_reached' }
    elseif ($Create.shape -in @('version_probe','help_probe')) { $classification = 'no_code_probe' }
    return [pscustomobject]@{
        classification=$classification
        runtime_pid=if ($runtime) { $runtime.pid } else { $null }
        runtime_creation_time=if ($runtime) { $runtime.creation_time } else { $null }
    }
}
function Test-Main5ControlLedger([string]$Directory) {
    try {
        $files = @(Get-ChildItem -LiteralPath $Directory -Filter '*.jsonl' -File)
        if ($files.Count -ne 2) { return $false }
        $identities = @()
        foreach ($file in $files) {
            $rows = @(Get-Content -LiteralPath $file.FullName | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
            if ($rows.Count -ne 2) { return $false }
            if ($rows[0].pid -ne $rows[1].pid -or $rows[0].test -cne $rows[1].test) { return $false }
            $codes = @($rows | ForEach-Object { $_.code } | Sort-Object -CaseSensitive)
            if (($codes -join ',') -cne 'MAIN5_REAL_ADAPTER,MAIN5_WRITE') { return $false }
            $identities += [string]$rows[0].test
        }
        return (($identities | Sort-Object -CaseSensitive) -join ',') -ceq 'MAIN5_CONTROL_CHILD,MAIN5_CONTROL_PARENT'
    } catch { return $false }
}
function Get-Main5GuardedUntracedClassification([object[]]$Rows, [object[]]$GuardRows, [string]$BasePython, [Nullable[long]]$ScoredStart, [Nullable[long]]$ScoredEnd) {
    $failed = 'unattributed_ledger_row'
    if (-not $BasePython -or $null -eq $ScoredStart -or $null -eq $ScoredEnd -or $ScoredStart -gt $ScoredEnd) { return $failed }
    $begins = @($Rows | Where-Object { $_.kind -ceq 'guard_begin' })
    $starts = @($Rows | Where-Object { $_.kind -ceq 'guard_start' })
    if ($begins.Count -ne 1 -or $starts.Count -ne 1) { return $failed }
    $begin = $begins[0]
    $start = $starts[0]
    foreach ($row in @($begin,$start)) {
        if ($null -eq $row.pid -or $null -eq $row.creation_time -or
            [string]$row.image -ine $BasePython -or $null -eq $row.flags.no_site -or $row.flags.no_site -ne $false -or
            [long]$row.creation_time -lt $ScoredStart -or [long]$row.creation_time -gt $ScoredEnd) { return $failed }
    }
    if ($begin.pid -ne $start.pid -or $begin.creation_time -ne $start.creation_time) { return $failed }
    if (@($GuardRows | Where-Object { $_.pid -eq $start.pid -and ($_.kind -ceq 'guard_refusal' -or $null -ne $_.code) }).Count -gt 0) { return $failed }
    return 'guarded_untraced'
}
function Test-Main5ScoredLedgerAttribution([object[]]$SpawnRows, [object[]]$GuardRows, [string]$Mode = 'Discover', [string]$BasePython = '', [Nullable[long]]$ScoredStart = $null, [Nullable[long]]$ScoredEnd = $null, [ref]$GuardedUntraced = $null) {
    $identityRows = @{}
    $attributed = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $createByChild = @{}
    foreach ($row in $SpawnRows) {
        if ($row.kind -eq 'create_process') {
            if ($null -eq $row.child_pid -or $null -eq $row.creation_time -or $null -eq $row.parent_creation_time) { return $false }
            $childKey = '{0}:{1}' -f $row.child_pid,$row.creation_time
            if ($createByChild.ContainsKey($childKey)) { return $false }
            $createByChild[$childKey] = $row
        }
        if ($row.kind -notin @('guard_begin','guard_start')) { continue }
        if ($null -eq $row.pid -or $null -eq $row.creation_time) { return $false }
        $key = '{0}:{1}' -f $row.pid,$row.creation_time
        if (-not $identityRows.ContainsKey($key)) { $identityRows[$key] = $row }
        if ($row.runner_direct_role -cin @('origin','collect','suite') -or
            ($Mode -ceq 'Coverage' -and $row.runner_direct_role -ceq 'coverage')) { $null = $attributed.Add($key) }
        elseif ($row.runner_direct_role) { return $false }
    }
    if ($attributed.Count -eq 0) { return $false }
    for ($pass = 0; $pass -le $identityRows.Count; $pass++) {
        $advanced = $false
        foreach ($key in @($identityRows.Keys)) {
            if ($attributed.Contains($key)) { continue }
            $row = $identityRows[$key]
            if ($null -eq $row.parent_pid -or $null -eq $row.parent_creation_time) { continue }
            $parentKey = '{0}:{1}' -f $row.parent_pid,$row.parent_creation_time
            if ($attributed.Contains($parentKey)) { $null = $attributed.Add($key); $advanced = $true; continue }
            if (-not $createByChild.ContainsKey($parentKey)) { continue }
            $create = $createByChild[$parentKey]
            $creatorKey = '{0}:{1}' -f $create.parent_pid,$create.parent_creation_time
            if ($attributed.Contains($creatorKey)) { $null = $attributed.Add($key); $advanced = $true }
        }
        if (-not $advanced) { break }
    }
    $untraced = @()
    foreach ($key in @($identityRows.Keys)) {
        if ($attributed.Contains($key)) { continue }
        $identity = $identityRows[$key]
        $rows = @($SpawnRows | Where-Object { $_.kind -cin @('guard_begin','guard_start') -and $_.pid -eq $identity.pid -and $_.creation_time -eq $identity.creation_time })
        $classification = Get-Main5GuardedUntracedClassification -Rows $rows -GuardRows $GuardRows -BasePython $BasePython -ScoredStart $ScoredStart -ScoredEnd $ScoredEnd
        if ($classification -cne 'guarded_untraced') { return $false }
        $null = $attributed.Add($key)
        $untraced += [pscustomobject]@{pid=$identity.pid;creation_time=$identity.creation_time;shape='guarded_untraced';classification=$classification;exit_code=$null}
    }
    if ($null -ne $GuardedUntraced) { $GuardedUntraced.Value = @($untraced | Sort-Object pid,creation_time) }
    foreach ($row in $GuardRows) {
        if ($null -eq $row.pid -or $null -eq $row.creation_time) { return $false }
        if (-not $attributed.Contains(('{0}:{1}' -f $row.pid,$row.creation_time))) { return $false }
    }
    return $true
}
function Get-Main5ClassCounts([object[]]$Classifications) {
    foreach ($group in @($Classifications | Group-Object -Property {
        if ($_ -is [System.Collections.IDictionary]) { [string]$_['classification'] }
        else { [string]$_.classification }
    })) {
        if (-not $group.Name) { throw 'MAIN5_CLASSIFICATION_MISSING' }
        [pscustomobject]@{classification=$group.Name;count=$group.Count}
    }
}
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
Push-Location -LiteralPath $repo
try {
$kitValue = if ($KitDirectory) { $KitDirectory } else { $env:MAIN5_KIT_DIR }
if (-not $kitValue) { throw 'MAIN5_KIT_DIRECTORY_REQUIRED' }
$kit = [IO.Path]::GetFullPath($kitValue)
$attempt = [IO.Path]::GetFullPath($AttemptDirectory)
$pinnedKit = Assert-Main5PinnedKit $kit
$sharedPython = if ($DependencyPython) { [IO.Path]::GetFullPath($DependencyPython) } else { Join-Path $repo '.venv\Scripts\python.exe' }
$startupSource = Join-Path $repo 'tools\testing\main5_startup\sitecustomize.py'
$uv = if ($env:MAIN5_UV_EXE) { $env:MAIN5_UV_EXE } else { (Get-Command uv -ErrorAction Stop).Source }
$gitCommand = (Get-Command git.exe -ErrorAction Stop).Source
$gitBash = Join-Path (Split-Path (Split-Path $gitCommand -Parent) -Parent) 'bin\bash.exe'
if (Test-Path -LiteralPath $attempt) { throw 'MAIN5_ATTEMPT_EXISTS' }
if (-not (Test-Path -LiteralPath $kit -PathType Container)) { throw 'MAIN5_KIT_DIRECTORY_MISSING' }
if (-not (Test-Path -LiteralPath (Join-Path $kit 'port-guard\sitecustomize.py') -PathType Leaf)) { throw 'MAIN5_PORT_GUARD_MISSING' }
if (-not (Test-Path -LiteralPath $sharedPython -PathType Leaf)) { throw 'MAIN5_SHARED_PYTHON_MISSING' }
if (-not (Test-Path -LiteralPath $startupSource -PathType Leaf)) { throw 'MAIN5_STARTUP_MISSING' }
if (-not (Test-Path -LiteralPath $gitBash -PathType Leaf)) { throw 'MAIN5_GIT_BASH_MISSING' }
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try { $worktreeStatus = @(& git -C $repo status --porcelain=v1 --untracked-files=all) }
finally { $ErrorActionPreference = $previousErrorAction }
$worktreeClean = $worktreeStatus.Count -eq 0
if ($RequireClean -and -not $worktreeClean) { throw 'MAIN5_WORKTREE_NOT_CLEAN' }
$hookHome = if ($PreCommitHome) { $PreCommitHome } else { $env:PRE_COMMIT_HOME }
if ($hookHome) {
    $hookHome = [IO.Path]::GetFullPath($hookHome)
    if (-not (Test-Path -LiteralPath (Join-Path $hookHome 'db.db') -PathType Leaf)) {
        throw 'MAIN5_PRECOMMIT_CACHE_UNAVAILABLE'
    }
    $env:PRE_COMMIT_HOME = $hookHome
}

$shortWorkBase = 'C:\worktrees\m5t'
do {
    $attemptToken = [Guid]::NewGuid().ToString('N').Substring(0,8)
    $shortWorkRoot = Join-Path $shortWorkBase $attemptToken
} while (Test-Path -LiteralPath $shortWorkRoot)
$workRoots = [ordered]@{
    scored_basetemp = Join-Path $shortWorkRoot 's'
    self_test_basetemp = Join-Path $shortWorkRoot 't'
    collection_pycache = Join-Path $shortWorkRoot 'pc'
    scored_pycache = Join-Path $shortWorkRoot 'ps'
    self_test_pycache = Join-Path $shortWorkRoot 'pt'
}
$longPathsEnabled = $null
try {
    $longPathsEnabled = [int](Get-ItemPropertyValue -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop)
} catch { }
$workRootLengths = Assert-Main5WorkRoots -Roots $workRoots -LongPathsEnabled $longPathsEnabled
if ($workRoots.scored_basetemp.Length -gt 40 -or $workRoots.self_test_basetemp.Length -gt 40) { throw 'MAIN5_WORK_ROOT_TOO_DEEP' }

New-Item -ItemType Directory -Path $attempt | Out-Null
New-Item -ItemType Directory -Path $shortWorkRoot | Out-Null
foreach ($name in @('collection_pycache','scored_pycache','self_test_pycache')) {
    New-Item -ItemType Directory -Path $workRoots[$name] | Out-Null
}
[ordered]@{short_work_root=$shortWorkRoot;attempt_token=$attemptToken;long_paths_enabled=$longPathsEnabled;roots=$workRoots;lengths=$workRootLengths} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $attempt 'work-roots.json') -Encoding utf8
$venv = Join-Path $attempt 'venv'
$logs = Join-Path $attempt 'logs'
$controlLogs = Join-Path $attempt 'control-logs'
$controlProtected = Join-Path $attempt 'control-protected'
$pycache = $workRoots.collection_pycache
New-Item -ItemType Directory -Path $logs | Out-Null
New-Item -ItemType Directory -Path $controlLogs | Out-Null
New-Item -ItemType Directory -Path $controlProtected | Out-Null
[ordered]@{
    source = 'main5-kit-pin-claude-ruling-20260930'
    v1_kit_raw_argv_rows = [ordered]@{
        partition_stop = 4
        ruling_n = 8
        ruling_v = 7
        ruling_t = 4
    }
    secret_like_values_found = 0
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $attempt 'prior-v1-kit-scan-counts.json') -Encoding utf8
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try { & $uv venv --python $sharedPython --no-python-downloads $venv *> (Join-Path $attempt 'venv-creation.txt'); $venvExit = $LASTEXITCODE }
finally { $ErrorActionPreference = $previousErrorAction }
if ($venvExit -ne 0) { throw 'MAIN5_VENV_CREATION_FAILED' }
$previousProjectEnvironment = $env:UV_PROJECT_ENVIRONMENT
$env:UV_PROJECT_ENVIRONMENT = $venv
try {
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $uv sync --frozen --extra dev --offline *> (Join-Path $attempt 'venv-sync.txt'); $syncExit = $LASTEXITCODE }
    finally { $ErrorActionPreference = $previousErrorAction }
} finally {
    $env:UV_PROJECT_ENVIRONMENT = $previousProjectEnvironment
}
if ($syncExit -ne 0) { throw 'MAIN5_FROZEN_SYNC_FAILED' }
$python = Join-Path $venv 'Scripts\python.exe'
$site = Join-Path $venv 'Lib\site-packages'
Initialize-Main5ScoredPlugin -Site $site -Venv $venv -Attempt $attempt
$paths = @(
    (Join-Path $kit 'port-guard'),
    (Join-Path $kit 'pytest-plugins'),
    (Join-Path $kit 'keyring-audit'),
    (Join-Path $kit 'evidence\rf37604d\claude-suites\marker')
)
[IO.File]::WriteAllText((Join-Path $site 'main5-kit.pth'),(($paths -join "`n") + "`n"),[Text.UTF8Encoding]::new($false))
$guardPath = Join-Path $site 'main5_guard_impl.py'
Copy-Item -LiteralPath (Join-Path $repo 'tools\testing\main5_startup\main5_guard_impl.py') -Destination $guardPath
$activation = @'
import json
import os
import runpy
import sys
from pathlib import Path

if not getattr(sys, "_main5_guard_activated", False):
    sys._main5_guard_activated = True
    guard = Path(__file__).with_name("main5_guard_impl.py").resolve()
    config = json.loads(guard.with_name("main5-config.json").read_text(encoding="utf-8"))
    original_system_root = os.environ.get("SystemRoot")
    temporary_system_root = not original_system_root and bool(config.get("system_root"))
    if temporary_system_root:
        os.environ["SystemRoot"] = config["system_root"]
    try:
        try:
            runpy.run_path(str(guard), run_name="_main5_guard_impl")
        finally:
            if temporary_system_root:
                if original_system_root is None:
                    os.environ.pop("SystemRoot", None)
                else:
                    os.environ["SystemRoot"] = original_system_root
    except BaseException:
        try:
            config = json.loads(guard.with_name("main5-config.json").read_text(encoding="utf-8"))
            refusal = Path(config["log_dir"]) / f"{os.getpid()}-activation.jsonl"
            with refusal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"kind": "guard_refusal", "pid": os.getpid(), "code": "activation_failure"}, separators=(",", ":")) + "\n")
        except BaseException:
            os._exit(87)
        os._exit(86)

'@
[IO.File]::WriteAllText((Join-Path $site 'main5_activate.py'),$activation,[Text.UTF8Encoding]::new($false))
$activationFailureCode = @'
try:
    import main5_activate
except BaseException:
    try:
        import json
        from pathlib import Path
        config = json.loads(Path(r"__CONFIG_PATH__").read_text(encoding="utf-8"))
        refusal = Path(config["log_dir"]) / f"{os.getpid()}-activation.jsonl"
        with refusal.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": "guard_refusal", "pid": os.getpid(), "code": "activation_failure"}, separators=(",", ":")) + "\n")
    except BaseException:
        os._exit(87)
    os._exit(86)
'@
$activationFailureCode = $activationFailureCode.Replace('__CONFIG_PATH__',[IO.Path]::GetFullPath((Join-Path $site 'main5-config.json')))
$activationLine = 'import os,sys; exec(' + ($activationFailureCode | ConvertTo-Json -Compress) + ')'
[IO.File]::WriteAllText((Join-Path $site '00-main5-guard.pth'),$activationLine + "`n",[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $site 'sitecustomize.py'),"# MAIN-5 attempt guard activation is owned by 00-main5-guard.pth.`n",[Text.UTF8Encoding]::new($false))
$guardConfig = [ordered]@{
    log_dir = $controlLogs
    control_protected_root = $controlProtected
    program_data = $env:ProgramData
    system_root = $env:SystemRoot
    port_guard = (Join-Path $kit 'port-guard\sitecustomize.py')
    X1_GUARD_LOG = (Join-Path $attempt 'port-guard.jsonl')
    KEYRING_AUDIT_LOG = (Join-Path $attempt 'keyring-audit.jsonl')
}
[IO.File]::WriteAllText((Join-Path $site 'main5-config.json'),($guardConfig | ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false))
$controlConfigSha256 = Get-Main5Sha256 (Join-Path $site 'main5-config.json')
Copy-Item -LiteralPath (Join-Path $site 'main5-config.json') -Destination (Join-Path $attempt 'control-config.json')

$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = $pycache
$env:MAIN5_GUARD_LOG_DIR = $controlLogs
$env:MAIN5_CONTROL_PROTECTED_ROOT = $controlProtected
$env:MAIN5_TEST_ID = 'MAIN5_CONTROL_PARENT'
$env:X1_GUARD_LOG = Join-Path $attempt 'port-guard.jsonl'
$env:KEYRING_AUDIT_LOG = Join-Path $attempt 'keyring-audit.jsonl'
$env:PYTHON_KEYRING_BACKEND = 'counting_keyring.CountingKeyring'
$env:PYTHONPATH = ''
$env:PATH = (Split-Path $gitBash -Parent) + ';' + (Join-Path $kit 'docker-shim') + ';' + $env:PATH
$resolvedBash = (Get-Command bash.exe -ErrorAction Stop).Source
$resolvedUv = (Get-Command uv.exe -ErrorAction Stop).Source
if ([IO.Path]::GetFullPath($resolvedBash) -cne [IO.Path]::GetFullPath($gitBash)) { throw 'MAIN5_BASH_NOT_PINNED' }

$control = @'
import os,sys,subprocess
probe='''
import os,sys,socket,shutil,keyring,optimus
from pathlib import Path
from types import SimpleNamespace
import optimus.acp.trusted_paths as trusted
want=Path(os.environ['MAIN5_EXPECTED_STARTUP']).resolve()
got=Path(sys.modules['sitecustomize'].__file__).resolve()
assert got==want,(got,want)
assert Path(optimus.__file__).resolve().is_relative_to(Path(os.environ['MAIN5_EXPECTED_SOURCE']).resolve())
assert type(keyring.get_keyring()).__name__=='CountingKeyring'
assert 'docker-shim' in (shutil.which('docker') or '').replace(chr(92),'/')
for port in (6379,8765):
    try: socket.create_connection(('127.0.0.1',port),timeout=1)
    except ConnectionRefusedError as exc: assert 'RF-GUARD' in str(exc)
    else: raise AssertionError('port guard did not refuse')
try: trusted._real_windows_known_folders()
except RuntimeError as exc: assert str(exc)=='MAIN5_REAL_ADAPTER'
else: raise AssertionError('real adapter not guarded')
root=Path(os.environ['MAIN5_CONTROL_PROTECTED_ROOT'])
folders=SimpleNamespace(roaming_appdata=root/'Roaming',local_appdata=root/'Local')
assert trusted.resolve_trusted_operator_roots(platform_name='win32',windows_known_folders=folders).approval_runtime_root==root/'Local'/'optimus-cost-agent'
target=root/'blocked'
try: target.write_text('control',encoding='utf-8')
except PermissionError as exc: assert str(exc)=='MAIN5_WRITE'
else: raise AssertionError('protected write not guarded')
assert not target.exists()
if os.environ['MAIN5_TEST_ID']=='MAIN5_CONTROL_CHILD':
    assert 'SystemRoot' not in os.environ
'''
exec(probe)
child_env={key:os.environ[key] for key in ('PATH','MAIN5_GUARD_LOG_DIR','MAIN5_CONTROL_PROTECTED_ROOT','MAIN5_EXPECTED_STARTUP','MAIN5_EXPECTED_SOURCE','PYTHON_KEYRING_BACKEND')}
child_env['MAIN5_TEST_ID']='MAIN5_CONTROL_CHILD'
subprocess.run([sys.executable,'-c',probe],env=child_env,check=True)
print('MAIN5_CONTROLS_PASS')
'@
$env:MAIN5_EXPECTED_STARTUP = Join-Path $site 'sitecustomize.py'
$env:MAIN5_EXPECTED_SOURCE = Join-Path $repo 'src'
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$previousControlRole = $env:MAIN5_DIRECT_LAUNCH
$env:MAIN5_DIRECT_LAUNCH = 'control'
try { & $python -c $control *> (Join-Path $attempt 'controls.txt'); $controlExit = $LASTEXITCODE }
finally { $ErrorActionPreference = $previousErrorAction; $env:MAIN5_DIRECT_LAUNCH = $previousControlRole }
if ($controlExit -ne 0) { throw 'MAIN5_CONTROLS_FAILED' }
if (-not (Test-Main5ControlLedger -Directory $controlLogs)) { throw 'MAIN5_CONTROL_BARRIERS_MISSING' }
if (@(Get-ChildItem -LiteralPath $logs -File).Count -ne 0) { throw 'MAIN5_CONTROL_LEDGER_CONTAMINATION' }
$guardConfig.log_dir = $logs
[IO.File]::WriteAllText((Join-Path $site 'main5-config.json'),($guardConfig | ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false))
$attemptConfigSha256 = Get-Main5Sha256 (Join-Path $site 'main5-config.json')
Copy-Item -LiteralPath (Join-Path $site 'main5-config.json') -Destination (Join-Path $attempt 'attempt-config.json')
$env:MAIN5_GUARD_LOG_DIR = $logs
$env:MAIN5_CONTROL_PROTECTED_ROOT = ''
$env:MAIN5_TEST_ID = ''
$originProbe = @'
import importlib.util, json, sys
names = ('optimus', 'pydantic', 'zr_marker')
origins = {}
for name in names:
    spec = importlib.util.find_spec(name)
    if spec is None or spec.origin is None:
        raise RuntimeError('MAIN5_IMPORT_ORIGIN_MISSING:' + name)
    origins[name] = spec.origin
print(json.dumps({'origins': origins, 'sys_path': sys.path}))
'@
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$previousDirectRole = $env:MAIN5_DIRECT_LAUNCH
$env:MAIN5_DIRECT_LAUNCH = 'origin'
try { $originText = & $python -c $originProbe 2> (Join-Path $attempt 'origin-stderr.txt'); $originExit = $LASTEXITCODE }
finally { $ErrorActionPreference = $previousErrorAction; $env:MAIN5_DIRECT_LAUNCH = $previousDirectRole }
if ($originExit -ne 0) { throw 'MAIN5_IMPORT_ORIGIN_PROBE_FAILED' }
$origin = $originText | ConvertFrom-Json
$siteResolved = [IO.Path]::GetFullPath($site)
$pydanticOrigin = [IO.Path]::GetFullPath($origin.origins.pydantic)
if (-not $pydanticOrigin.StartsWith($siteResolved + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'MAIN5_PYDANTIC_OUTSIDE_DEDICATED_VENV'
}
$meta = [ordered]@{
    mode = $Mode
    branch = (& git -C $repo branch --show-current)
    head = (& git -C $repo rev-parse HEAD)
    src_tree = (& git -C $repo rev-parse 'HEAD:src')
    worktree_clean = $worktreeClean
    worktree_entry_count = $worktreeStatus.Count
    precommit_cache_provided = [bool]$hookHome
    kit_directory = $pinnedKit.directory
    kit_manifest_sha256 = $pinnedKit.manifest_sha256
    kit_manifest_entry_count = $pinnedKit.entry_count
    venv = $venv
    pycache_prefix = $pycache
    scored_pycache_prefix = $null
    short_work_root = $shortWorkRoot
    attempt_token = $attemptToken
    long_paths_enabled = $longPathsEnabled
    work_roots = $workRoots
    work_root_lengths = $workRootLengths
    scored_basetemp_zip_sha256 = $null
    scored_basetemp_archive = $null
    scored_plugin_sha256 = Get-Main5Sha256 (Join-Path $site 'main5_scored_scope.py')
    scored_plugin_config_sha256 = Get-Main5Sha256 (Join-Path $site 'main5-scored-scope.json')
    scored_lane_window = $null
    self_test_basetemp_zip_sha256 = $null
    self_test_basetemp_archive = $null
    python = $python
    resolved_bash = $resolvedBash
    resolved_uv = $resolvedUv
    origins = $origin.origins
    sys_path = @($origin.sys_path)
    startup_sha256 = Get-Main5Sha256 (Join-Path $site 'sitecustomize.py')
    activation_sha256 = Get-Main5Sha256 (Join-Path $site '00-main5-guard.pth')
    activation_helper_sha256 = Get-Main5Sha256 (Join-Path $site 'main5_activate.py')
    guard_impl_sha256 = Get-Main5Sha256 (Join-Path $site 'main5_guard_impl.py')
    guard_config_sha256 = $attemptConfigSha256
    control_guard_config_sha256 = $controlConfigSha256
    attempt_guard_config_sha256 = $attemptConfigSha256
    pth_sha256 = Get-Main5Sha256 (Join-Path $site 'main5-kit.pth')
}
$meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $attempt 'metadata.json') -Encoding utf8
$censusFile = Join-Path $attempt 'process-census.jsonl'
$censusStop = Join-Path $attempt 'process-census.stop'
$censusJob = Start-Job -ArgumentList $censusFile,$censusStop,$repo,$venv,$PID -ScriptBlock {
    param($output,$stop,$repoRoot,$venvRoot,$runnerPid)
    function Descends([int]$target, [int]$runner, [hashtable]$parents, [hashtable]$created) {
        $current = $target
        $seen = @{}
        while ($current -gt 0 -and -not $seen.ContainsKey($current)) {
            if ($current -eq $runner) { return $true }
            $seen[$current] = $true
            if (-not $parents.ContainsKey($current)) { break }
            $parent = [int]$parents[$current]
            if (-not $created.ContainsKey($current) -or -not $created.ContainsKey($parent) -or
                $null -eq $created[$current] -or $null -eq $created[$parent] -or
                [long]$created[$parent] -gt [long]$created[$current]) { break }
            $current = $parent
        }
        return $false
    }
    function Related([int]$target, [int]$runner, [hashtable]$parents, [hashtable]$created) {
        return (Descends $target $runner $parents $created) -or (Descends $runner $target $parents $created)
    }
    function Capture([string]$phase) {
        try { $items = @(Get-CimInstance Win32_Process -ErrorAction Stop) }
        catch {
            [IO.File]::AppendAllText($output, ((@{phase=$phase;unavailable=$true;processes=@()} | ConvertTo-Json -Compress) + "`n"))
            return
        }
        $parents = @{}
        $created = @{}
        foreach ($item in $items) {
            $parents[[int]$item.ProcessId] = [int]$item.ParentProcessId
            $created[[int]$item.ProcessId] = if ($item.CreationDate) { $item.CreationDate.ToFileTimeUtc() } else { $null }
        }
        $rows = @()
        foreach ($item in $items) {
            $line = [string]$item.CommandLine
            $exe = [string]$item.ExecutablePath
            $image = [string]$item.Name
            $inTree = Descends ([int]$item.ProcessId) ([int]$runnerPid) $parents $created
            if (-not $inTree -and $image -notmatch '(?i)^(?:python(?:w)?|pytest|pre-commit|optimus)\.exe$') { continue }
            $reason = $null
            if ($image -match 'pre-commit' -or $line -match '(?i)(?:^|\s)pre-commit(?:\s|$)') {
                $reason = 'pre_commit'
            } elseif ($line -match '(?i)pytest' -and ($line -match '(?i)optimus' -or $exe -match '(?i)optimus')) {
                $reason = 'optimus_pytest'
            } elseif ($line -match '(?i)optimus[.\\/]acp|optimus-cost-agent') {
                $reason = 'optimus_acp'
            } elseif ($image -match '(?i)^python(?:w)?\.exe$' -and $exe -match '(?i)optimus') {
                $reason = 'other_python_in_worktree'
            }
            if (-not $reason -and -not $inTree) { continue }
            if (-not $reason) { $reason = 'own_descendant' }
            $root = $null
            $match = [regex]::Match($exe,'(?i)^(.*?)[\\/](?:\.venv|venv)[\\/](?:Scripts|bin)[\\/]')
            if ($match.Success) { $root = $match.Groups[1].Value }
            $rows += [ordered]@{
                pid = [int]$item.ProcessId
                ppid = [int]$item.ParentProcessId
                image = $image
                executable = $exe
                created_at = if ($item.CreationDate) { $item.CreationDate.ToString('o') } else { $null }
                worktree_root = $root
                match_reason = $reason
                foreign = -not $inTree
                tree_member = $inTree
            }
        }
        $record = [ordered]@{phase=$phase;at=(Get-Date).ToUniversalTime().ToString('o');unavailable=$false;processes=$rows}
        [IO.File]::AppendAllText($output, (($record | ConvertTo-Json -Depth 6 -Compress) + "`n"))
    }
    Capture 'start'
    $next = (Get-Date).AddSeconds(60)
    while (-not (Test-Path -LiteralPath $stop)) {
        Start-Sleep -Seconds 1
        if ((Get-Date) -ge $next) {
            Capture 'interval'
            $next = (Get-Date).AddSeconds(60)
        }
    }
    Capture 'end'
}
$deadline = (Get-Date).AddSeconds(15)
while (-not (Test-Path -LiteralPath $censusFile) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200 }
if (-not (Test-Path -LiteralPath $censusFile)) { throw 'MAIN5_CENSUS_START_FAILED' }
function Stop-Main5Census {
    [IO.File]::WriteAllText($censusStop,'stop')
    $null = Wait-Job -Job $censusJob -Timeout 15
    if ($censusJob.State -ne 'Completed') { Stop-Job -Job $censusJob; throw 'MAIN5_CENSUS_STOP_FAILED' }
    $null = Receive-Job -Job $censusJob -ErrorAction Stop
    $records = @(Get-Content -LiteralPath $censusFile | ForEach-Object { $_ | ConvertFrom-Json })
    if ($records.Count -lt 2 -or $records[0].phase -ne 'start' -or $records[-1].phase -ne 'end') {
        throw 'MAIN5_CENSUS_INCOMPLETE'
    }
    $foreign = @($records | ForEach-Object { $_.processes } | Where-Object { $_.foreign -eq $true })
    $unavailable = @($records | Where-Object { $_.unavailable -eq $true })
    return [pscustomobject]@{
        foreign_count = $foreign.Count
        unavailable_count = $unavailable.Count
        records = $records
    }
}
function Get-Main5RootVerdict([bool]$rootSame, [bool]$foreignAny) {
    if ($rootSame) { return 'CLEAN' }
    if ($foreignAny) { return 'CONFOUNDED' }
    return 'FAIL'
}
function Compare-Main5RootSnapshot([string]$BeforePath, [string]$AfterPath) {
    $beforeSnapshot = Get-Content -LiteralPath $BeforePath -Raw | ConvertFrom-Json
    $afterSnapshot = Get-Content -LiteralPath $AfterPath -Raw | ConvertFrom-Json
    $names = @($beforeSnapshot.roots.PSObject.Properties.Name | Sort-Object)
    if ($names.Count -ne 4 -or $names -join ',' -cne (@($afterSnapshot.roots.PSObject.Properties.Name | Sort-Object) -join ',')) { throw 'MAIN5_ROOT_COUNT' }
    foreach ($name in $names) {
        $left = $beforeSnapshot.roots.PSObject.Properties[$name].Value | ConvertTo-Json -Depth 12 -Compress
        $right = $afterSnapshot.roots.PSObject.Properties[$name].Value | ConvertTo-Json -Depth 12 -Compress
        if ($left -cne $right) { return $false }
    }
    return $true
}
if ($Mode -eq 'Control') {
    $census = Stop-Main5Census
    @{mode=$Mode;process_tree_status='PASS';foreign_process_count=$census.foreign_count;census_unavailable_count=$census.unavailable_count} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $attempt 'result.json') -Encoding utf8
    if ($census.unavailable_count -gt 0) { exit 1 }
    Write-Output 'MAIN5_CONTROL_PASS'
    exit 0
}
$selfTestVenv = Join-Path $attempt 'self-test-venv'
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try { & $uv venv --python $sharedPython --no-python-downloads $selfTestVenv *> (Join-Path $attempt 'self-test-venv-creation.txt'); $selfVenvExit = $LASTEXITCODE }
finally { $ErrorActionPreference = $previousErrorAction }
if ($selfVenvExit -ne 0) { throw 'MAIN5_SELF_TEST_VENV_CREATION_FAILED' }
$previousProjectEnvironment = $env:UV_PROJECT_ENVIRONMENT
$env:UV_PROJECT_ENVIRONMENT = $selfTestVenv
try {
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $uv sync --frozen --extra dev --offline *> (Join-Path $attempt 'self-test-venv-sync.txt'); $selfSyncExit = $LASTEXITCODE }
    finally { $ErrorActionPreference = $previousErrorAction }
} finally {
    $env:UV_PROJECT_ENVIRONMENT = $previousProjectEnvironment
}
if ($selfSyncExit -ne 0) { throw 'MAIN5_SELF_TEST_FROZEN_SYNC_FAILED' }
$selfTestPython = Join-Path $selfTestVenv 'Scripts\python.exe'
$snapshot = Join-Path $repo 'tools\testing\main5_snapshot.ps1'
$env:KIT_AUDIT_LOG = Join-Path $attempt 'suite-audit.jsonl'
$collectArgs = @('-m','pytest',("--rootdir={0}" -f $repo),'-p','zr_marker','-p','kit_audit','-p','no:cacheprovider','--collect-only','-q')
$null = Invoke-Main5FullCollection -Python $python -Attempt $attempt -Arguments $collectArgs
$fullNodeIds = @(Get-Content -LiteralPath (Join-Path $attempt 'full-collection.txt') | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^tests[/\\].*::' })
$partition = Get-Main5LanePartition -FullNodeIds $fullNodeIds -SelfTestFile 'tests/unit/acp/test_main5_guard.py'
if ($partition.self_test_nodeids.Count -ne @($fullNodeIds | Where-Object { $_.StartsWith('tests/unit/acp/test_main5_guard.py::',[StringComparison]::Ordinal) }).Count) { throw 'MAIN5_SELF_TEST_PARTITION_NOT_WHOLE_FILE' }
$partition | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $attempt 'partition.json') -Encoding utf8
$targetNodeIds = @()
if ($PytestTarget.Count -gt 0) {
    $targetNodeIds = @(Resolve-Main5TargetSet -FullNodeIds $fullNodeIds -Targets $PytestTarget -SelfTestFile 'tests/unit/acp/test_main5_guard.py' -SelfTestNodeIds $partition.self_test_nodeids)
}
$scoredTargets = @($PytestTarget | Where-Object { $_ -cne 'tests/unit/acp/test_main5_guard.py' })
$runScored = $true
$runSelfTest = $true
if ($Mode -eq 'Discover' -and $targetNodeIds.Count -eq 0) { $runScored = $false; $runSelfTest = $false }
if ($targetNodeIds.Count -gt 0 -and $scoredTargets.Count -eq 0) { $runScored = $false }
$scoredExit = 0
$scoredStart = $null
$scoredEnd = $null
$selfTestExit = 0
$scoredBefore = Join-Path $attempt 'scored-before.json'
$scoredAfter = Join-Path $attempt 'scored-after.json'
$selfBefore = Join-Path $attempt 'self-test-before.json'
$selfAfter = Join-Path $attempt 'self-test-after.json'
try {
    & $snapshot -OutputFile (Join-Path $attempt 'before.json')
    if ($runScored) {
        & $snapshot -OutputFile $scoredBefore
        $scoredArgs = @('-m','pytest','-p','main5_scored_scope',("--rootdir={0}" -f $repo),'-p','zr_marker','-p','kit_audit','-p','no:cacheprovider','-q','--ignore=tests/unit/acp/test_main5_guard.py',("--basetemp={0}" -f $workRoots.scored_basetemp))
        if ($Mode -eq 'Coverage') { $env:COVERAGE_FILE = Join-Path $attempt 'scored-coverage.data'; $scoredArgs += @('--cov=optimus','--cov-branch','--cov-report=term-missing','--cov-fail-under=0','--tb=long') }
        if ($scoredTargets.Count -gt 0) { $scoredArgs += $scoredTargets }
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $previousDirectRole = $env:MAIN5_DIRECT_LAUNCH
        $env:MAIN5_DIRECT_LAUNCH = 'suite'
        $scoredStart = [DateTime]::UtcNow.ToFileTimeUtc()
        try { $scoredExit = Invoke-Main5ScoredLane -Python $python -Venv $venv -Arguments $scoredArgs -Output (Join-Path $attempt 'scored-suite.txt') }
        finally {
            $scoredEnd = [DateTime]::UtcNow.ToFileTimeUtc()
            $meta.scored_lane_window = [ordered]@{start_filetime_utc=$scoredStart;end_filetime_utc=$scoredEnd}
            $meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $attempt 'metadata.json') -Encoding utf8
            $ErrorActionPreference = $previousErrorAction
            $env:MAIN5_DIRECT_LAUNCH = $previousDirectRole
            $env:PYTHONPYCACHEPREFIX = $workRoots.collection_pycache
            $archive = Save-Main5BasetempArchive -Basetemp $workRoots.scored_basetemp -Attempt $attempt -Lane 'scored'
            $meta.scored_basetemp_zip_sha256 = $archive.sha256
            $meta.scored_basetemp_archive = $archive
            $meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $attempt 'metadata.json') -Encoding utf8
        }
        & $snapshot -OutputFile $scoredAfter
    }
    if ($runSelfTest) {
        & $snapshot -OutputFile $selfBefore
        $selfArgs = @('-m','pytest',("--rootdir={0}" -f $repo),'-p','no:cacheprovider','-q',("--basetemp={0}" -f $workRoots.self_test_basetemp),'tests/unit/acp/test_main5_guard.py')
        if ($Mode -eq 'Coverage') { $env:COVERAGE_FILE = Join-Path $attempt 'self-test-coverage.data'; $selfArgs += @('--cov=optimus','--cov-branch','--cov-report=term-missing','--cov-fail-under=0','--tb=long') }
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $env:PYTHONPYCACHEPREFIX = $workRoots.self_test_pycache
        try { & $selfTestPython @selfArgs *> (Join-Path $attempt 'self-test-suite.txt'); $selfTestExit = $LASTEXITCODE }
        finally {
            $ErrorActionPreference = $previousErrorAction
            $env:PYTHONPYCACHEPREFIX = $workRoots.collection_pycache
            $archive = Save-Main5BasetempArchive -Basetemp $workRoots.self_test_basetemp -Attempt $attempt -Lane 'self'
            $meta.self_test_basetemp_zip_sha256 = $archive.sha256
            $meta.self_test_basetemp_archive = $archive
            $meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $attempt 'metadata.json') -Encoding utf8
        }
        & $snapshot -OutputFile $selfAfter
    }
} finally {
    & $snapshot -OutputFile (Join-Path $attempt 'after.json')
    $census = Stop-Main5Census
}
$combinedCoverage = $null
if ($Mode -eq 'Coverage') {
    $combinedCoverage = Invoke-Main5CombinedCoverage -Python $python -Attempt $attempt
}
$suiteExit = if ($scoredExit -ne 0 -or $selfTestExit -ne 0 -or ($Mode -eq 'Coverage' -and ($combinedCoverage.combine_exit -ne 0 -or $combinedCoverage.report_exit -ne 0 -or $null -eq $combinedCoverage.total))) { 1 } else { 0 }
$before = Get-Content -LiteralPath (Join-Path $attempt 'before.json') -Raw | ConvertFrom-Json
$after = Get-Content -LiteralPath (Join-Path $attempt 'after.json') -Raw | ConvertFrom-Json
$rootNames = @($before.roots.PSObject.Properties.Name | Sort-Object)
if ($rootNames.Count -ne 4) { throw 'MAIN5_ROOT_COUNT' }
$rootSame = $true
foreach ($name in $rootNames) {
    $left = $before.roots.PSObject.Properties[$name].Value | ConvertTo-Json -Depth 12 -Compress
    $right = $after.roots.PSObject.Properties[$name].Value | ConvertTo-Json -Depth 12 -Compress
    if ($left -cne $right) { $rootSame = $false }
}
$violations = 0
$guardRows = @()
$guardLogs = @(Get-ChildItem -LiteralPath $logs -Filter '*.jsonl' -File)
foreach ($file in $guardLogs) {
    foreach ($line in (Get-Content -LiteralPath $file.FullName)) {
        if (-not $line.Trim()) { continue }
        $row = $line | ConvertFrom-Json
        if (-not $row.code) { throw 'MAIN5_GUARD_LOG_INVALID' }
        $guardRows += $row
        if ($row.kind -eq 'guard_refusal' -or $row.code -ne $null) { $violations++ }
    }
}
$spawnRows = @(
    Get-ChildItem -LiteralPath $logs -Filter '*.spawn' -File | ForEach-Object {
        Get-Content -LiteralPath $_.FullName | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }
    }
)
$starts = @($spawnRows | Where-Object { $_.kind -eq 'guard_start' })
$begins = @($spawnRows | Where-Object { $_.kind -eq 'guard_begin' })
$created = @($spawnRows | Where-Object { $_.kind -eq 'create_process' })
$exits = @($spawnRows | Where-Object { $_.kind -eq 'exit_code' })
$auditSpawns = @($spawnRows | Where-Object { $_.kind -eq 'audit_spawn' })
$refusals = @($guardRows | Where-Object { $_.kind -eq 'guard_refusal' })
$failures = @()
if ($refusals.Count -gt 0) { $failures += 'guard_refusal' }
if ($starts.Count -lt 1) { $failures += 'guard_start_missing' }
$startByIdentity = @{}
$beginByIdentity = @{}
$refusalByIdentity = @{}
$refusalPids = @{}
foreach ($start in $starts) {
    if ($null -eq $start.creation_time -or $null -eq $start.parent_creation_time) {
        $failures += 'guard_creation_unavailable'
        continue
    }
    $key = Get-Main5IdentityKey $start.pid $start.creation_time
    if ($startByIdentity.ContainsKey($key)) { $failures += 'duplicate_guard_identity' }
    $startByIdentity[$key] = $start
}
foreach ($begin in $begins) {
    if ($null -eq $begin.creation_time) { $failures += 'guard_begin_identity_unavailable'; continue }
    $key = Get-Main5IdentityKey $begin.pid $begin.creation_time
    if ($beginByIdentity.ContainsKey($key)) { $failures += 'duplicate_guard_begin_identity' }
    $beginByIdentity[$key] = $begin
}
foreach ($refusal in $refusals) {
    $refusalPids[[string]$refusal.pid] = $true
    if ($null -ne $refusal.creation_time) {
        $refusalByIdentity[(Get-Main5IdentityKey $refusal.pid $refusal.creation_time)] = $true
    }
}
$homeLine = @(Get-Content -LiteralPath (Join-Path $venv 'pyvenv.cfg') | Where-Object { $_ -match '^home\s*=\s*(.+)$' } | Select-Object -First 1)
if ($homeLine.Count -ne 1) { $failures += 'venv_home_missing' }
$basePython = if ($homeLine.Count -eq 1) { Join-Path ($homeLine[0] -replace '^home\s*=\s*','') 'python.exe' } else { '' }
$guardedUntraced = @()
if (-not (Test-Main5ScoredLedgerAttribution -SpawnRows $spawnRows -GuardRows $guardRows -Mode $Mode -BasePython $basePython -ScoredStart $scoredStart -ScoredEnd $scoredEnd -GuardedUntraced ([ref]$guardedUntraced))) { $failures += 'unattributed_ledger_row' }
$pairs = @()
$pythonClassifications = @()
$exitByIdentity = @{}
foreach ($exitRow in $exits) {
    if ($null -eq $exitRow.creation_time) { $failures += 'exit_identity_unavailable'; continue }
    $exitByIdentity[(Get-Main5IdentityKey $exitRow.child_pid $exitRow.creation_time)] = $exitRow
}
foreach ($create in $created) {
    $image = [string]$create.image
    $imageName = [IO.Path]::GetFileName($image)
    if ($image -eq '<unavailable>') { $failures += 'child_image_unavailable'; continue }
    if ($imageName -notmatch '(?i)^python(?:w)?\.exe$') { continue }
    if ($null -eq $create.creation_time) { $failures += 'child_creation_unavailable'; continue }
    $childKey = Get-Main5IdentityKey $create.child_pid $create.creation_time
    $observedExit = if ($exitByIdentity.ContainsKey($childKey)) { $exitByIdentity[$childKey].exit_code } else { $null }
    $isAttemptImage = $image.StartsWith($venv + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)
    if ($isAttemptImage) {
        $runtimeRows = @(@($begins) + @($starts) | Where-Object {
            $null -ne $_.parent_creation_time -and
            $_.parent_pid -eq $create.child_pid -and $_.parent_creation_time -eq $create.creation_time
        })
        $hasRefusal = $refusalByIdentity.ContainsKey($childKey) -or $refusalPids.ContainsKey([string]$create.child_pid)
        foreach ($runtimeRow in $runtimeRows) {
            $runtimeKey = Get-Main5IdentityKey $runtimeRow.pid $runtimeRow.creation_time
            if ($refusalByIdentity.ContainsKey($runtimeKey) -or $refusalPids.ContainsKey([string]$runtimeRow.pid)) { $hasRefusal = $true }
        }
        $verdict = Get-Main5LauncherVerdict -Create $create -Begins $begins -Starts $starts -ObservedExit $observedExit -HasRefusal $hasRefusal
        $classification = $verdict.classification
        if ($classification -eq 'launcher_pair') {
            $pairs += [ordered]@{
                launcher_pid=[int]$create.child_pid;launcher_created=$create.creation_time
                runtime_pid=[int]$verdict.runtime_pid;runtime_created=$verdict.runtime_creation_time;source='guard_ledger'
            }
        }
    } else {
        $hasStart = $startByIdentity.ContainsKey($childKey)
        $hasBegin = $beginByIdentity.ContainsKey($childKey)
        $hasRefusal = $refusalByIdentity.ContainsKey($childKey) -or $refusalPids.ContainsKey([string]$create.child_pid)
        $classification = 'outside_attempt_venv'
        if ($create.flags.no_site) { $classification = 'no_site' }
        elseif ($hasRefusal -or $observedExit -eq 87) { $classification = 'guard_refusal' }
        elseif ($hasStart -and $hasBegin) { $classification = 'guarded' }
        elseif ($hasBegin -and ($null -eq $observedExit -or $observedExit -ne 0)) { $classification = 'killed_in_guard_setup' }
        elseif ($null -eq $observedExit -or $observedExit -ne 0) { $classification = 'outside_attempt_venv' }
        elseif ($create.shape -in @('version_probe','help_probe')) { $classification = 'no_code_probe' }
    }
    if ($classification -in @('no_site','guard_refusal','activation_bypassed','ambiguous_runtime','outside_attempt_venv')) {
        $failures += $classification
    }
    $pythonClassifications += [pscustomobject]@{
        pid=$create.child_pid;creation_time=$create.creation_time;shape=$create.shape
        classification=$classification;exit_code=$observedExit
    }
}
$pythonClassifications += $guardedUntraced
$g5Counts = @(Get-Main5ClassCounts -Classifications $pythonClassifications)
# Only two explicitly marked PowerShell launches lack a guarded Python creator.
foreach ($start in $starts) {
    if ($null -eq $start.parent_creation_time) { continue }
    $parentKey = Get-Main5IdentityKey $start.parent_pid $start.parent_creation_time
    $alreadyCreated = @($created | Where-Object {
        $null -ne $_.creation_time -and
        (Get-Main5IdentityKey $_.child_pid $_.creation_time) -eq $parentKey
    }).Count -gt 0
    if (-not $alreadyCreated -and
        ($start.runner_direct_role -cin @('control','origin','collect','suite') -or
        ($Mode -ceq 'Coverage' -and $start.runner_direct_role -ceq 'coverage')) -and
        [string]$start.image -ieq [string]$basePython) {
        $pairs += [ordered]@{launcher_pid=[int]$start.parent_pid;launcher_created=$start.parent_creation_time;runtime_pid=[int]$start.pid;runtime_created=$start.creation_time;source=[string]$start.runner_direct_role}
    }
}
$directRoles = @($starts | Where-Object { $_.runner_direct_role } | ForEach-Object { $_.runner_direct_role } | Sort-Object -CaseSensitive -Unique)
$expectedDirectRoles = @('collect','origin')
if ($Mode -eq 'Coverage') { $expectedDirectRoles += 'coverage' }
if ($runScored) { $expectedDirectRoles += 'suite' }
$expectedDirectRoles = @($expectedDirectRoles | Sort-Object -CaseSensitive)
if (($directRoles -join ',') -cne ($expectedDirectRoles -join ',')) { $failures += 'runner_direct_provenance' }
$ownRows = @($census.records | ForEach-Object { $_.processes } | Where-Object { $_.tree_member -eq $true })
$ownPython = @($ownRows | Where-Object { $_.image -match '(?i)^python(?:w)?\.exe$' } | Sort-Object pid -Unique)
if ($census.unavailable_count -gt 0) { $failures += 'census_unavailable' }
$nonPython = @(Get-Main5NonPythonDescendants -Rows $ownRows -Created $created -Venv $venv -SelfTestVenv $selfTestVenv)
if (@($nonPython | Where-Object { $_.classification -ceq 'outside_attempt_venv' }).Count -gt 0) { $failures += 'outside_attempt_venv' }
$treeStatus = if ($failures.Count -eq 0) { 'PASS' } else { 'FAIL' }
$rootStatus = Get-Main5RootVerdict $rootSame ($census.foreign_count -gt 0)
$scoredRootStatus = 'NOT_RUN'
$selfTestRootStatus = 'NOT_RUN'
if (Test-Path -LiteralPath $scoredBefore -PathType Leaf) {
    $scoredSame = Compare-Main5RootSnapshot $scoredBefore $scoredAfter
    $scoredRootStatus = Get-Main5RootVerdict $scoredSame ($census.foreign_count -gt 0)
}
if (Test-Path -LiteralPath $selfBefore -PathType Leaf) {
    $selfSame = Compare-Main5RootSnapshot $selfBefore $selfAfter
    $selfTestRootStatus = Get-Main5RootVerdict $selfSame ($census.foreign_count -gt 0)
}
$selfTestGate = if (-not $runSelfTest) { 'NOT_RUN' } elseif ($selfTestExit -eq 0 -and $selfTestRootStatus -in @('CLEAN','CONFOUNDED')) { 'PASS' } else { 'FAIL' }
$result = [ordered]@{
    mode=$Mode;suite_exit=$suiteExit;scored_exit=$scoredExit;self_test_exit=$selfTestExit
    combined_coverage_total=if ($null -ne $combinedCoverage) { $combinedCoverage.total } else { $null }
    combined_coverage_combine_exit=if ($null -ne $combinedCoverage) { $combinedCoverage.combine_exit } else { $null }
    combined_coverage_report_exit=if ($null -ne $combinedCoverage) { $combinedCoverage.report_exit } else { $null }
    roots_unchanged=$rootSame;root_status=$rootStatus;scored_root_status=$scoredRootStatus
    self_test_root_status=$selfTestRootStatus;self_test_gate=$selfTestGate
    self_test_process_tree_status='NOT_APPLICABLE_SELF_TEST_LANE'
    violation_count=$violations;guard_violation_status=if ($violations -eq 0) { 'PASS' } else { 'FAIL' }
    guard_process_count=$guardLogs.Count
    guarded_execution_count=$starts.Count;launcher_pair_count=$pairs.Count
    launcher_pairs=$pairs;process_tree_status=$treeStatus;process_tree_failures=@($failures | Sort-Object -Unique)
    python_classifications=$pythonClassifications;g5_class_counts=$g5Counts
    guarded_untraced=$guardedUntraced;scored_lane_window=$meta.scored_lane_window
    full_nodeid_count=$partition.full_count;scored_nodeid_count=$partition.scored_nodeids.Count
    self_test_nodeid_count=$partition.self_test_nodeids.Count
    self_test_basetemp=$workRoots.self_test_basetemp
    observed_python_descendants=$ownPython.Count;non_python_descendants=$nonPython
    foreign_venv_launcher_count=@($nonPython | Where-Object { $_.classification -ceq 'outside_attempt_venv' }).Count
    pidless_spawn_events=$auditSpawns;foreign_process_count=$census.foreign_count
    census_unavailable_count=$census.unavailable_count
}
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $attempt 'result.json') -Encoding utf8
if ($suiteExit -ne 0 -or $treeStatus -ne 'PASS' -or $violations -gt 0 -or $rootStatus -eq 'FAIL' -or $scoredRootStatus -eq 'FAIL' -or $selfTestRootStatus -eq 'FAIL') { exit 1 }
Write-Output 'MAIN5_SUITE_PASS'
} finally {
    Pop-Location
}
