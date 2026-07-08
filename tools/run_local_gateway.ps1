# Fallback launcher — prefer `bash tools/run_local_gateway.sh` (Git Bash) per AGENTS.md.
# PowerShell cannot scope env vars to a child process the way a bash subshell can: this
# script sets them in the CURRENT session and restores them in `finally`. If the process
# is hard-killed (window closed, Stop-Process), the provider API key stays in this
# session's environment until the window closes.

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvFile = Join-Path $Root ".env.gateway"

if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing $EnvFile. Copy .env.gateway.example and add your provider key."
}

function Read-DotEnvFile {
    param([string]$Path)

    $result = @{}
    Get-Content -Path $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) {
            return
        }
        $equals = $line.IndexOf("=")
        if ($equals -lt 1) {
            return
        }
        $key = $line.Substring(0, $equals).Trim()
        $value = $line.Substring($equals + 1).Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $result[$key] = $value
    }
    return $result
}

$overrides = Read-DotEnvFile -Path $EnvFile
$saved = @{}
foreach ($key in $overrides.Keys) {
    $saved[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
    [Environment]::SetEnvironmentVariable($key, $overrides[$key], "Process")
}

try {
    Set-Location $Root
    & python -m optimus_gateway @args
    exit $LASTEXITCODE
}
finally {
    foreach ($key in $saved.Keys) {
        if ($null -eq $saved[$key]) {
            [Environment]::SetEnvironmentVariable($key, $null, "Process")
        }
        else {
            [Environment]::SetEnvironmentVariable($key, $saved[$key], "Process")
        }
    }
}
