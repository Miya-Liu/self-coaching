#!/usr/bin/env bash
# AERL
# Usage: LOG_FILE=/path/to.log bash training/pipelines/sft/run.sh [extra argv for trainer or gsm8k_sft.py]
set -euo pipefail

# shellcheck source=../_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../_lib.sh"

LOG_FILE="${LOG_FILE:?Set LOG_FILE to the full path for training output (stdout+stderr)}"

mode="${PIPELINE_MODE:-http}"
if [[ "${mode}" == "local" || "${mode}" == "aerl" ]]; then
  training_local_aerl_run "${LOG_FILE}" python3 examples/math/gsm8k_sft.py "$@"
else
  training_http_run "sft" "${LOG_FILE}" "$@"
fi
