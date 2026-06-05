#!/usr/bin/env bash
# Install deps for an external autoresearch trainer clone (AUTORESEARCH_ROOT).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib-trainer-repo.sh
source "${ROOT}/scripts/lib-trainer-repo.sh"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install from https://docs.astral.sh/uv/" >&2
  exit 1
fi

if ! TRAINER_REPO="$(resolve_autoresearch_root "${ROOT}")"; then
  autoresearch_root_hint
  exit 1
fi

if [[ -n "${AERL_ROOT:-}" ]]; then
  if [[ ! -d "${AERL_ROOT}" || ! -f "${AERL_ROOT}/train.py" ]]; then
    echo "AERL_ROOT does not look like a trainer source tree (expected train.py): ${AERL_ROOT}" >&2
    exit 1
  fi
  echo "AERL_ROOT ok: ${AERL_ROOT}"
fi

echo "Syncing Python environment in ${TRAINER_REPO}..."
uv --directory "${TRAINER_REPO}" sync
echo "Done."
echo "If data/tokenizer cache is missing, run once:"
echo "  uv --directory \"${TRAINER_REPO}\" run prepare.py"
echo "Create a worktree (see modes/skill/SKILL.md), then:"
echo "  bash \"${ROOT}/scripts/run-once.sh\" <worktree-path> [log]"
echo "AERL HTTP pipelines: set TRAINER_BASE_URL in modes/skill/self-tuning/services/.env (default port 8004)."
