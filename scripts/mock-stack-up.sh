#!/usr/bin/env bash
# Start Phase 0 mock stack: AgentEvals (:8080) + optional Coaching API (:8765).
#
# Usage:
#   bash scripts/mock-stack-up.sh [data-dir] [--with-coaching] [--with-learning]
#
# Environment (for clients):
#   export AGENTEVALS_BASE_URL=http://127.0.0.1:8080
#   export ORCHESTRATOR_EVAL_BACKEND=agentevals
#   export AGENTEVALS_SUITE_ID=tool-use-canary
#   export AGENTEVALS_SUITE_ID_HOLDOUT=tool-use-holdout
#   export MOCK_AGENTEVALS_URL=http://127.0.0.1:8080
#   export AGENT_ID=example-agent
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT}/mock-services/demo-stack"
WITH_COACHING=0
WITH_LEARNING=0
AGENTEVALS_PORT="${MOCK_AGENTEVALS_PORT:-8080}"
COACHING_PORT="${MOCK_COACHING_PORT:-8765}"
LEARNING_PORT="${MOCK_SELF_LEARNING_PORT:-8766}"
AGENT_ID="${AGENT_ID:-example-agent}"

for arg in "$@"; do
  case "${arg}" in
    --with-coaching) WITH_COACHING=1 ;;
    --with-learning) WITH_LEARNING=1 ;;
    --help|-h)
      sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      if [[ "${arg}" != --* ]]; then
        DATA_DIR="$(cd "${arg}" && pwd)"
      fi
      ;;
  esac
done

mkdir -p "${DATA_DIR}"

echo "==> Init mock AgentEvals data at ${DATA_DIR}"
python "${ROOT}/mock-services/mock_agentevals.py" init --data-dir "${DATA_DIR}" --agent-id "${AGENT_ID}"

echo "==> Starting mock AgentEvals on :${AGENTEVALS_PORT}"
python "${ROOT}/mock-services/mock_agentevals.py" serve \
  --data-dir "${DATA_DIR}" --host 127.0.0.1 --port "${AGENTEVALS_PORT}" &
PID_AE=$!

cleanup() {
  kill "${PID_AE}" 2>/dev/null || true
  if [[ -n "${PID_LEARNING:-}" ]]; then
    kill "${PID_LEARNING}" 2>/dev/null || true
  fi
  if [[ -n "${PID_COACHING:-}" ]]; then
    kill "${PID_COACHING}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [[ "${WITH_LEARNING}" -eq 1 ]]; then
  echo "==> Starting mock Self-Learning on :${LEARNING_PORT}"
  python "${ROOT}/mock-services/mock_self_learning.py" serve \
    --data-dir "${DATA_DIR}" --host 127.0.0.1 --port "${LEARNING_PORT}" &
  PID_LEARNING=$!
fi

if [[ "${WITH_COACHING}" -eq 1 ]]; then
  echo "==> Starting mock Coaching API on :${COACHING_PORT}"
  export MOCK_AGENTEVALS_URL="http://127.0.0.1:${AGENTEVALS_PORT}"
  if [[ "${WITH_LEARNING}" -eq 1 ]]; then
    export MOCK_SELF_LEARNING_URL="http://127.0.0.1:${LEARNING_PORT}"
  fi
  python "${ROOT}/mock-services/mock_self_coaching.py" serve \
    --root "${DATA_DIR}" --host 127.0.0.1 --port "${COACHING_PORT}" &
  PID_COACHING=$!
fi

echo ""
echo "Mock stack running (Ctrl+C to stop)."
echo "  AgentEvals:     http://127.0.0.1:${AGENTEVALS_PORT}"
if [[ "${WITH_LEARNING}" -eq 1 ]]; then
  echo "  Self-Learning:  http://127.0.0.1:${LEARNING_PORT}"
fi
if [[ "${WITH_COACHING}" -eq 1 ]]; then
  echo "  Coaching:       http://127.0.0.1:${COACHING_PORT}"
fi
echo "  Data dir:    ${DATA_DIR}"
echo ""
echo "Example:"
echo "  export AGENTEVALS_BASE_URL=http://127.0.0.1:${AGENTEVALS_PORT}"
echo "  export ORCHESTRATOR_EVAL_BACKEND=agentevals"
echo "  export AGENTEVALS_SUITE_ID=tool-use-canary"
echo "  python -m services.orchestrator record-eval --coaching-root ${DATA_DIR} --agent-id ${AGENT_ID}"

wait "${PID_AE}"
