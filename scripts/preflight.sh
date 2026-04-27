#!/usr/bin/env bash
# Install deps for the vendored upstream trainer (shared lock under upstream/autoresearch).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM="${ROOT}/upstream/autoresearch"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install from https://docs.astral.sh/uv/" >&2
  exit 1
fi

echo "Syncing Python environment in ${UPSTREAM}..."
uv --directory "${UPSTREAM}" sync
echo "Done."
echo "If data/tokenizer cache is missing, run once: uv --directory \"${UPSTREAM}\" run prepare.py"
echo "Create a worktree (see SKILL.md), then: bash \"${ROOT}/scripts/run-once.sh\" <worktree-path> [log]"
