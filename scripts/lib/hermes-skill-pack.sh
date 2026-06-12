#!/usr/bin/env bash
# Shared Hermes skill-pack install/update helpers.
# Sourced by install-skill-pack.sh and update-skill-pack.sh (do not execute directly).

HERMES_SUBMODULES=(self-learning self-play self-evaluation self-tuning)
HERMES_ASSET_KINDS=(references templates scripts)

copy_tree_excluding() {
  local src="$1" dst="$2"
  shift 2
  local extra exclude
  mkdir -p "${dst}"
  local tar_args=( -C "${src}"
    --exclude='__pycache__'
    --exclude='*.pyc'
    --exclude='*.pyo'
    --exclude='.pytest_cache'
    --exclude='*.egg-info'
    --exclude='.egg-info'
  )
  for exclude in "$@"; do
    tar_args+=( "--exclude=${exclude}" )
  done
  tar "${tar_args[@]}" -cf - . | tar -C "${dst}" -xf -
}

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
      echo "hermes-skill-pack: ambiguous skill name '${name}' (${counts[$name]} SKILL.md files under ${skills_root})" >&2
      echo "  Remove duplicate SKILL.md copies (often under self-coaching/assets/) and retry." >&2
      return 1
    fi
  done
  return 0
}

remove_legacy_hermes_flat_siblings() {
  local skills_root="$1"
  local sub legacy
  for sub in "${HERMES_SUBMODULES[@]}"; do
    legacy="${skills_root}/${sub}"
    if [[ -f "${legacy}/SKILL.md" ]] && grep -q 'self-coaching' "${legacy}/SKILL.md" 2>/dev/null; then
      echo "==> Removing legacy flat install: ${legacy}"
      rm -rf "${legacy}"
    fi
  done
}

read_pack_semver() {
  local root="${1:-${ROOT}}"
  tr -d '\r\n' < "${root}/modes/self-coaching/SKILL_PACK_VERSION" | head -n 1
}

get_repo_sha() {
  git -C "${ROOT}" rev-parse HEAD 2>/dev/null || echo "unknown"
}

read_hermes_installed_sha() {
  local umbrella="$1"
  local vf="${umbrella}/SKILL_PACK_VERSION"
  [[ -f "${vf}" ]] || return 0
  grep -E '^installed_sha=' "${vf}" 2>/dev/null | head -n 1 | cut -d= -f2- | tr -d '\r\n' || true
}

# Write Hermes install stamp (semver + git SHA). Only for ~/.hermes/skills/self-coaching/.
# Repo modes/self-coaching/SKILL_PACK_VERSION stays semver-only (single line).
write_hermes_installed_version() {
  local umbrella="$1"
  local sha="$2"
  local semver
  semver="$(read_pack_semver)"
  mkdir -p "${umbrella}"
  printf '%s\ninstalled_sha=%s\n' "${semver}" "${sha}" > "${umbrella}/SKILL_PACK_VERSION"
}

repo_path_to_installed_rel() {
  local repo_path="$1"
  local rest="${repo_path#modes/self-coaching/}"
  echo "self-coaching/${rest}"
}

# Print repo-relative paths (under modes/self-coaching/) managed by Hermes install.
list_hermes_managed_repo_paths() {
  local src="${ROOT}/modes/self-coaching"
  local sub kind

  for f in SKILL.md DESCRIPTION.md; do
    [[ -f "${src}/${f}" ]] && echo "modes/self-coaching/${f}"
  done

  for kind in "${HERMES_ASSET_KINDS[@]}"; do
    [[ -d "${src}/${kind}" ]] || continue
    while IFS= read -r -d '' path; do
      echo "${path#${ROOT}/}"
    done < <(find "${src}/${kind}" -type f -print0 2>/dev/null)
  done

  for sub in "${HERMES_SUBMODULES[@]}"; do
    [[ -f "${src}/${sub}/SKILL.md" ]] && echo "modes/self-coaching/${sub}/SKILL.md"
    for kind in "${HERMES_ASSET_KINDS[@]}"; do
      [[ -d "${src}/${sub}/${kind}" ]] || continue
      while IFS= read -r -d '' path; do
        echo "${path#${ROOT}/}"
      done < <(find "${src}/${sub}/${kind}" -type f -print0 2>/dev/null)
    done
    if [[ "${sub}" == "self-tuning" ]]; then
      for extra in pipelines services; do
        [[ -d "${src}/${sub}/${extra}" ]] || continue
        while IFS= read -r -d '' path; do
          echo "${path#${ROOT}/}"
        done < <(find "${src}/${sub}/${extra}" -type f -print0 2>/dev/null)
      done
    fi
  done
}

