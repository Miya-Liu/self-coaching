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
echo "mock-self-learning-smoke: OK"
