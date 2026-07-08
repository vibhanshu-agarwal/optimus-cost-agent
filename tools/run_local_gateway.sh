#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env.gateway"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy .env.gateway.example and add your provider key." >&2
  exit 1
fi

cd "${ROOT}"

(
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
  exec python -m optimus_gateway "$@"
)