install_hermes_skills() {
  local skills_root="$1"
  local src dst umbrella sub kind

  umbrella="${skills_root}/self-coaching"
  mkdir -p "${umbrella}"

  src="${ROOT}/modes/self-coaching"
  for f in SKILL.md DESCRIPTION.md; do
    [[ -f "${src}/${f}" ]] && cp -f "${src}/${f}" "${umbrella}/${f}"
  done
  for kind in "${HERMES_ASSET_KINDS[@]}"; do
    [[ -d "${src}/${kind}" ]] && cp -rf "${src}/${kind}" "${umbrella}/"
  done

  for sub in "${HERMES_SUBMODULES[@]}"; do
    src="${ROOT}/modes/self-coaching/${sub}"
    dst="${umbrella}/${sub}"
    mkdir -p "${dst}"
    cp -f "${src}/SKILL.md" "${dst}/SKILL.md"
    for kind in "${HERMES_ASSET_KINDS[@]}"; do
      [[ -d "${src}/${kind}" ]] && cp -rf "${src}/${kind}" "${dst}/"
    done
    if [[ "${sub}" == "self-tuning" ]]; then
      [[ -d "${src}/pipelines" ]] && cp -rf "${src}/pipelines" "${dst}/"
      [[ -d "${src}/services" ]] && cp -rf "${src}/services" "${dst}/"
    fi
  done
}

install_hermes_bundle_assets() {
  local umbrella_dst="$1"
  local skill_md assets="${umbrella_dst}/assets"

  # Legacy layout: mock-services lived under assets/ only — migrate to SKILL.md paths.
  if [[ -d "${assets}/mock-services" && ! -d "${umbrella_dst}/mock-services" ]]; then
    mkdir -p "${umbrella_dst}"
    mv "${assets}/mock-services" "${umbrella_dst}/mock-services"
  fi
  if [[ -d "${assets}/scenarios" && ! -d "${umbrella_dst}/scenarios" ]]; then
    mv "${assets}/scenarios" "${umbrella_dst}/scenarios"
  fi

  # Paths referenced in SKILL.md (mock-services/README.md, scenarios/, tools/).
  copy_tree_excluding "${ROOT}/mock-services" "${umbrella_dst}/mock-services" \
    production-readiness-runs demo-loop demo-run 'ci-mock-*'
  copy_tree_excluding "${ROOT}/scenarios" "${umbrella_dst}/scenarios"
  mkdir -p "${umbrella_dst}/tools"
  cp -f "${ROOT}/tools/loop_completeness.py" "${umbrella_dst}/tools/"

  # Python loop runtime + service adapters — not Hermes-discoverable.
  mkdir -p "${assets}/services" "${assets}/modes/self-coaching"
  copy_tree_excluding "${ROOT}/services" "${assets}/services"
  copy_tree_excluding "${ROOT}/modes/self-coaching" "${assets}/modes/self-coaching"
  while IFS= read -r -d '' skill_md; do
    rel="${skill_md#${assets}/modes/self-coaching/}"
    bundle="_asset-bundle-${rel//\//-}"
    bundle="${bundle%.md}"
    neutralize_skill_frontmatter "${skill_md}" "${bundle}"
  done < <(find "${assets}/modes/self-coaching" -name 'SKILL.md' -print0)
}

# Back-compat alias
install_hermes_mock_assets() {
  install_hermes_bundle_assets "$1"
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

print_hermes_install_success() {
  local target="$1"
  local with_mock="${2:-0}"
  echo "==> Hermes skill pack installed to ${target}/self-coaching"
  echo "==> Pack version: $(read_pack_semver) (installed_sha=$(read_hermes_installed_sha "${target}/self-coaching"))"
  echo "==> Installed 5 skills (nested under self-coaching/):"
  echo "    - self-coaching/SKILL.md (umbrella)"
  echo "    - self-coaching/self-learning/"
  echo "    - self-coaching/self-play/"
  echo "    - self-coaching/self-evaluation/"
  echo "    - self-coaching/self-tuning/"
  echo "==> Mock harness: ${target}/self-coaching/mock-services/ (see mock-services/README.md)"
  echo "==> Update later: bash scripts/update-skill-pack.sh --hermes [--dry-run]"
  echo "==> Verify: hermes skill list | grep -E '^(self-coaching|self-learning|self-play|self-evaluation|self-tuning)$'"
  if [[ "${with_mock}" == "1" ]]; then
    echo "==> Demo:    python -m self_coaching.demo  (requires pip install -e . from repo clone)"
  else
    echo "==> CLI smoke: cd \"${target}/self-coaching\" && python mock-services/mock_self_coaching.py --help"
    echo "    Full demo: bash scripts/install-skill-pack.sh --hermes --with-mock  (adds pip install -e .)"
  fi
}
