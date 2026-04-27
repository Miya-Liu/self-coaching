#!/usr/bin/env bash
# Ensure Experience log files exist under experience/ (do not overwrite).
set -euo pipefail

ROOT="${1:-.}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="${SCRIPT_DIR}/../experience"
DEST="${ROOT}/experience"

mkdir -p "${DEST}" "${ROOT}/logs" "${ROOT}/worktrees"

for f in EXPERIMENT_LOG.md ERROR.md LEARNINGS.md; do
  if [ ! -f "${DEST}/${f}" ] && [ -f "${TEMPLATE_DIR}/${f}" ]; then
    cp "${TEMPLATE_DIR}/${f}" "${DEST}/${f}"
  fi
done

echo "Initialized Experience at ${DEST} and ${ROOT}/logs, ${ROOT}/worktrees (existing files preserved)."
