#!/usr/bin/env bash
# Update an installed Hermes self-coaching skill pack from the current repo checkout.
# Hermes Agent ONLY — Cursor, pack copy, and repo-clone users: see
# docs/guides/deploy-skill-pack.md#upgrade
#
# Usage:
#   bash scripts/update-skill-pack.sh --hermes [--dry-run] [--force] [skills-root]
#
# Flags:
#   --hermes     Update ~/.hermes/skills/self-coaching/ (Hermes default)
#   --dry-run    Show diffs and commits since last install; do not write
#   --force      Overwrite local edits to managed skill files
#
# Windows: POSIX bash only — run via Git Bash or WSL.
#
# Examples:
#   bash scripts/update-skill-pack.sh --hermes --dry-run
#   bash scripts/update-skill-pack.sh --hermes
#   bash scripts/update-skill-pack.sh --hermes --force
set -euo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/hermes-skill-pack.sh
source "${ROOT}/scripts/lib/hermes-skill-pack.sh"

TARGET="${HOME}/.hermes/skills"
HERMES_MODE=0
DRY_RUN=0
FORCE=0

POSITIONAL=""
for arg in "$@"; do
  case "${arg}" in
    --hermes) HERMES_MODE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    -h|--help)
      sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    --*)
      echo "update-skill-pack.sh: unknown arg: ${arg}" >&2
      exit 2
      ;;
    *)
      if [[ -n "${POSITIONAL}" ]]; then
        echo "update-skill-pack.sh: unexpected extra arg: ${arg}" >&2
        exit 2
      fi
      POSITIONAL="${arg}"
      ;;
  esac
done

if [[ "${HERMES_MODE}" -ne 1 ]]; then
  echo "update-skill-pack.sh: --hermes is required (Hermes Agent installs only)." >&2
  echo "  Other agents: git pull, compare modes/self-coaching/SKILL_PACK_VERSION," >&2
  echo "  re-copy modes/self-coaching/ or re-run install-skill-pack.sh — see docs/guides/deploy-skill-pack.md#upgrade" >&2
  exit 2
fi

if [[ -n "${POSITIONAL}" ]]; then
  TARGET="$(cd "${POSITIONAL}" && pwd)"
fi

UMBRELLA="${TARGET}/self-coaching"
REPO_SHA="$(get_repo_sha)"
INSTALLED_SHA="$(read_hermes_installed_sha "${UMBRELLA}")"

if [[ ! -d "${UMBRELLA}" || ! -f "${UMBRELLA}/SKILL.md" ]]; then
  echo "update-skill-pack.sh: no Hermes install found at ${UMBRELLA}" >&2
  echo "  Run: bash scripts/install-skill-pack.sh --hermes" >&2
  exit 1
fi

classify_hermes_update() {
  local repo_path installed_rel installed_path
  local -n _updates="$1"
  local -n _local_mods="$2"
  local -n _new_files="$3"
  local -n _unchanged="$4"

  while IFS= read -r repo_path; do
    [[ -n "${repo_path}" ]] || continue
    installed_rel="$(repo_path_to_installed_rel "${repo_path}")"
    installed_path="${TARGET}/${installed_rel}"
    local src_path="${ROOT}/${repo_path}"

    if [[ ! -f "${installed_path}" ]]; then
      _new_files+=("${installed_rel}")
      continue
    fi

    if cmp -s "${installed_path}" "${src_path}" 2>/dev/null; then
      _unchanged+=("${installed_rel}")
      continue
    fi

    if [[ -n "${INSTALLED_SHA}" && "${INSTALLED_SHA}" != "unknown" && "${REPO_SHA}" != "unknown" ]]; then
      local base_file
      base_file="$(mktemp)"
      if git -C "${ROOT}" show "${INSTALLED_SHA}:${repo_path}" > "${base_file}" 2>/dev/null; then
        if cmp -s "${installed_path}" "${base_file}" 2>/dev/null; then
          _updates+=("${installed_rel}")
        elif cmp -s "${installed_path}" "${src_path}" 2>/dev/null; then
          _unchanged+=("${installed_rel}")
        else
          _local_mods+=("${installed_rel}")
        fi
        rm -f "${base_file}"
        continue
      fi
      rm -f "${base_file}"
    fi

    # No installed_sha (legacy install) or git history unavailable — treat diff as local edit.
    _local_mods+=("${installed_rel}")
  done < <(list_hermes_managed_repo_paths)
}

