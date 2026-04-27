#!/usr/bin/env bash
# Hook: print the standard training bash pattern (log to file). Safe for context size.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPERIMENT_ID="${EXPERIMENT_ID:-run-01}"
WT="${EXPERIMENT_WORKTREE:-$ROOT/worktrees/${EXPERIMENT_ID}}"
LOG="${EXPERIMENT_LOG_FILE:-$ROOT/logs/${EXPERIMENT_ID}.log}"

cat <<EOF
[self-coaching / experiment command — run in Bash, not in chat]
Experiment worktree (edits only here): ${WT}
Full training output MUST go to a file (never paste full logs into context):
  mkdir -p "${ROOT}/logs"
  ( cd "${WT}" && uv run train.py ) > "${LOG}" 2>&1
Then Read "${LOG}" in small sections to parse val_bpb / peak_vram_mb.
Set EXPERIMENT_ID / EXPERIMENT_WORKTREE / EXPERIMENT_LOG_FILE to override defaults.
EOF
