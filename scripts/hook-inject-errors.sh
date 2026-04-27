#!/usr/bin/env bash
# Hook: inject recent error log (similar failures / context for debugging).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="${SKILL_ERROR_FILE:-${ROOT}/experience/ERROR.md}"
LINES="${ERROR_TAIL_LINES:-100}"

if [ ! -f "${FILE}" ]; then
  echo "[self-coaching] No file at ${FILE}"
  exit 0
fi

echo "[self-coaching / recent errors from ${FILE} — last ${LINES} lines]"
echo "---"
tail -n "${LINES}" "${FILE}" || true
