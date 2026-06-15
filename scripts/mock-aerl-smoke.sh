#!/usr/bin/env bash
# Smoke test mock AERL (in-process + HTTP argv endpoint).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT}/mock-services/ci-mock-aerl"
rm -rf "${DATA_DIR}"
mkdir -p "${DATA_DIR}"

python "${ROOT}/mock-services/mock_agentevals.py" init --data-dir "${DATA_DIR}" --agent-id smoke-agent

python "${ROOT}/mock-services/mock_aerl.py" run \
  --data-dir "${DATA_DIR}" \
  --pipeline sft \
  --base-model mock-base-v1 \
  --agent-id smoke-agent \
  --coaching-root "${DATA_DIR}"

test -f "${DATA_DIR}/.self-coaching/manifests/training_run_manifest.json"
manifest="${DATA_DIR}/.self-coaching/manifests/training_run_manifest.json"
python -c "import json,sys; m=json.load(open(sys.argv[1])); assert m.get('candidate_model_id')" "${manifest}"
test -f "${DATA_DIR}/aerl/logs/train-"*.log

PORT=18004
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

LOG="${DATA_DIR}/pipeline-smoke.log"
curl -fsS -X POST "http://127.0.0.1:${PORT}/v1/pipelines/sft/run" \
  -H "Content-Type: application/json" \
  -d '{"argv":["--dry-run","--epochs","1"]}' >"${LOG}"
grep -q "metric.val_loss" "${LOG}"

curl -fsS -X POST "http://127.0.0.1:${PORT}/v1/training/runs" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id":"sft","base_model":"mock-base-v1","agent_id":"smoke-agent","coaching_root":"'"${DATA_DIR}"'","agent_snapshot":{"skill_bundle_version":"skills-smoke"}}' \
  | grep -q '"status": "queued"'

echo "mock-aerl-smoke: OK"
