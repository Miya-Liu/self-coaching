#!/usr/bin/env bash
# Run the evolution engine (T3) from repo root. See docs/design/pipelines.md.
# Usage:
#   bash scripts/run-orchestrator.sh record-eval [coaching-root]
#   bash scripts/run-orchestrator.sh check-drop [coaching-root]
#   bash scripts/run-orchestrator.sh run [coaching-root] [run-dir]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COACHING_ROOT="${2:-${ROOT}/mock-services/demo-run}"
CMD="${1:-run}"

case "${CMD}" in
  record-eval)
    exec python -m services.orchestrator record-eval \
      --coaching-root "${COACHING_ROOT}" \
      --agent-id "${AGENT_ID:-demo-agent}" \
      --candidate "${CANDIDATE:-mock-candidate-v1}" \
      --baseline "${BASELINE:-mock-baseline-v0}" \
      ${BASELINE_SCORE:+--baseline-score "${BASELINE_SCORE}"}
    ;;
  check-drop)
    METRICS="${COACHING_ROOT}/.self-coaching/metrics"
    exec python -m services.orchestrator check-drop --metrics-dir "${METRICS}" --agent-id "${AGENT_ID:-demo-agent}"
    ;;
  run)
    RUN_DIR="${3:-${ROOT}/runs/improvement-$(date +%Y%m%d-%H%M%S)}"
    exec python -m services.orchestrator run \
      --coaching-root "${COACHING_ROOT}" \
      --run-dir "${RUN_DIR}" \
      --agent-id "${AGENT_ID:-demo-agent}" \
      --force-trigger
    ;;
  *)
    echo "usage: $0 {record-eval|check-drop|run} [coaching-root] [run-dir]" >&2
    exit 2
    ;;
esac
