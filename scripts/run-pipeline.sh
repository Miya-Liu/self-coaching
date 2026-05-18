#!/usr/bin/env bash
# Run a named training pipeline (AERL; see self-coaching-training/pipelines/registry.yaml).
# Usage: bash scripts/run-pipeline.sh <pipeline-id> <log-file> [args passed to the pipeline entrypoint]
# Example: bash scripts/run-pipeline.sh grpo logs/exp-01-grpo.log scheduler.type=local
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ID="${1:?usage: run-pipeline.sh <pipeline-id> <log-file> [args...]}"
LOG="${2:?usage: run-pipeline.sh <pipeline-id> <log-file> [args...]}"
shift 2

if [[ -f "${ROOT}/self-coaching-training/services/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ROOT}/self-coaching-training/services/.env"
  set +a
fi

export LOG_FILE="${LOG}"
mkdir -p "$(dirname "${LOG}")"

case "${ID}" in
  sft|grpo)
    bash "${ROOT}/self-coaching-training/pipelines/${ID}/run.sh" "$@"
    ;;
  *)
    echo "Unknown pipeline id: ${ID}. See ${ROOT}/self-coaching-training/pipelines/registry.yaml" >&2
    exit 1
    ;;
esac

echo "Finished. Log: ${LOG}"
