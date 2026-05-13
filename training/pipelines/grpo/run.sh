#!/usr/bin/env bash
# AERL
# Usage: LOG_FILE=/path/to.log bash training/pipelines/grpo/run.sh [override argv]
set -euo pipefail

# shellcheck source=../_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../_lib.sh"

LOG_FILE="${LOG_FILE:?Set LOG_FILE to the full path for training output (stdout+stderr)}"

mode="${PIPELINE_MODE:-http}"
if [[ "${mode}" == "local" || "${mode}" == "aerl" ]]; then
  DEFAULT_CONFIG="examples/math/gsm8k_grpo.yaml"
  if [[ $# -eq 0 ]]; then
    set -- --config "${DEFAULT_CONFIG}" scheduler.type=local
  fi
  training_local_aerl_run "${LOG_FILE}" python3 examples/math/gsm8k_rl.py "$@"
else
  if [[ $# -eq 0 ]]; then
    set -- scheduler.type=local
  fi
  training_http_run "grpo" "${LOG_FILE}" "$@"
fi
