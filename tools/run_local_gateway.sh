#!/usr/bin/env bash
set -euo pipefail

# Plan 9.96, Task 5 Batch 3 Step 4: this script no longer sources
# .env.gateway. It delegates entirely to `optimus-trust run-gateway`, which
# parses .env.gateway as untrusted key=value DATA (never `source`d/executed),
# validates its file permissions, displays the complete safe (non-secret)
# configuration snapshot for review, builds a short-lived HMAC-signed
# GatewayChildManifest, and spawns the real optimus_gateway subprocess with
# --bind-host/--port/--manifest as explicit CLI arguments — never through
# OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT env vars. This script's own shell
# session never sees the provider API key or shared secret.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "${ROOT}/.env.gateway" ]]; then
  echo "Missing ${ROOT}/.env.gateway. Copy .env.gateway.example and add your provider key." >&2
  exit 1
fi

cd "${ROOT}"

if [[ -x "${ROOT}/.venv/Scripts/optimus-trust.exe" ]]; then
  OPTIMUS_TRUST="${ROOT}/.venv/Scripts/optimus-trust.exe"
elif [[ -x "${ROOT}/.venv/bin/optimus-trust" ]]; then
  OPTIMUS_TRUST="${ROOT}/.venv/bin/optimus-trust"
else
  OPTIMUS_TRUST=optimus-trust
fi

exec "${OPTIMUS_TRUST}" --workspace-root "${ROOT}" run-gateway
