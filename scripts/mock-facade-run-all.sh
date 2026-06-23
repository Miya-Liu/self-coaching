#!/usr/bin/env bash
# Facade run-all: monolithic entrypoint delegating to split mock stack via MOCK_*_URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT}/mock-services/ci-facade-run-all"
rm -rf "${DATA_DIR}"
mkdir -p "${DATA_DIR}"

AE_PORT="${MOCK_AGENTEVALS_PORT:-28180}"
LEARNING_PORT="${MOCK_SELF_LEARNING_PORT:-28766}"
SQ_PORT="${MOCK_SELF_QUESTIONING_PORT:-28767}"
AERL_PORT="${MOCK_AERL_PORT:-28004}"

AGENTEVALS_URL="http://127.0.0.1:${AE_PORT}"
LEARNING_URL="http://127.0.0.1:${LEARNING_PORT}"
SQ_URL="http://127.0.0.1:${SQ_PORT}"
AERL_URL="http://127.0.0.1:${AERL_PORT}"

cleanup() {
  for pid in "${PID_AE:-}" "${PID_LEARNING:-}" "${PID_SQ:-}" "${PID_AERL:-}"; do
    kill "${pid}" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

wait_for_health() {
  local url="$1"
  for _ in $(seq 1 40); do
    if curl -fsS "${url}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  echo "mock-facade-run-all: service not healthy at ${url}" >&2
  return 1
}

python "${ROOT}/mock-services/mock_agentevals.py" init --data-dir "${DATA_DIR}" --agent-id facade-agent

python "${ROOT}/mock-services/mock_agentevals.py" serve \
  --data-dir "${DATA_DIR}" --host 127.0.0.1 --port "${AE_PORT}" &
PID_AE=$!
python "${ROOT}/mock-services/mock_self_learning.py" serve \
  --data-dir "${DATA_DIR}" --host 127.0.0.1 --port "${LEARNING_PORT}" &
PID_LEARNING=$!
MOCK_AGENTEVALS_URL="${AGENTEVALS_URL}" python "${ROOT}/mock-services/mock_self_questioning.py" serve \
  --data-dir "${DATA_DIR}" --host 127.0.0.1 --port "${SQ_PORT}" &
PID_SQ=$!
python "${ROOT}/mock-services/mock_aerl.py" serve \
  --data-dir "${DATA_DIR}" --host 127.0.0.1 --port "${AERL_PORT}" &
PID_AERL=$!

wait_for_health "${AGENTEVALS_URL}"
wait_for_health "${LEARNING_URL}"
wait_for_health "${SQ_URL}"
wait_for_health "${AERL_URL}"

# Evaluate stays in-process (AgentEvals delegation changes pass/fail gates for run-all).
unset MOCK_AGENTEVALS_URL AGENTEVALS_BASE_URL
export MOCK_SELF_LEARNING_URL="${LEARNING_URL}"
export MOCK_SELF_QUESTIONING_URL="${SQ_URL}"
export MOCK_AERL_URL="${AERL_URL}"
export TRAINER_BASE_URL="${AERL_URL}"
export AGENT_ID=facade-agent

python "${ROOT}/mock-services/mock_self_coaching.py" run-all \
  --root "${DATA_DIR}" \
  --capability tool_use \
  --pipeline sft

test -f "${DATA_DIR}/.self-coaching/manifests/mock_pipeline_summary.json"
test -f "${DATA_DIR}/.self-coaching/curated/validation.jsonl"
test -f "${DATA_DIR}/.self-coaching/curated/holdout.jsonl"
test -s "${DATA_DIR}/.self-coaching/curated/holdout.jsonl"

python -c "
import json, sys
summary = json.load(open(sys.argv[1], encoding='utf-8'))
assert summary.get('status') == 'ok', summary
assert summary.get('promotion_allowed') is True, summary
assert '_eval_backend' not in (summary.get('baseline_eval') or {}), summary
sp = summary.get('self_questioning') or {}
assert sp.get('suite_id'), 'expected AgentEvals suite_id from delegated self-questioning'
tr = summary.get('training') or {}
assert tr.get('_train_backend') == 'aerl' or 'candidate' in tr, tr
print('facade run-all ok suite_id=', sp.get('suite_id'))
" "${DATA_DIR}/.self-coaching/manifests/mock_pipeline_summary.json"

echo "mock-facade-run-all: OK"
