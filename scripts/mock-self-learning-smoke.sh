#!/usr/bin/env bash
# Smoke test mock self-learning (in-process).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT}/mock-services/ci-mock-self-learning"
rm -rf "${DATA_DIR}"
mkdir -p "${DATA_DIR}"

python "${ROOT}/mock-services/mock_self_learning.py" record \
  --data-dir "${DATA_DIR}" \
  --agent-id smoke-agent \
  --event "Skill patch: require verification before claiming success" \
  --classification skill_patch

python "${ROOT}/mock-services/mock_self_learning.py" record \
  --data-dir "${DATA_DIR}" \
  --agent-id smoke-agent \
  --event "Agent forgot to verify file write" \
  --classification eval_case_candidate

test -f "${DATA_DIR}/.self-coaching/skills/patches/"*.md
test -f "${DATA_DIR}/.self-coaching/events/learning_events.jsonl"

python "${ROOT}/mock-services/mock_self_learning.py" evolve \
  --data-dir "${DATA_DIR}" \
  --agent-id smoke-agent \
  --session-id sess_smoke_001

PORT=18766
python "${ROOT}/mock-services/mock_self_learning.py" serve \
  --data-dir "${DATA_DIR}" --host 127.0.0.1 --port "${PORT}" &
PID=$!
trap 'kill "${PID}" 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/learning/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

curl -fsS -X POST "http://127.0.0.1:${PORT}/learning/evolve" \
  -H "Content-Type: application/json" \
  -d '{"session_ids":["sess_smoke_002"],"wait":true,"coaching_root":"'"${DATA_DIR}"'"}' \
  | grep -q '"status": "completed"'

curl -fsS -X POST "http://127.0.0.1:${PORT}/learning/evolve/recent" \
  -H "Content-Type: application/json" \
  -d '{"hours":24,"max_sessions":1,"wait":false,"coaching_root":"'"${DATA_DIR}"'"}' \
  | grep -q '"status": "queued"'

echo "mock-self-learning-smoke: OK"
