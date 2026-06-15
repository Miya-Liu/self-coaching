#!/usr/bin/env bash
# hook-inject-learnings.sh — print a bounded tail of experience/LEARNINGS.md.
#
# Symmetric with hook-inject-errors.sh. Env vars:
#   LEARNINGS_LOG_PATH   default: experience/LEARNINGS.md
#   LEARNINGS_TAIL_LINES default: 120

set -euo pipefail

PATH_LOG="${LEARNINGS_LOG_PATH:-experience/LEARNINGS.md}"
LINES="${LEARNINGS_TAIL_LINES:-120}"

if ! [[ "$LINES" =~ ^[0-9]+$ ]]; then
  echo "hook-inject-learnings: LEARNINGS_TAIL_LINES must be an integer (got: $LINES)" >&2
  exit 2
fi

if [[ ! -f "$PATH_LOG" ]]; then
  exit 0
fi

echo "----- BEGIN $PATH_LOG (last $LINES lines) -----"
tail -n "$LINES" "$PATH_LOG"
echo "----- END $PATH_LOG -----"
