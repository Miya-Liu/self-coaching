#!/usr/bin/env bash
# Shared helpers for training/pipelines/*/run.sh (sourced, not executed directly).
# Default: POST to TRAINER_BASE_URL (AERL; see training/pipelines/registry.yaml service.url).
# Override: PIPELINE_MODE=local and AERL_ROOT for in-repo AERL reference python entrypoints.

set -euo pipefail

_training_caller_script() {
  echo "${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}"
}

training_skill_root() {
  # Caller is training/pipelines/<id>/run.sh → three levels up to skill root.
  cd "$(dirname "$(_training_caller_script)")/../../.." && pwd
}

training_load_env() {
  local root
  root="$(training_skill_root)"
  if [[ -f "${root}/training/services/.env" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${root}/training/services/.env"
    set +a
  fi
  : "${TRAINER_BASE_URL:=http://localhost:8004}"
}

_training_json_argv() {
  command -v python3 >/dev/null 2>&1 || {
    echo "training_http_run requires python3 to JSON-encode argv" >&2
    return 1
  }
  python3 -c 'import json,sys; print(json.dumps({"argv": sys.argv[1:]}))' "$@"
}

training_http_run() {
  local pipeline_id="$1"
  local log_file="$2"
  shift 2
  training_load_env
  local base="${TRAINER_BASE_URL%/}"
  local url="${base}/v1/pipelines/${pipeline_id}/run"
  local auth_header=()
  if [[ -n "${TRAINER_API_KEY:-}" ]]; then
    auth_header=(-H "Authorization: Bearer ${TRAINER_API_KEY}")
  elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
    auth_header=(-H "Authorization: Bearer ${OPENAI_API_KEY}")
  fi
  mkdir -p "$(dirname "${log_file}")"
  # Contract: trainer returns training log / stream as response body (text ok).
  curl -fsS "${auth_header[@]}" -X POST "${url}" \
    -H "Content-Type: application/json" \
    -d "$(_training_json_argv "$@")" >"${log_file}" 2>&1
}

training_local_aerl_run() {
  local log_file="$1"
  shift
  : "${AERL_ROOT:?PIPELINE_MODE=local requires AERL_ROOT (path to an AERL trainer source tree)}"
  mkdir -p "$(dirname "${log_file}")"
  (
    cd "${AERL_ROOT}"
    "$@"
  ) >"${log_file}" 2>&1
}
