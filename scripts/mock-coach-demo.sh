#!/usr/bin/env bash
# Phase 4 coach demo: full mock stack, two supervised agents, drop loop, promote vs reject.
#
# Usage:
#   bash scripts/mock-coach-demo.sh
#
# Exits non-zero if promote/reject outcomes do not match expectations.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_DIR="${ROOT}/mock-services/ci-coach-demo"
REGISTRY="${ROOT}/modes/coach/agents.demo.json"

AE_PORT="${MOCK_AGENTEVALS_PORT:-18080}"
LEARNING_PORT="${MOCK_SELF_LEARNING_PORT:-18766}"
SQ_PORT="${MOCK_SELF_QUESTIONING_PORT:-18767}"
AERL_PORT="${MOCK_AERL_PORT:-18004}"
COACHING_PORT="${MOCK_COACHING_PORT:-18765}"

AGENTEVALS_URL="http://127.0.0.1:${AE_PORT}"
LEARNING_URL="http://127.0.0.1:${LEARNING_PORT}"
SQ_URL="http://127.0.0.1:${SQ_PORT}"
AERL_URL="http://127.0.0.1:${AERL_PORT}"
COACHING_URL="http://127.0.0.1:${COACHING_PORT}"

cleanup() {
  for pid in "${PID_AE:-}" "${PID_LEARNING:-}" "${PID_SQ:-}" "${PID_AERL:-}" "${PID_COACHING:-}"; do
    kill "${pid}" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

wait_for_health() {
  local url="$1"
  local label="$2"
  for _ in $(seq 1 40); do
    if curl -fsS "${url}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  echo "mock-coach-demo: ${label} did not become healthy at ${url}" >&2
  return 1
}

echo "==> Prepare coach demo data at ${DEMO_DIR}"
rm -rf "${DEMO_DIR}"
mkdir -p "${DEMO_DIR}/runs"

python "${ROOT}/mock-services/mock_agentevals.py" init --data-dir "${DEMO_DIR}" --agent-id agent-promote
python "${ROOT}/mock-services/mock_agent_registry.py" init --data-dir "${DEMO_DIR}" --agent-id agent-reject

for agent in agent-promote agent-reject; do
  mkdir -p "${DEMO_DIR}/agents/${agent}/experience"
  python "${ROOT}/mock-services/mock_self_coaching.py" init --root "${DEMO_DIR}/agents/${agent}"
done

echo "==> Start mock platform stack"
python "${ROOT}/mock-services/mock_agentevals.py" serve \
  --data-dir "${DEMO_DIR}" --host 127.0.0.1 --port "${AE_PORT}" &
PID_AE=$!
python "${ROOT}/mock-services/mock_self_learning.py" serve \
  --data-dir "${DEMO_DIR}" --host 127.0.0.1 --port "${LEARNING_PORT}" &
PID_LEARNING=$!
export MOCK_AGENTEVALS_URL="${AGENTEVALS_URL}"
python "${ROOT}/mock-services/mock_self_questioning.py" serve \
  --data-dir "${DEMO_DIR}" --host 127.0.0.1 --port "${SQ_PORT}" &
PID_SQ=$!
python "${ROOT}/mock-services/mock_aerl.py" serve \
  --data-dir "${DEMO_DIR}" --host 127.0.0.1 --port "${AERL_PORT}" &
PID_AERL=$!
export MOCK_AGENTEVALS_URL="${AGENTEVALS_URL}"
export MOCK_SELF_LEARNING_URL="${LEARNING_URL}"
export MOCK_SELF_QUESTIONING_URL="${SQ_URL}"
export MOCK_AERL_URL="${AERL_URL}"
export TRAINER_BASE_URL="${AERL_URL}"
python "${ROOT}/mock-services/mock_self_coaching.py" serve \
  --root "${DEMO_DIR}" --host 127.0.0.1 --port "${COACHING_PORT}" &
PID_COACHING=$!

wait_for_health "${AGENTEVALS_URL}" "AgentEvals"
wait_for_health "${LEARNING_URL}" "Self-Learning"
wait_for_health "${SQ_URL}" "Self-Questioning"
wait_for_health "${AERL_URL}" "AERL"
wait_for_health "${COACHING_URL}" "Coaching API"

export ORCHESTRATOR_EVAL_BACKEND=agentevals
export ORCHESTRATOR_TRAIN_BACKEND=aerl
# Module transport: each agent has its own coaching_root (HTTP gateway is single-root).
export ORCHESTRATOR_TRANSPORT=module
export AGENTEVALS_BASE_URL="${AGENTEVALS_URL}"
export MOCK_AGENTEVALS_URL="${AGENTEVALS_URL}"
export MOCK_SELF_LEARNING_URL="${LEARNING_URL}"
export MOCK_SELF_QUESTIONING_URL="${SQ_URL}"
export MOCK_AERL_URL="${AERL_URL}"
export TRAINER_BASE_URL="${AERL_URL}"
export AGENTEVALS_SUITE_ID=tool-use-canary
export AGENTEVALS_SUITE_ID_HOLDOUT=tool-use-holdout
export ORCHESTRATOR_MIN_CASES_FOR_MODEL=2
export ORCHESTRATOR_SELF_QUESTIONING_N=4

run_agent_demo() {
  local agent_id="$1"
  local coaching_root="$2"
  local production_candidate="$3"
  local expected="$4"

  echo ""
  echo "==> Coach loop: ${agent_id} (expect ${expected})"
  export AGENT_ID="${agent_id}"

  python -m services.orchestrator record-eval \
    --coaching-root "${coaching_root}" \
    --agent-id "${agent_id}" \
    --candidate "mock-bad-regress" \
    --baseline "mock-baseline-v0" \
    --baseline-score 0.95 \
    --split canary >/dev/null

  set +e
  python -m services.orchestrator check-drop \
    --metrics-dir "${coaching_root}/.self-coaching/metrics" \
    --agent-id "${agent_id}" >/dev/null
  local drop_code=$?
  set -e
  if [[ "${drop_code}" -eq 0 ]]; then
    echo "mock-coach-demo: expected drop for ${agent_id}, check-drop exited 0" >&2
    exit 1
  fi

  local run_dir="${DEMO_DIR}/runs/${agent_id}"
  rm -rf "${run_dir}"
  python -m services.orchestrator run \
    --coaching-root "${coaching_root}" \
    --run-dir "${run_dir}" \
    --agent-id "${agent_id}" \
    --production-candidate "${production_candidate}" \
    --production-baseline "mock-baseline-v0" \
    --pipeline sft

  local decision_file="${run_dir}/decision.json"
  local decision improvement_path
  decision="$(python -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8'))['recommendation'])" "${decision_file}")"
  improvement_path="$(python -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8'))['improvement_path'])" "${decision_file}")"

  if [[ "${decision}" != "${expected}" ]]; then
    echo "mock-coach-demo: ${agent_id} expected ${expected}, got ${decision}" >&2
    exit 1
  fi
  if [[ "${improvement_path}" != "model" ]]; then
    echo "mock-coach-demo: ${agent_id} expected model path, got ${improvement_path}" >&2
    exit 1
  fi
  if [[ ! -f "${run_dir}/training.json" ]]; then
    echo "mock-coach-demo: missing training.json for ${agent_id}" >&2
    exit 1
  fi

  DEMO_DIR="${DEMO_DIR}" RUN_DIR="${run_dir}" AGENT_ID="${agent_id}" ROOT="${ROOT}" python - <<'PY'
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.environ["ROOT"], "mock-services"))
from mock_agent_registry import AgentRegistry

