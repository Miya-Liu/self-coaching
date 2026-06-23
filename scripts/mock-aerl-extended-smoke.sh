# ⚠️ ON-HOLD: AERL services not yet deployed
# This module depends on the AERL training platform which is not available
# in the current deployment. Kept for future integration when AERL is live.
# Status: ON-HOLD — do not remove, do not invest further until AERL deploys.

#!/usr/bin/env bash
# Extended smoke: production-shaped mock AERL routes (M4.1 Slice 1–2).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT}/mock-services/ci-mock-aerl-extended"
FIXTURES="${ROOT}/tests/fixtures/aerl"
PORT=18005

rm -rf "${DATA_DIR}"
mkdir -p "${DATA_DIR}"

python "${ROOT}/mock-services/mock_agentevals.py" init --data-dir "${DATA_DIR}" --agent-id smoke-agent

python "${ROOT}/mock-services/mock_aerl.py" serve \
  --data-dir "${DATA_DIR}" --host 127.0.0.1 --port "${PORT}" &
PID=$!
trap 'kill "${PID}" 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

curl -fsS "http://127.0.0.1:${PORT}/health" | grep -q '"gpu_available": true'
curl -fsS "http://127.0.0.1:${PORT}/v1/pipelines" | grep -q '"id": "grpo"'
curl -fsS "http://127.0.0.1:${PORT}/v1/rewards/schema" | grep -q 'reward.ic.v1'
curl -fsS "http://127.0.0.1:${PORT}/v1/processes" | grep -q '"processes": \[\]'

curl -fsS -X POST "http://127.0.0.1:${PORT}/v1/rollout/configs/validate" \
  -H "Content-Type: application/json" \
  -d @"${FIXTURES}/rollout_validate_ok.json" | grep -q '"valid": true'

curl -fsS -X POST "http://127.0.0.1:${PORT}/v1/rewards/validate" \
  -H "Content-Type: application/json" \
  -d "{\"dataset_refs\":[\"${FIXTURES}/reward_sft.jsonl\"],\"reward_spec\":{\"schema_version\":\"reward.ic.v1\"}}" \
  | grep -q '"valid": true'

# GRPO without rollout must fail
code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:${PORT}/v1/training/runs" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id":"grpo","base_model":"mock-base"}')"
test "${code}" = "400"

# SFT run with snapshot
CREATE="$(curl -fsS -X POST "http://127.0.0.1:${PORT}/v1/training/runs" \
  -H "Content-Type: application/json" \
  -d "{\"pipeline_id\":\"sft\",\"base_model\":\"mock-base-v1\",\"agent_id\":\"smoke-agent\",\"coaching_root\":\"${DATA_DIR}\",\"agent_snapshot\":{\"skill_bundle_version\":\"skills-smoke\"}}")"
RUN_ID="$(python -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"${CREATE}")"

for _ in $(seq 1 50); do
  STATUS="$(curl -fsS "http://127.0.0.1:${PORT}/v1/training/runs/${RUN_ID}" | python -c "import json,sys; print(json.load(sys.stdin).get('status',''))")"
  if [ "${STATUS}" = "succeeded" ]; then
    break
  fi
  sleep 0.05
done
test "${STATUS}" = "succeeded"

curl -fsS "http://127.0.0.1:${PORT}/v1/training/runs/${RUN_ID}/metrics" | grep -q 'train_loss'
curl -fsS "http://127.0.0.1:${PORT}/v1/checkpoints?training_run_id=${RUN_ID}" | grep -q '"status": "available"'

CKPT_ID="$(curl -fsS "http://127.0.0.1:${PORT}/v1/training/runs/${RUN_ID}" \
  | python -c "import json,sys; print(json.load(sys.stdin)['primary_checkpoint_id'])")"
CKPT_DETAIL="$(curl -fsS "http://127.0.0.1:${PORT}/v1/checkpoints/${CKPT_ID}")"
echo "${CKPT_DETAIL}" | grep -q 'mock://'
echo "${CKPT_DETAIL}" | grep -q '"adapter_only": true'

test -f "${DATA_DIR}/.self-coaching/manifests/training_run_manifest.json"

echo "mock-aerl-extended-smoke: OK"
