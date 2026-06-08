#!/usr/bin/env bash
# Smoke test mock self-play (in-process).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT}/mock-services/ci-mock-self-play"
rm -rf "${DATA_DIR}"
mkdir -p "${DATA_DIR}"

python "${ROOT}/mock-services/mock_agentevals.py" init --data-dir "${DATA_DIR}" --agent-id smoke-agent

python "${ROOT}/mock-services/mock_self_play.py" generate-suite \
  --data-dir "${DATA_DIR}" \
  --agent-id smoke-agent \
  --query "Create config.yaml and prove validation" \
  --score 0.3 \
  --mode adversarial

test -f "${DATA_DIR}/.self-coaching/curated/train.jsonl"
test -f "${DATA_DIR}/.self-coaching/curated/validation.jsonl"
test -f "${DATA_DIR}/.self-coaching/curated/holdout.jsonl"
test -f "${DATA_DIR}/.self-coaching/cases/self_play_candidates.jsonl"
echo "mock-self-play-smoke: OK"