run_dir = Path(os.environ["RUN_DIR"])
decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
training = json.loads((run_dir / "training.json").read_text(encoding="utf-8"))
registry = AgentRegistry(os.environ["DEMO_DIR"])
agent_id = os.environ["AGENT_ID"]
version_id = training.get("registry_version_id")
if decision["recommendation"] == "promote" and version_id:
    registry.activate(agent_id, version_id)
    active = registry.get_agent(agent_id)
    model_id = active["version"]["components"]["model_id"]
    if "candidate" not in model_id:
        raise SystemExit(f"promoted model_id missing candidate marker: {model_id}")
    print(f"promoted {agent_id} -> {version_id} ({model_id})")
elif decision["recommendation"] == "reject" and version_id:
    active = registry.get_agent(agent_id)
    if active["active_version_id"] == version_id:
        raise SystemExit(f"reject path must not activate draft {version_id}")
    print(f"rejected {agent_id}; draft {version_id} left inactive")
PY

  echo "ok: ${agent_id} -> ${decision}"
}

cd "${ROOT}"

run_agent_demo \
  "agent-promote" \
  "${DEMO_DIR}/agents/agent-promote" \
  "mock-bad-production" \
  "promote"

run_agent_demo \
  "agent-reject" \
  "${DEMO_DIR}/agents/agent-reject" \
  "mock-baseline-v0" \
  "reject"

python -c "
import sys
sys.path.insert(0, sys.argv[1])
from modes.coach.registry import load_registry
agents = load_registry(sys.argv[2])
assert len(agents) == 2
assert {a.id for a in agents} == {'agent-promote', 'agent-reject'}
print('registry: ok', [a.id for a in agents])
" "${ROOT}" "${REGISTRY}"

echo ""
echo "mock-coach-demo: OK (two agents, drop loop, promote + reject)"
