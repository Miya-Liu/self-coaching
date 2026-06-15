#!/usr/bin/env bash
# Validate AERL / trainer pipeline configuration (HTTP or local source tree).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/modes/self-coaching/self-tuning/services/.env"
EXAMPLE="${ROOT}/modes/self-coaching/self-tuning/services/example.env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  echo "Loaded ${ENV_FILE}"
elif [[ -f "${EXAMPLE}" ]]; then
  echo "No .env yet — copy example.env and set TRAINER_BASE_URL for HTTP pipelines."
else
  echo "Missing services/example.env under modes/self-coaching/self-tuning/" >&2
  exit 1
fi

if [[ -n "${AERL_ROOT:-}" ]]; then
  if [[ ! -d "${AERL_ROOT}" || ! -f "${AERL_ROOT}/train.py" ]]; then
    echo "AERL_ROOT does not look like a trainer source tree (expected train.py): ${AERL_ROOT}" >&2
    exit 1
  fi
  echo "AERL_ROOT ok: ${AERL_ROOT}"
  if command -v uv >/dev/null 2>&1; then
    echo "Syncing Python environment in ${AERL_ROOT}..."
    uv --directory "${AERL_ROOT}" sync
  else
    echo "WARN: uv not found — skip sync; install from https://docs.astral.sh/uv/" >&2
  fi
fi

echo "HTTP pipelines: TRAINER_BASE_URL=${TRAINER_BASE_URL:-http://localhost:8004} (default from registry.yaml)"
echo "Run: bash scripts/run-pipeline.sh sft logs/my-run.log"
echo "Mock loop: python -m self_coaching.demo"
