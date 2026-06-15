#!/usr/bin/env bash
# T1 — Install / verify the self-coaching skill pack at a target root.
#
# Usage:
#   bash scripts/install-skill-pack.sh [target-root] [--hermes] [--with-mock] [--with-trainer]
#
# Flags:
#   --hermes        Hermes Agent ONLY — copy skills to ~/.hermes/skills/self-coaching/
#   --with-mock     Hermes: pip install -e . for python -m self_coaching.demo
#                   Non-Hermes: run mock-run-all.sh dry run
#
# Without --hermes: initialize coaching root at [target-root] (experience/, doctor,
# optional mock dry-run). Skills remain in modes/self-coaching/ (repo clone) or are
# copied manually (Cursor, pack copy). Does not touch ~/.hermes/skills/.
#
# Windows: POSIX bash only — run via Git Bash or WSL (no install-skill-pack.ps1).
#          Demo after install: scripts/mock-self-coaching-demo.ps1
#
# Examples:
#   bash scripts/install-skill-pack.sh .              # current repo as skill root
#   bash scripts/install-skill-pack.sh ~/skills/self-coaching --with-mock
#   bash scripts/install-skill-pack.sh --hermes --with-mock   # -> ~/.hermes/skills/
set -euo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/hermes-skill-pack.sh
source "${ROOT}/scripts/lib/hermes-skill-pack.sh"

TARGET="${ROOT}"
HERMES_MODE=0
WITH_MOCK=0

POSITIONAL=""
for arg in "$@"; do
  case "${arg}" in
    --hermes) HERMES_MODE=1 ;;
    --with-mock) WITH_MOCK=1 ;;
    --with-trainer|--with-upstream)
      echo "install-skill-pack.sh: --with-trainer removed (autoresearch path dropped); use AERL: bash scripts/preflight.sh" >&2
      exit 2
      ;;
    -h|--help)
      sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
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

  remove_legacy_hermes_flat_siblings "${TARGET}"
  install_hermes_skills "${TARGET}"
  install_hermes_bundle_assets "${TARGET}/self-coaching"
  write_hermes_installed_version "${TARGET}/self-coaching" "$(get_repo_sha)"

  if ! check_duplicate_skill_names "${TARGET}"; then
    exit 1
  fi

  if [[ "${WITH_MOCK}" == "1" ]]; then
    pip_install_runtime
  fi

  print_hermes_install_success "${TARGET}" "${WITH_MOCK}"
  exit 0
fi

echo "==> Self-coaching skill pack $(read_pack_semver)"
echo "    Source: ${ROOT}"
echo "    Target: ${TARGET}"

bash "${ROOT}/scripts/init-experience.sh" "${TARGET}"

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
  2. Mock demo: python -m self_coaching.demo  (or: pip install -e . first)
  3. Read: ${ROOT}/docs/guides/deploy-skill-pack.md
  4. Optional AERL: cp modes/self-coaching/self-tuning/services/example.env -> modes/self-coaching/self-tuning/services/.env; bash scripts/preflight.sh

EOF
