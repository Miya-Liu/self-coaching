#!/usr/bin/env bash
# Bootstrap private dev repo workflow (one-time per machine).
#
# 1. Create an empty PRIVATE repo on GitHub (no README):
#      https://github.com/new  → name: self-coaching-dev, visibility: Private
# 2. Run:
#      export PRIVATE_REMOTE_URL=git@github.com:Miya-Liu/self-coaching-dev.git
#      bash scripts/setup-dev-remote.sh
#
# This creates branch `dev` with tests/, integration docs, and snapshots tracked,
# pushes it to the private remote, and leaves you on `main` for day-to-day public work.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

PRIVATE_REMOTE_NAME="${PRIVATE_REMOTE_NAME:-private}"
PRIVATE_REMOTE_URL="${PRIVATE_REMOTE_URL:-git@github.com:Miya-Liu/self-coaching-dev.git}"
PUBLIC_REMOTE="${PUBLIC_REMOTE:-origin}"
DEV_BRANCH="${DEV_BRANCH:-dev}"

if [[ -z "${PRIVATE_REMOTE_URL}" ]]; then
  echo "Set PRIVATE_REMOTE_URL (e.g. git@github.com:ORG/self-coaching-dev.git)" >&2
  exit 1
fi

if git remote get-url "${PRIVATE_REMOTE_NAME}" >/dev/null 2>&1; then
  git remote set-url "${PRIVATE_REMOTE_NAME}" "${PRIVATE_REMOTE_URL}"
  echo "==> Updated remote ${PRIVATE_REMOTE_NAME} → ${PRIVATE_REMOTE_URL}"
else
  git remote add "${PRIVATE_REMOTE_NAME}" "${PRIVATE_REMOTE_URL}"
  echo "==> Added remote ${PRIVATE_REMOTE_NAME} → ${PRIVATE_REMOTE_URL}"
fi

CURRENT="$(git branch --show-current)"
echo "==> Create/update ${DEV_BRANCH} from ${CURRENT}"
git checkout -B "${DEV_BRANCH}"

if [[ -f "${ROOT}/scripts/gitignore.dev" ]]; then
  cp "${ROOT}/scripts/gitignore.dev" "${ROOT}/.gitignore"
  git add .gitignore
fi

echo "==> Stage dev-only paths (force-add ignored files)"
git add -f tests/*.py tests/conftest.py tests/fixtures/ 2>/dev/null || true
git add -f docs/integration/ 2>/dev/null || true
git add -f docs/project/integration-plan.md docs/project/progress.md 2>/dev/null || true
git add -f scripts/DEV_WORKFLOW.md 2>/dev/null || true
# Stage any other tracked edits on dev (avoid git add -A — skips __pycache__ via .gitignore)
git add -u

if git diff --cached --quiet; then
  echo "==> No new changes on ${DEV_BRANCH}."
else
  git commit -m "dev: track tests, integration artifacts, and internal project docs."
fi

echo "==> Push ${DEV_BRANCH} to ${PRIVATE_REMOTE_NAME} (private)"
git push -u "${PRIVATE_REMOTE_NAME}" "${DEV_BRANCH}:main"

echo "==> Return to ${PUBLIC_REMOTE}/main"
git checkout main 2>/dev/null || git checkout -b main "${PUBLIC_REMOTE}/main"
git pull "${PUBLIC_REMOTE}" main || true

cat <<EOF

Private dev repo bootstrap complete.

  Public:  ${PUBLIC_REMOTE}  →  branch main   (lean, github.com/Miya-Liu/self-coaching)
  Private: ${PRIVATE_REMOTE_NAME}  →  branch main   (full tree from local ${DEV_BRANCH})

Day to day:
  - Commit integration work on branch ${DEV_BRANCH}; push: git push ${PRIVATE_REMOTE_NAME} ${DEV_BRANCH}:main
  - Promote to public: bash scripts/promote-to-public.sh --dry-run
                       bash scripts/promote-to-public.sh --push

See scripts/DEV_WORKFLOW.md (on ${DEV_BRANCH} / private repo only).

EOF
