#!/usr/bin/env bash
# Run one training experiment from an experiment worktree; all output to a log file.
# Usage: bash scripts/run-once.sh <worktree-path> [log-file]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WT="${1:?usage: run-once.sh <path-to-experiment-worktree> [log-file]}"
LOG="${2:-${ROOT}/logs/$(basename "${WT}").log}"

mkdir -p "$(dirname "${LOG}")"
if command -v uv >/dev/null 2>&1; then
  ( cd "${WT}" && uv run train.py ) > "${LOG}" 2>&1
elif [[ -f "${WT}/train.py" ]] && command -v python >/dev/null 2>&1; then
  ( cd "${WT}" && python train.py ) > "${LOG}" 2>&1
else
  echo "run-once.sh: need 'uv' (recommended) or python + train.py in worktree" >&2
  echo "  Install uv: https://docs.astral.sh/uv/" >&2
  exit 1
fi
echo "Finished. Log: ${LOG}"
