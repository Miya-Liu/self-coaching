#!/usr/bin/env bash
# T1 — Install / verify the self-coaching skill pack at a target root.
#
# Usage:
#   bash scripts/install-skill-pack.sh [target-root] [--hermes] [--with-mock] [--with-trainer]
#
# Examples:
#   bash scripts/install-skill-pack.sh .              # current repo as skill root
#   bash scripts/install-skill-pack.sh ~/skills/self-coaching --with-mock
#   bash scripts/install-skill-pack.sh --hermes --with-mock   # -> ~/.hermes/skills/
set -euo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ROOT}"
HERMES_MODE=0
WITH_MOCK=0
WITH_TRAINER=0

POSITIONAL=""
for arg in "$@"; do
  case "${arg}" in
    --hermes) HERMES_MODE=1 ;;
    --with-mock) WITH_MOCK=1 ;;
    --with-trainer|--with-upstream) WITH_TRAINER=1 ;;
    -h|--help)
      sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    --*)
      echo "install-skill-pack.sh: unknown arg: ${arg}" >&2
      exit 2
      ;;
    *)
      if [[ -n "${POSITIONAL}" ]]; then
        echo "install-skill-pack.sh: unexpected extra arg: ${arg}" >&2
        exit 2
      fi
      POSITIONAL="${arg}"
      ;;
  esac
done

if [[ -n "${POSITIONAL}" ]]; then
  if [[ "${HERMES_MODE}" -eq 1 && ! -d "${POSITIONAL}" ]]; then
    mkdir -p "${POSITIONAL}"
  fi
  TARGET="$(cd "${POSITIONAL}" && pwd)"
fi

if [[ "${HERMES_MODE:-0}" == "1" ]]; then
  if [[ "${TARGET}" == "${ROOT}" ]]; then
    TARGET="${HOME}/.hermes/skills"
  fi
  mkdir -p "${TARGET}"
  for sub in self-coaching self-learning self-play self-evaluation self-tuning; do
    src="${ROOT}/modes/self-coaching"
    [[ "${sub}" != "self-coaching" ]] && src="${ROOT}/modes/self-coaching/${sub}"
    dst="${TARGET}/${sub}"
    mkdir -p "${dst}"
    cp -f "${src}/SKILL.md" "${dst}/SKILL.md"
    for kind in references templates scripts; do
      [[ -d "${src}/${kind}" ]] && cp -rf "${src}/${kind}" "${dst}/"
    done
  done
  if [[ "${WITH_MOCK}" == "1" ]]; then
    umbrella_dst="${TARGET}/self-coaching"
    mkdir -p "${umbrella_dst}/assets/mock-services" \
             "${umbrella_dst}/assets/scenarios" \
             "${umbrella_dst}/assets/tools" \
             "${umbrella_dst}/assets/services" \
             "${umbrella_dst}/scripts"
    cp -rf "${ROOT}/mock-services/." "${umbrella_dst}/assets/mock-services/"
    cp -rf "${ROOT}/scenarios/."     "${umbrella_dst}/assets/scenarios/"
    cp -f  "${ROOT}/tools/loop_completeness.py" "${umbrella_dst}/assets/tools/"
    cp -rf "${ROOT}/services/."      "${umbrella_dst}/assets/services/"
    mkdir -p "${umbrella_dst}/assets/modes/self-coaching"
    cp -rf "${ROOT}/modes/self-coaching/." "${umbrella_dst}/assets/modes/self-coaching/"
    cp -f  "${ROOT}/scripts/mock_self_coaching_demo.py" \
           "${ROOT}/scripts/mock-self-coaching-demo.sh" \
           "${ROOT}/scripts/mock-self-coaching-demo.ps1" \
           "${umbrella_dst}/scripts/"
  fi
  echo "==> Hermes skill pack installed to ${TARGET}"
  echo "    Verify: hermes skill list | grep self-coaching"
  exit 0
fi

echo "==> Self-coaching skill pack $(tr -d '\r\n' < "${ROOT}/modes/self-coaching/SKILL_PACK_VERSION" 2>/dev/null || echo unknown)"
echo "    Source: ${ROOT}"
echo "    Target: ${TARGET}"

bash "${ROOT}/scripts/init-experience.sh" "${TARGET}"

if [[ "${WITH_TRAINER}" -eq 1 ]]; then
  if command -v uv >/dev/null 2>&1; then
    echo "==> Syncing external trainer repo (preflight)..."
    bash "${ROOT}/scripts/preflight.sh"
  else
    echo "WARN: --with-trainer requires uv and AUTORESEARCH_ROOT; skipped preflight" >&2
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
  1. Point your agent at: ${ROOT}/modes/self-coaching/SKILL.md
  2. Read: ${ROOT}/docs/guides/deploy-skill-pack.md
  3. Optional AERL: cp modes/self-coaching/self-tuning/services/example.env -> modes/self-coaching/self-tuning/services/.env
  4. Optional autoresearch: clone karpathy/autoresearch, export AUTORESEARCH_ROOT, see upstream/README.md

EOF
