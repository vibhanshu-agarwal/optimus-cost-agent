# Plan 9.96, Task 5 Batch 3 Step 4: this script no longer parses .env.gateway
# into PowerShell variables or copies its values into the invoking session's
# environment via SetEnvironmentVariable. It delegates entirely to
# `optimus-trust run-gateway`, which parses .env.gateway as untrusted
# key=value DATA, validates its file permissions, displays the complete safe
# (non-secret) configuration snapshot for review, builds a short-lived
# HMAC-signed GatewayChildManifest, and spawns the real optimus_gateway
# subprocess with --bind-host/--port/--manifest as explicit CLI arguments —
# never through OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT env vars. This
# PowerShell session never sees the provider API key or shared secret.

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvFile = Join-Path $Root ".env.gateway"

if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing $EnvFile. Copy .env.gateway.example and add your provider key."
}

Set-Location $Root

$OptimusTrust = Join-Path $Root ".venv\Scripts\optimus-trust.exe"
if (-not (Test-Path $OptimusTrust)) {
    $OptimusTrust = Join-Path $Root ".venv/bin/optimus-trust"
}
if (-not (Test-Path $OptimusTrust)) {
    $OptimusTrust = "optimus-trust"
}

& $OptimusTrust --workspace-root $Root run-gateway
exit $LASTEXITCODE
