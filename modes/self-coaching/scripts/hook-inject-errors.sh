#!/usr/bin/env bash
# hook-inject-errors.sh — print a bounded tail of experience/ERROR.md.
#
# Used by the self-coaching/self-learning skill to inject prior incident
# context into an agent's prompt without flooding it. Reads from
# ./experience/ERROR.md by default; override with $ERROR_LOG_PATH.
# Tail length controlled by $ERROR_TAIL_LINES (default 120).
#
# Exit codes:
#   0 — printed (file present) or printed nothing (file absent)
#   2 — bad config

set -euo pipefail

PATH_LOG="${ERROR_LOG_PATH:-experience/ERROR.md}"
LINES="${ERROR_TAIL_LINES:-120}"

if ! [[ "$LINES" =~ ^[0-9]+$ ]]; then
  echo "hook-inject-errors: ERROR_TAIL_LINES must be an integer (got: $LINES)" >&2
  exit 2
fi

if [[ ! -f "$PATH_LOG" ]]; then
  # Silent no-op when no log exists — caller can chain safely.
  exit 0
fi

echo "----- BEGIN $PATH_LOG (last $LINES lines) -----"
tail -n "$LINES" "$PATH_LOG"
echo "----- END $PATH_LOG -----"
