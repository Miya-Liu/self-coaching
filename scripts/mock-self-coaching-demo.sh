#!/usr/bin/env bash
# Self-coaching loop demo — one command, deterministic mocks, completeness PASS.
#
# Usage:
#   bash scripts/mock-self-coaching-demo.sh            # module transport (default, fastest)
#   bash scripts/mock-self-coaching-demo.sh --with-http  # split mock stack on high ports
#
# Exits 0 when loop + completeness audit (C01–C18) PASS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_DIR="${ROOT}/mock-services/demo-loop"
SCENARIO="${ROOT}/scenarios/full_loop.json"
WITH_HTTP=0

for arg in "$@"; do
  case "${arg}" in
    --with-http) WITH_HTTP=1 ;;
    --help|-h)
      sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
  esac
done

AE_PORT="${MOCK_AGENTEVALS_PORT:-38180}"
LEARNING_PORT="${MOCK_SELF_LEARNING_PORT:-38766}"
SELF_PLAY_PORT="${MOCK_SELF_PLAY_PORT:-38767}"
AERL_PORT="${MOCK_AERL_PORT:-38004}"

AGENTEVALS_URL="http://127.0.0.1:${AE_PORT}"
LEARNING_URL="http://127.0.0.1:${LEARNING_PORT}"
SELF_PLAY_URL="http://127.0.0.1:${SELF_PLAY_PORT}"
AERL_URL="http://127.0.0.1:${AERL_PORT}"

cleanup() {
  for pid in "${PID_AE:-}" "${PID_LEARNING:-}" "${PID_SELF_PLAY:-}" "${PID_AERL:-}"; do
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
  echo "mock-self-coaching-demo: ${label} not healthy at ${url}" >&2
  return 1
}

echo "==> Prepare demo coaching root at ${DEMO_DIR}"
rm -rf "${DEMO_DIR}"
mkdir -p "${DEMO_DIR}"

export AGENT_ID="${LOOP_AGENT_ID:-demo-agent}"
export LOOP_AGENT_ID="${AGENT_ID}"
export LOOP_SIGMA_MIN="${LOOP_SIGMA_MIN:-3}"
export LOOP_SIGMA_PLAY="${LOOP_SIGMA_PLAY:-0}"
export LOOP_BATCH_SIZE="${LOOP_BATCH_SIZE:-4}"
export LOOP_TAU_FAIL="${LOOP_TAU_FAIL:-0.75}"
export LOOP_IDLE_AFTER="${LOOP_IDLE_AFTER:-0}"

if [[ "${WITH_HTTP}" -eq 1 ]]; then
  echo "==> Start split mock stack (--with-http)"
  python "${ROOT}/mock-services/mock_agentevals.py" init \
    --data-dir "${DEMO_DIR}" --agent-id "${AGENT_ID}"

  python "${ROOT}/mock-services/mock_agentevals.py" serve \
    --data-dir "${DEMO_DIR}" --host 127.0.0.1 --port "${AE_PORT}" &
  PID_AE=$!
  python "${ROOT}/mock-services/mock_self_learning.py" serve \
    --data-dir "${DEMO_DIR}" --host 127.0.0.1 --port "${LEARNING_PORT}" &
  PID_LEARNING=$!
  MOCK_AGENTEVALS_URL="${AGENTEVALS_URL}" python "${ROOT}/mock-services/mock_self_play.py" serve \
    --data-dir "${DEMO_DIR}" --host 127.0.0.1 --port "${SELF_PLAY_PORT}" &
  PID_SELF_PLAY=$!
  python "${ROOT}/mock-services/mock_aerl.py" serve \
    --data-dir "${DEMO_DIR}" --host 127.0.0.1 --port "${AERL_PORT}" &
  PID_AERL=$!

  wait_for_health "${AGENTEVALS_URL}" "AgentEvals"
  wait_for_health "${LEARNING_URL}" "Self-Learning"
  wait_for_health "${SELF_PLAY_URL}" "Self-Play"
  wait_for_health "${AERL_URL}" "AERL"

  export MOCK_SELF_LEARNING_URL="${LEARNING_URL}"
  export MOCK_SELF_PLAY_URL="${SELF_PLAY_URL}"
  export MOCK_AERL_URL="${AERL_URL}"
  export TRAINER_BASE_URL="${AERL_URL}"
else
  echo "==> Module transport (in-process mocks)"
  unset MOCK_SELF_LEARNING_URL MOCK_SELF_PLAY_URL MOCK_AERL_URL MOCK_AGENTEVALS_URL AGENTEVALS_BASE_URL
fi

echo "==> Run self-coaching loop (scenarios/full_loop.json)"
python "${ROOT}/mock-services/self_coaching_loop.py" run \
  --root "${DEMO_DIR}" \
  --scenario "${SCENARIO}"

for artifact in \
  "${DEMO_DIR}/.self-coaching/loop/state.json" \
  "${DEMO_DIR}/.self-coaching/loop/support.jsonl" \
  "${DEMO_DIR}/.self-coaching/loop/tuning_buffer.jsonl" \
  "${DEMO_DIR}/.self-coaching/loop/demo_summary.md" \
  "${DEMO_DIR}/agents/demo-agent/meta.json"
do
  if [[ ! -f "${artifact}" ]]; then
    echo "mock-self-coaching-demo: missing artifact ${artifact}" >&2
    exit 1
  fi
done

echo "==> Completeness audit (C01–C18)"
REPORT_JSON="${DEMO_DIR}/.self-coaching/loop/completeness_report.json"
python "${ROOT}/tools/loop_completeness.py" \
  --root "${DEMO_DIR}" \
  --expect-json "${SCENARIO}" \
  --json > "${REPORT_JSON}.stdout"

python -c "
import json, sys
report = json.load(open(sys.argv[1], encoding='utf-8'))
status = report.get('status')
print(f'completeness: {status}')
if status != 'PASS':
    for item in report.get('failures', []):
        print(f'  FAIL: {item}', file=sys.stderr)
    sys.exit(1)
" "${REPORT_JSON}"

GEN_BEFORE="$(python -c "import json; print(json.load(open('${DEMO_DIR}/.self-coaching/loop/state.json'))['generation'])")"
echo "generation: ${GEN_BEFORE}"
echo "registry versions: $(find "${DEMO_DIR}/agents/demo-agent/versions" -name '*.json' | wc -l | tr -d ' ')"
echo "mock-self-coaching-demo: PASS"