UPDATES=()
LOCAL_MODS=()
NEW_FILES=()
UNCHANGED=()
classify_hermes_update UPDATES LOCAL_MODS NEW_FILES UNCHANGED

TOTAL_CHANGES=$(( ${#UPDATES[@]} + ${#NEW_FILES[@]} ))

echo "==> Hermes skill pack update"
echo "    Install: ${UMBRELLA}"
echo "    Pack version (repo): $(read_pack_semver)"
echo "    Installed SHA: ${INSTALLED_SHA:-<none — legacy install>}"
echo "    Repo SHA:      ${REPO_SHA}"

if [[ "${INSTALLED_SHA}" == "${REPO_SHA}" && "${TOTAL_CHANGES}" -eq 0 && ${#LOCAL_MODS[@]} -eq 0 ]]; then
  echo "==> Already up to date."
  exit 0
fi

if [[ "${REPO_SHA}" != "unknown" && -n "${INSTALLED_SHA}" && "${INSTALLED_SHA}" != "unknown" && "${INSTALLED_SHA}" != "${REPO_SHA}" ]]; then
  echo ""
  echo "==> Commits since last install (${INSTALLED_SHA:0:12}..${REPO_SHA:0:12}):"
  if git -C "${ROOT}" log --oneline "${INSTALLED_SHA}..${REPO_SHA}" 2>/dev/null | head -n 20 | sed 's/^/    /'; then
    :
  else
    echo "    (unable to compute git log)"
  fi
fi

if [[ "${TOTAL_CHANGES}" -eq 0 && ${#LOCAL_MODS[@]} -eq 0 ]]; then
  echo "==> Skill files match repo; refreshing installed_sha stamp only."
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "    (dry-run: would write installed_sha=${REPO_SHA})"
    exit 0
  fi
  write_hermes_installed_version "${UMBRELLA}" "${REPO_SHA}"
  exit 0
fi

if [[ ${#NEW_FILES[@]} -gt 0 ]]; then
  echo ""
  echo "==> New files (${#NEW_FILES[@]}):"
  printf '    + %s\n' "${NEW_FILES[@]}"
fi

if [[ ${#UPDATES[@]} -gt 0 ]]; then
  echo ""
  echo "==> Upstream changes (${#UPDATES[@]}):"
  printf '    ~ %s\n' "${UPDATES[@]}"
fi

if [[ ${#LOCAL_MODS[@]} -gt 0 ]]; then
  echo ""
  echo "==> Local modifications (${#LOCAL_MODS[@]}) — need --force to overwrite:"
  printf '    ! %s\n' "${LOCAL_MODS[@]}"
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo ""
  echo "==> Diff (installed → repo):"
  while IFS= read -r repo_path; do
    [[ -n "${repo_path}" ]] || continue
    installed_rel="$(repo_path_to_installed_rel "${repo_path}")"
    installed_path="${TARGET}/${installed_rel}"
    src_path="${ROOT}/${repo_path}"
    [[ -f "${src_path}" ]] || continue
    if [[ -f "${installed_path}" ]] && cmp -s "${installed_path}" "${src_path}" 2>/dev/null; then
      continue
    fi
    echo "--- ${installed_rel}"
    if [[ -f "${installed_path}" ]]; then
      diff -u "${installed_path}" "${src_path}" || true
    else
      echo "    (new file in repo)"
      head -n 40 "${src_path}" | sed 's/^/    /'
      if [[ "$(wc -l < "${src_path}")" -gt 40 ]]; then
        echo "    ..."
      fi
    fi
  done < <(list_hermes_managed_repo_paths)
  echo ""
  echo "==> Dry run complete — no files written."
  exit 0
fi

if [[ ${#LOCAL_MODS[@]} -gt 0 && "${FORCE}" -ne 1 ]]; then
  echo ""
  echo "update-skill-pack.sh: local modifications detected; re-run with --force to overwrite." >&2
  echo "  Preview: bash scripts/update-skill-pack.sh --hermes --dry-run" >&2
  exit 1
fi

remove_legacy_hermes_flat_siblings "${TARGET}"
install_hermes_skills "${TARGET}"
write_hermes_installed_version "${UMBRELLA}" "${REPO_SHA}"

if ! check_duplicate_skill_names "${TARGET}"; then
  exit 1
fi

echo ""
print_hermes_install_success "${TARGET}" 0
echo "==> Updated ${TOTAL_CHANGES} file(s); ${#LOCAL_MODS[@]} local edit(s) overwritten."
