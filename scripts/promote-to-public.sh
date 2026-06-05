#!/usr/bin/env bash
# Promote allowlisted paths from the private dev branch to public main.
#
# Prerequisites:
#   - origin  → public repo (github.com/Miya-Liu/self-coaching)
#   - private → private dev repo (github.com/Miya-Liu/self-coaching-dev)
#   - Branch `dev` has the full tree; `main` on origin is the public face
#
# Usage:
#   bash scripts/promote-to-public.sh              # dry-run (show planned changes)
#   bash scripts/promote-to-public.sh --push       # commit on main and push origin
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

SOURCE_BRANCH="${PROMOTE_SOURCE_BRANCH:-dev}"
PUBLIC_BRANCH="${PROMOTE_PUBLIC_BRANCH:-main}"
PUBLIC_REMOTE="${PROMOTE_PUBLIC_REMOTE:-origin}"
ALLOWLIST="${ROOT}/scripts/promote-allowlist.txt"
DENYLIST="${ROOT}/scripts/promote-denylist.txt"
DO_PUSH=false

for arg in "$@"; do
  case "$arg" in
    --push) DO_PUSH=true ;;
    --dry-run) ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

if ! git rev-parse --verify "${SOURCE_BRANCH}" >/dev/null 2>&1; then
  echo "ERROR: source branch '${SOURCE_BRANCH}' not found. Run scripts/setup-dev-remote.sh first." >&2
  exit 1
fi

if [[ ! -f "${ALLOWLIST}" ]]; then
  echo "ERROR: missing ${ALLOWLIST}" >&2
  exit 1
fi

read_paths() {
  local file="$1"
  grep -v '^\s*#' "${file}" | grep -v '^\s*$' || true
}

CURRENT_BRANCH="$(git branch --show-current)"
RESTORE_BRANCH="${CURRENT_BRANCH}"

cleanup() {
  git checkout "${RESTORE_BRANCH}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Fetch ${PUBLIC_REMOTE}"
git fetch "${PUBLIC_REMOTE}"

echo "==> Checkout ${PUBLIC_BRANCH} from ${PUBLIC_REMOTE}"
git checkout "${PUBLIC_BRANCH}"
git pull "${PUBLIC_REMOTE}" "${PUBLIC_BRANCH}" || true

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
done < <(read_paths "${ALLOWLIST}")

if [[ -f "${DENYLIST}" ]]; then
  echo "==> Remove denylisted paths from public ${PUBLIC_BRANCH}"
  while IFS= read -r path; do
    [[ -z "${path}" ]] && continue
    git rm -rf --ignore-unmatch "${path}" 2>/dev/null || true
  done < <(read_paths "${DENYLIST}")
fi

if git diff --quiet && git diff --cached --quiet; then
  echo "==> No changes to promote."
  exit 0
fi

echo "==> Staged diff summary:"
git diff --cached --stat

if [[ "${DO_PUSH}" != true ]]; then
  echo ""
  echo "Dry-run only. Re-run with --push to commit and push to ${PUBLIC_REMOTE}/${PUBLIC_BRANCH}."
  git reset --hard HEAD
  exit 0
fi

if ! git diff --cached --quiet; then
  git commit -m "Promote allowlisted paths from ${SOURCE_BRANCH} to public ${PUBLIC_BRANCH}."
fi

echo "==> Push ${PUBLIC_REMOTE} ${PUBLIC_BRANCH}"
git push "${PUBLIC_REMOTE}" "${PUBLIC_BRANCH}"

echo "Done. Public ${PUBLIC_REMOTE}/${PUBLIC_BRANCH} updated."
