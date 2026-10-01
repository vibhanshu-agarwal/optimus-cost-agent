param([Parameter(Mandatory=$true)][string]$OutputFile)

$ErrorActionPreference = 'Stop'
$roots = [ordered]@{}
foreach ($root in @((Join-Path $env:LOCALAPPDATA 'optimus-cost-agent'),(Join-Path $env:APPDATA 'optimus-cost-agent'),(Join-Path $env:LOCALAPPDATA 'Python Keyring'),(Join-Path $env:ProgramData 'Python Keyring'))) {
    $exists=Test-Path -LiteralPath $root
    $entries=@()
    if ($exists) { $entries=@(Get-ChildItem -LiteralPath $root -Recurse -Force | Sort-Object FullName | ForEach-Object { [ordered]@{path=$_.FullName;directory=$_.PSIsContainer;size=if ($_.PSIsContainer) {0} else {$_.Length};mtime=if ($_.PSIsContainer) {[IO.Directory]::GetLastWriteTimeUtc($_.FullName).Ticks} else {[IO.File]::GetLastWriteTimeUtc($_.FullName).Ticks}} }) }
    $roots[$root]=[ordered]@{exists=$exists;entries=$entries}
}
if (Test-Path -LiteralPath $OutputFile) { throw 'MAIN5_SNAPSHOT_EXISTS' }
[IO.File]::WriteAllText($OutputFile,([ordered]@{roots=$roots} | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
