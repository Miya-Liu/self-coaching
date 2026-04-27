#!/usr/bin/env bash
# Hook: inject recent optimization learnings (for stagnation / no improvement).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="${SKILL_LEARNINGS_FILE:-${ROOT}/experience/LEARNINGS.md}"
LINES="${LEARNINGS_TAIL_LINES:-100}"

if [ ! -f "${FILE}" ]; then
  echo "[self-coaching] No file at ${FILE}"
  exit 0
fi

echo "[self-coaching / recent learnings from ${FILE} — last ${LINES} lines]"
echo "---"
tail -n "${LINES}" "${FILE}" || true
