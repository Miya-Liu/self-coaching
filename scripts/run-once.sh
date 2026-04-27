#!/usr/bin/env bash
# Run one training experiment from an experiment worktree; all output to a log file.
# Usage: bash scripts/run-once.sh <worktree-path> [log-file]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WT="${1:?usage: run-once.sh <path-to-experiment-worktree> [log-file]}"
LOG="${2:-${ROOT}/logs/$(basename "${WT}").log}"

mkdir -p "$(dirname "${LOG}")"
( cd "${WT}" && uv run train.py ) > "${LOG}" 2>&1
echo "Finished. Log: ${LOG}"
