#!/usr/bin/env bash
# Smoke tests for skill-pack experience scripts (L1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="${ROOT}/modes/self-coaching/scripts"
WORK="${ROOT}/.ci-skill-pack-scripts-$$"
trap 'rm -rf "${WORK}"' EXIT

test -x "${SCRIPTS}/init-experience.sh" || test -f "${SCRIPTS}/init-experience.sh"
test -f "${SCRIPTS}/hook-inject-errors.sh"
test -f "${SCRIPTS}/hook-inject-learnings.sh"

mkdir -p "${WORK}"
bash "${SCRIPTS}/init-experience.sh" "${WORK}"
for f in EXPERIMENT_LOG.md ERROR.md LEARNINGS.md; do
  test -f "${WORK}/experience/${f}"
done
test -d "${WORK}/logs"
test -d "${WORK}/worktrees"

# Idempotent re-run
out="$(bash "${SCRIPTS}/init-experience.sh" "${WORK}")"
echo "${out}" | grep -q "kept"

# Hooks: missing log → silent exit 0
(
  cd "${WORK}"
  bash "${SCRIPTS}/hook-inject-errors.sh"
  bash "${SCRIPTS}/hook-inject-learnings.sh"
)

echo "line1" > "${WORK}/experience/ERROR.md"
(
  cd "${WORK}"
  out="$(bash "${SCRIPTS}/hook-inject-errors.sh")"
  echo "${out}" | grep -q "BEGIN experience/ERROR.md"
)

if ERROR_TAIL_LINES=bad bash "${SCRIPTS}/hook-inject-errors.sh" 2>/dev/null; then
  echo "expected hook-inject-errors to fail on bad ERROR_TAIL_LINES" >&2
  exit 1
fi

echo "test_skill_pack_scripts: OK"
