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

# Copy a directory tree, excluding Python cache and egg metadata.
copy_tree_excluding() {
  local src="$1" dst="$2"
  mkdir -p "${dst}"
  tar -C "${src}" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.pytest_cache' \
    --exclude='*.egg-info' \
    --exclude='.egg-info' \
    -cf - . | tar -C "${dst}" -xf -
}

# Rewrite frontmatter `name:` so Hermes does not treat asset copies as skills.
neutralize_skill_frontmatter() {
  local skill_md="$1"
  local bundle_name="$2"
  if [[ ! -f "${skill_md}" ]]; then
    return 0
  fi
  if sed --version >/dev/null 2>&1; then
    sed -i -E "s/^name:[[:space:]]*.*/name: ${bundle_name}/" "${skill_md}"
  else
    sed -i '' -E "s/^name:[[:space:]]*.*/name: ${bundle_name}/" "${skill_md}"
  fi
}

# Fail when Hermes would see the same skill name in more than one SKILL.md.
check_duplicate_skill_names() {
  local skills_root="$1"
  local skill_md name
  local -A counts=()
  while IFS= read -r -d '' skill_md; do
    name="$(grep -m1 '^name:' "${skill_md}" 2>/dev/null | sed 's/^name:[[:space:]]*//' | tr -d '\r' || true)"
    [[ -z "${name}" ]] && continue
    [[ "${name}" == _asset-bundle-* ]] && continue
    counts["${name}"]=$(( ${counts["${name}"]:-0} + 1 ))
  done < <(find "${skills_root}" -name 'SKILL.md' -print0 2>/dev/null)
  for name in "${!counts[@]}"; do
    if [[ "${counts[$name]}" -gt 1 ]]; then
      echo "install-skill-pack.sh: ambiguous skill name '${name}' (${counts[$name]} SKILL.md files under ${skills_root})" >&2
      echo "  Remove duplicate SKILL.md copies (often under self-coaching/assets/) and retry." >&2
      return 1
    fi
  done
  return 0
}

install_hermes_skills() {
  local skills_root="$1"
  local src dst sub kind

  if ! check_duplicate_skill_names "${skills_root}"; then
    exit 1
  fi

  # Umbrella — Hermes-discoverable markdown + metadata only.
  src="${ROOT}/modes/self-coaching"
  dst="${skills_root}/self-coaching"
  mkdir -p "${dst}"
  for f in SKILL.md DESCRIPTION.md SKILL_PACK_VERSION; do
    [[ -f "${src}/${f}" ]] && cp -f "${src}/${f}" "${dst}/${f}"
  done
  for kind in references templates scripts; do
    [[ -d "${src}/${kind}" ]] && cp -rf "${src}/${kind}" "${dst}/"
  done

  # Flat sibling submodules — Hermes-discoverable.
  for sub in self-learning self-play self-evaluation self-tuning; do
    src="${ROOT}/modes/self-coaching/${sub}"
    dst="${skills_root}/${sub}"
    mkdir -p "${dst}"
    cp -f "${src}/SKILL.md" "${dst}/SKILL.md"
    for kind in references templates scripts; do
      [[ -d "${src}/${kind}" ]] && cp -rf "${src}/${kind}" "${dst}/"
    done
    if [[ "${sub}" == "self-tuning" ]]; then
      [[ -d "${src}/pipelines" ]] && cp -rf "${src}/pipelines" "${dst}/"
      [[ -d "${src}/services" ]] && cp -rf "${src}/services" "${dst}/"
    fi
  done
}

install_hermes_mock_assets() {
  local umbrella_dst="$1"
  local assets="${umbrella_dst}/assets"
  local skill_md

  mkdir -p "${assets}/mock-services" \
           "${assets}/scenarios" \
           "${assets}/tools" \
           "${assets}/services" \
           "${assets}/modes/self-coaching"

  copy_tree_excluding "${ROOT}/mock-services" "${assets}/mock-services"
  copy_tree_excluding "${ROOT}/scenarios" "${assets}/scenarios"
  mkdir -p "${assets}/tools"
  cp -f "${ROOT}/tools/loop_completeness.py" "${assets}/tools/"
  copy_tree_excluding "${ROOT}/services" "${assets}/services"

  # Runtime Python modules for legacy path resolution — NOT Hermes-discoverable.
  copy_tree_excluding "${ROOT}/modes/self-coaching" "${assets}/modes/self-coaching"
  while IFS= read -r -d '' skill_md; do
    rel="${skill_md#${assets}/modes/self-coaching/}"
    bundle="_asset-bundle-${rel//\//-}"
    bundle="${bundle%.md}"
    neutralize_skill_frontmatter "${skill_md}" "${bundle}"
  done < <(find "${assets}/modes/self-coaching" -name 'SKILL.md' -print0)
}

pip_install_runtime() {
  local py=""
  if command -v python3 >/dev/null 2>&1; then
    py="python3"
  elif command -v python >/dev/null 2>&1; then
    py="python"
  else
    echo "WARN: python not found; skipped pip install -e ." >&2
    echo "      Mock demo requires: pip install -e ${ROOT}" >&2
    return 0
  fi
  echo "==> Installing Python runtime (editable): pip install -e ${ROOT}"
  "${py}" -m pip install -e "${ROOT}" --quiet
}

if [[ "${HERMES_MODE:-0}" == "1" ]]; then
  if [[ "${TARGET}" == "${ROOT}" ]]; then
    TARGET="${HOME}/.hermes/skills"
  fi
  mkdir -p "${TARGET}"

  install_hermes_skills "${TARGET}"

  if [[ "${WITH_MOCK}" == "1" ]]; then
    pip_install_runtime
    install_hermes_mock_assets "${TARGET}/self-coaching"
    if ! check_duplicate_skill_names "${TARGET}"; then
      exit 1
    fi
  fi

  echo "==> Hermes skill pack installed to ${TARGET}"
  echo "    Skills:  hermes skill list | grep self-coaching"
  if [[ "${WITH_MOCK}" == "1" ]]; then
    echo "    Demo:    python -m self_coaching.demo"
  fi
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
  2. Mock demo: python -m self_coaching.demo  (or: pip install -e . first)
  3. Read: ${ROOT}/docs/guides/deploy-skill-pack.md
  4. Optional AERL: cp modes/self-coaching/self-tuning/services/example.env -> modes/self-coaching/self-tuning/services/.env
  5. Optional autoresearch: clone karpathy/autoresearch, export AUTORESEARCH_ROOT, see upstream/README.md

EOF
