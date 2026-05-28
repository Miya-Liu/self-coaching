#!/usr/bin/env bash
# Install deps for the vendored upstream trainer (shared lock under upstream/autoresearch).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM="${ROOT}/upstream/autoresearch"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install from https://docs.astral.sh/uv/" >&2
  exit 1
fi

if [[ -n "${AERL_ROOT:-}" ]]; then
  if [[ ! -d "${AERL_ROOT}" || ! -f "${AERL_ROOT}/train.py" ]]; then
    echo "AERL_ROOT does not look like a trainer source tree (expected train.py): ${AERL_ROOT}" >&2
    exit 1
  fi
  echo "AERL_ROOT ok: ${AERL_ROOT}"
fi

echo "Syncing Python environment in ${UPSTREAM}..."
uv --directory "${UPSTREAM}" sync
echo "Done."
echo "If data/tokenizer cache is missing, run once: uv --directory \"${UPSTREAM}\" run prepare.py"
echo "Create a worktree (see SKILL.md), then: bash \"${ROOT}/scripts/run-once.sh\" <worktree-path> [log]"
echo "AERL HTTP pipelines: set TRAINER_BASE_URL in self-coaching-training/services/.env (default port 8004)."
