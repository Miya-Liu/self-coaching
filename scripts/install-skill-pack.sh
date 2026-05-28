#!/usr/bin/env bash
# T1 — Install / verify the self-coaching skill pack at a target root.
#
# Usage:
#   bash scripts/install-skill-pack.sh [target-root] [--with-mock] [--with-upstream]
#
# Examples:
#   bash scripts/install-skill-pack.sh .              # current repo as skill root
#   bash scripts/install-skill-pack.sh ~/skills/self-coaching --with-mock
set -euo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ROOT}"
WITH_MOCK=0
WITH_UPSTREAM=0

if [[ $# -gt 0 && "${1}" != --* ]]; then
  TARGET="$(cd "${1}" && pwd)"
  shift
fi

for arg in "$@"; do
  case "${arg}" in
    --with-mock) WITH_MOCK=1 ;;
    --with-upstream) WITH_UPSTREAM=1 ;;
    -h|--help)
      sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "install-skill-pack.sh: unknown arg: ${arg}" >&2
      exit 2
      ;;
  esac
done

echo "==> Self-coaching skill pack $(tr -d '\r\n' < "${ROOT}/SKILL_PACK_VERSION" 2>/dev/null || echo unknown)"
echo "    Source: ${ROOT}"
echo "    Target: ${TARGET}"

bash "${ROOT}/scripts/init-experience.sh" "${TARGET}"

if [[ "${WITH_UPSTREAM}" -eq 1 && -d "${ROOT}/upstream/autoresearch" ]]; then
  if command -v uv >/dev/null 2>&1; then
    echo "==> Syncing upstream/autoresearch (uv)..."
    bash "${ROOT}/scripts/preflight.sh"
  else
    echo "WARN: --with-upstream requires uv; skipped preflight" >&2
  fi
fi

echo "==> Running doctor.sh..."
if ! bash "${ROOT}/scripts/doctor.sh" --quiet; then
  echo "doctor.sh reported failures — run: bash scripts/doctor.sh" >&2
  exit 1
fi

if [[ "${WITH_MOCK}" -eq 1 ]]; then
  if ! command -v python >/dev/null 2>&1; then
    echo "WARN: --with-mock requires python; skipped mock-run-all" >&2
  else
    DEMO="${TARGET}/mock-services/demo-run"
    echo "==> Mock pipeline dry run -> ${DEMO}"
    bash "${ROOT}/scripts/mock-run-all.sh" "${DEMO}" sft
  fi
fi

cat <<EOF

Skill pack ready at: ${TARGET}

Next steps:
  1. Point your agent at: ${TARGET}/SKILL.md
  2. Read: ${ROOT}/docs/deploy-t1-skill-pack.md
  3. Optional AERL: cp self-coaching-training/services/example.env -> .env

EOF
