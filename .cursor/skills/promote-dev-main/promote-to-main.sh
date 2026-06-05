#!/usr/bin/env bash
# Promote allowlisted paths from branch `dev` to `main` (single public repo).
#
# Prerequisites:
#   - Local branch `dev` has the full tree (tests, docs/integration/, …)
#   - Run from repo root while on `dev` (Git Bash on Windows)
#
# Usage:
#   bash .cursor/skills/promote-dev-main/promote-to-main.sh
#   bash .cursor/skills/promote-dev-main/promote-to-main.sh --push
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
cd "${ROOT}"

SKILL_REL=".cursor/skills/promote-dev-main"
ALLOWLIST_REL="${SKILL_REL}/promote-allowlist.txt"
DENYLIST_REL="${SKILL_REL}/promote-denylist.txt"
GITIGNORE_MAIN_REL="${SKILL_REL}/gitignore.main"

SOURCE_BRANCH="${PROMOTE_SOURCE_BRANCH:-dev}"
TARGET_BRANCH="${PROMOTE_TARGET_BRANCH:-main}"
REMOTE="${PROMOTE_REMOTE:-origin}"
DO_PUSH=false

for arg in "$@"; do
  case "$arg" in
    --push) DO_PUSH=true ;;
    --dry-run) ;;
    -h|--help)
      sed -n '2,11p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

if ! git rev-parse --verify "${SOURCE_BRANCH}" >/dev/null 2>&1; then
  echo "ERROR: source branch '${SOURCE_BRANCH}' not found." >&2
  echo "Create it: git checkout -b dev && git push -u ${REMOTE} dev" >&2
  exit 1
fi

if ! git cat-file -e "${SOURCE_BRANCH}:${ALLOWLIST_REL}" 2>/dev/null; then
  echo "ERROR: missing ${ALLOWLIST_REL} on branch '${SOURCE_BRANCH}'." >&2
  exit 1
fi

read_paths_from_source() {
  local rel="$1"
  git show "${SOURCE_BRANCH}:${rel}" | grep -v '^\s*#' | grep -v '^\s*$' || true
}

CURRENT_BRANCH="$(git branch --show-current)"
RESTORE_BRANCH="${CURRENT_BRANCH}"

cleanup() {
  git checkout "${RESTORE_BRANCH}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Fetch ${REMOTE}"
git fetch "${REMOTE}" || true

echo "==> Checkout ${TARGET_BRANCH}"
git checkout "${TARGET_BRANCH}"
git pull "${REMOTE}" "${TARGET_BRANCH}" 2>/dev/null || true

echo "==> Apply allowlist from ${SOURCE_BRANCH}"
while IFS= read -r path; do
  [[ -z "${path}" ]] && continue
  if git cat-file -e "${SOURCE_BRANCH}:${path}" 2>/dev/null; then
    git checkout "${SOURCE_BRANCH}" -- "${path}"
  elif git ls-tree -d --name-only "${SOURCE_BRANCH}" "${path}" >/dev/null 2>&1; then
    git checkout "${SOURCE_BRANCH}" -- "${path}" 2>/dev/null || true
  else
    echo "    skip (not on ${SOURCE_BRANCH}): ${path}"
  fi
done < <(read_paths_from_source "${ALLOWLIST_REL}")

if git cat-file -e "${SOURCE_BRANCH}:${DENYLIST_REL}" 2>/dev/null; then
  echo "==> Remove denylisted paths from ${TARGET_BRANCH}"
  while IFS= read -r path; do
    [[ -z "${path}" ]] && continue
    git rm -rf --ignore-unmatch "${path}" 2>/dev/null || true
  done < <(read_paths_from_source "${DENYLIST_REL}")
fi

if git cat-file -e "${SOURCE_BRANCH}:${GITIGNORE_MAIN_REL}" 2>/dev/null; then
  echo "==> Apply main .gitignore template"
  git show "${SOURCE_BRANCH}:${GITIGNORE_MAIN_REL}" > "${ROOT}/.gitignore"
  git add .gitignore
fi

if git diff --quiet && git diff --cached --quiet; then
  echo "==> No changes to promote."
  exit 0
fi

echo "==> Staged diff summary:"
git diff --cached --stat

if [[ "${DO_PUSH}" != true ]]; then
  echo ""
  echo "Dry-run only. Re-run with --push to commit and push ${REMOTE}/${TARGET_BRANCH}."
  git reset --hard HEAD
  exit 0
fi

git commit -m "Promote allowlisted paths from ${SOURCE_BRANCH} to ${TARGET_BRANCH}."

echo "==> Push ${REMOTE} ${TARGET_BRANCH}"
git push "${REMOTE}" "${TARGET_BRANCH}"

echo "Done. ${REMOTE}/${TARGET_BRANCH} updated."
