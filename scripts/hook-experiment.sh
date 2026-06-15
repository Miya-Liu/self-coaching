#!/usr/bin/env bash
# Hook: print the standard training bash pattern (log to file). Safe for context size.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${RUN_ID:-${EXPERIMENT_ID:-run-01}}"
LOG="${TRAIN_LOG_FILE:-${EXPERIMENT_LOG_FILE:-$ROOT/logs/${RUN_ID}.log}}"
PIPELINE="${TRAIN_PIPELINE:-sft}"

cat <<EOF
[self-coaching / experiment command — run in Bash, not in chat]
Full training output MUST go to a file (never paste full logs into context):
  mkdir -p "${ROOT}/logs"
  bash "${ROOT}/scripts/run-pipeline.sh" ${PIPELINE} "${LOG}"
Or validate on mocks: python -m self_coaching.demo
Then Read "${LOG}" in small sections to parse metrics.
Set RUN_ID / TRAIN_PIPELINE / TRAIN_LOG_FILE to override defaults.
EOF
