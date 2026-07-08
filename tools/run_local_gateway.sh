#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env.gateway"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy .env.gateway.example and add your provider key." >&2
  exit 1
fi

cd "${ROOT}"

if [[ -x "${ROOT}/.venv/Scripts/python.exe" ]]; then
  PYTHON="${ROOT}/.venv/Scripts/python.exe"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
else
  PYTHON=python
fi

(
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
  exec "${PYTHON}" -m optimus_gateway "$@"
)
