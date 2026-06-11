#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# doctor.sh — self-diagnostic for the self-coaching skill.
#
# Runs a series of checks and reports PASS / WARN / FAIL for each. Exits non-zero
# if any FAIL check trips. WARN checks never fail the run.
#
# Usage:
#   bash scripts/doctor.sh           # human-readable output
#   bash scripts/doctor.sh --json    # one JSON object per check on stdout
#   bash scripts/doctor.sh --quiet   # only print failures + summary

set -Eeuo pipefail
IFS=$'\n\t'

# Resolve repo root (parent of this script's directory). Handles symlinked installs.
SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
  # readlink -f is GNU; fall back to a loop for BSD/macOS.
  if readlink -f "${SCRIPT_PATH}" >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f "${SCRIPT_PATH}")"
  else
    while [[ -L "${SCRIPT_PATH}" ]]; do
      SCRIPT_PATH="$(readlink "${SCRIPT_PATH}")"
    done
  fi
fi
SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODE="text"
QUIET=0
for arg in "$@"; do
  case "${arg}" in
    --json) MODE="json" ;;
    --quiet) QUIET=1 ;;
    -h|--help)
      sed -n '2,12p' "${SCRIPT_PATH}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "doctor.sh: unknown arg: ${arg}" >&2
      exit 2
      ;;
  esac
done

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

# Emit a check result.
#   $1 = status (PASS|WARN|FAIL)
#   $2 = check id (machine-readable)
#   $3 = human message
emit() {
  local status="$1" id="$2" msg="$3"
  case "${status}" in
    PASS) PASS_COUNT=$((PASS_COUNT+1)) ;;
    WARN) WARN_COUNT=$((WARN_COUNT+1)) ;;
    FAIL) FAIL_COUNT=$((FAIL_COUNT+1)) ;;
  esac
  if [[ "${MODE}" == "json" ]]; then
    # Escape double quotes and backslashes for JSON.
    local jmsg
    jmsg="$(printf '%s' "${msg}" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    printf '{"check":"%s","status":"%s","message":"%s"}\n' "${id}" "${status}" "${jmsg}"
    return
  fi
  if [[ "${QUIET}" -eq 1 && "${status}" == "PASS" ]]; then return; fi
  local color reset
  case "${status}" in
    PASS) color=$'\033[32m' ;;
    WARN) color=$'\033[33m' ;;
    FAIL) color=$'\033[31m' ;;
  esac
  reset=$'\033[0m'
  if [[ ! -t 1 ]]; then color=""; reset=""; fi
  printf '  %s[%s]%s %-40s %s\n' "${color}" "${status}" "${reset}" "${id}" "${msg}"
}

section() {
  if [[ "${MODE}" == "json" || "${QUIET}" -eq 1 ]]; then return; fi
  printf '\n%s\n' "$1"
}

# -------- Checks --------

section "Binaries"

for bin in bash git python jq curl uv shellcheck; do
  if command -v "${bin}" >/dev/null 2>&1; then
    ver="$( { "${bin}" --version 2>&1 || true; } | head -n1 | tr -d '\r')"
    [[ -z "${ver}" ]] && ver="(installed)"
    case "${bin}" in
      uv|shellcheck) emit PASS "bin.${bin}" "${ver}" ;;
      *)             emit PASS "bin.${bin}" "${ver}" ;;
    esac
  else
    case "${bin}" in
      bash|git|python) emit FAIL "bin.${bin}" "missing (required)" ;;
      jq|curl)         emit FAIL "bin.${bin}" "missing (required for AERL HTTP pipelines)" ;;
      uv)              emit WARN "bin.${bin}" "missing (only needed for local trainer preflight)" ;;
      shellcheck)      emit WARN "bin.${bin}" "missing (CI lints scripts; local dev can skip)" ;;
    esac
  fi
done

section "Script syntax (bash -n)"

shopt -s nullglob
script_files=(
  "${ROOT}"/scripts/*.sh
  "${ROOT}"/modes/self-coaching/self-tuning/pipelines/*/run.sh
  "${ROOT}"/modes/self-coaching/self-tuning/pipelines/_lib.sh
)
shopt -u nullglob

for f in "${script_files[@]}"; do
  rel="${f#${ROOT}/}"
  if bash -n "${f}" 2>/dev/null; then
    emit PASS "syntax.${rel}" "OK"
  else
    err="$(bash -n "${f}" 2>&1 || true)"
    emit FAIL "syntax.${rel}" "${err}"
  fi
done

section "Gitignore"

# .env must be ignored. Use git check-ignore if we are inside a git work tree.
if git -C "${ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git -C "${ROOT}" check-ignore -q modes/self-coaching/self-tuning/services/.env; then
    emit PASS "gitignore.env" "modes/self-coaching/self-tuning/services/.env is ignored"
  else
    emit FAIL "gitignore.env" "modes/self-coaching/self-tuning/services/.env is NOT ignored — credential leak risk"
  fi
  # Sanity-check: example.env must NOT be ignored (it's the template users copy).
  if git -C "${ROOT}" check-ignore -q modes/self-coaching/self-tuning/services/example.env; then
    emit FAIL "gitignore.example_env" "example.env is ignored — users won't see the template"
  else
    emit PASS "gitignore.example_env" "example.env is tracked"
  fi
else
  emit WARN "gitignore" "not inside a git work tree; skipping check-ignore assertions"
fi

section "Skill structure"

# Required top-level files for a working install.
required_files=(
  "modes/self-coaching/SKILL.md"
  "modes/self-coaching/SKILL_PACK_VERSION"
  "modes/self-coaching/DESCRIPTION.md"
  "README.md"
  "LICENSE"
  "scripts/install-skill-pack.sh"
  "docs/guides/deploy-skill-pack.md"
  "scripts/run-pipeline.sh"
  "modes/self-coaching/self-tuning/services/example.env"
  "modes/self-coaching/self-tuning/pipelines/registry.yaml"
  "modes/self-coaching/self-tuning/pipelines/_lib.sh"
  "modes/self-coaching/self-tuning/pipelines/sft/run.sh"
  "modes/self-coaching/self-tuning/pipelines/grpo/run.sh"
  "modes/self-coaching/self-learning/SKILL.md"
  "modes/self-coaching/self-play/SKILL.md"
  "modes/self-coaching/self-evaluation/SKILL.md"
  "modes/self-coaching/self-tuning/SKILL.md"
  "modes/coach/README.md"
  "mock-services/mock_self_coaching.py"
)
for rel in "${required_files[@]}"; do
  if [[ -e "${ROOT}/${rel}" ]]; then
    emit PASS "files.${rel}" "present"
  else
    emit FAIL "files.${rel}" "missing"
  fi
done

section "Skill content"

# No hardcoded user-specific paths in skill files (the bug we just fixed).
# Allow them inside historical run artifacts and the vendored superpowers clone.
bad_paths_excludes=(
  ":(exclude)references/superpowers-skills/**"
  ":(exclude)mock-services/production-readiness-runs/**"
  ":(exclude)mock-services/demo-run*/**"
)
if git -C "${ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # Use git grep (respects .gitignore and pathspecs).
  if matches="$(git -C "${ROOT}" grep -nE 'C:[/\\]Users[/\\]liumy26' -- \
        '*.md' '*.sh' '*.py' '*.yaml' '*.yml' '*.env' \
        "${bad_paths_excludes[@]}" 2>/dev/null)"; then
    if [[ -n "${matches}" ]]; then
      first_line="$(printf '%s' "${matches}" | head -n1)"
      emit FAIL "content.hardcoded_paths" "found hardcoded user paths (first: ${first_line})"
    else
      emit PASS "content.hardcoded_paths" "no hardcoded user paths in skill files"
    fi
  else
    emit PASS "content.hardcoded_paths" "no hardcoded user paths in skill files"
  fi

  # Stale 'training/services' or 'training/pipelines' (pre-rename) references.
  # We accept legitimate quotes-of-the-old-path inside backticks in pitfall sections
  # (e.g. "not `training/pipelines/`"), but reject bare unquoted occurrences.
  if matches="$(git -C "${ROOT}" grep -nE '(^|[^-/\`])training/(services|pipelines)/' -- \
        '*.md' '*.sh' '*.py' '*.yaml' '*.yml' '*.env' \
        "${bad_paths_excludes[@]}" 2>/dev/null \
        | grep -vE 'not \`training/(services|pipelines)/' \
        | grep -vE '\`training/(services|pipelines)/[^[:space:]]*\` ?[,.]' )"; then
    if [[ -n "${matches}" ]]; then
      first_line="$(printf '%s' "${matches}" | head -n1)"
      emit FAIL "content.stale_training_paths" "stale 'training/...' refs (first: ${first_line})"
    else
      emit PASS "content.stale_training_paths" "no stale 'training/...' refs"
    fi
  else
    emit PASS "content.stale_training_paths" "no stale 'training/...' refs"
  fi
else
  emit WARN "content" "not in a git work tree; skipping content scans"
fi

# Convert an MSYS / cygwin path to a native Windows path when needed.
# Python on Windows cannot open '/d/foo/bar' — it needs 'D:/foo/bar' or 'D:\foo\bar'.
to_native_path() {
  local p="$1"
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "${p}" 2>/dev/null || printf '%s' "${p}"
  else
    printf '%s' "${p}"
  fi
}

section "Contracts"

# Assert openapi.yaml and mock_service_contract.json are in sync.
if [[ -f "${ROOT}/mock-services/contracts/regenerate.py" ]]; then
  if command -v python >/dev/null 2>&1; then
    regen_script="$(to_native_path "${ROOT}/mock-services/contracts/regenerate.py")"
    if out="$(python "${regen_script}" --check 2>&1)"; then
      emit PASS "contracts.openapi_sync" "openapi.yaml ↔ mock_service_contract.json in sync"
    else
      emit FAIL "contracts.openapi_sync" "$(printf '%s' "${out}" | tr '\n' ' ' | head -c 200)"
    fi
  else
    emit WARN "contracts.openapi_sync" "python missing; skipping contract sync check"
  fi
fi

section "Skill pack (T1)"

if [[ -f "${ROOT}/modes/self-coaching/SKILL_PACK_VERSION" ]]; then
  ver="$(head -n 1 "${ROOT}/modes/self-coaching/SKILL_PACK_VERSION" | tr -d '\r\n')"
  emit PASS "skill_pack.version" "SKILL_PACK_VERSION=${ver}"
else
  emit FAIL "skill_pack.version" "modes/self-coaching/SKILL_PACK_VERSION missing"
fi

if [[ -x "${ROOT}/scripts/install-skill-pack.sh" ]] || [[ -f "${ROOT}/scripts/install-skill-pack.sh" ]]; then
  emit PASS "skill_pack.install_script" "scripts/install-skill-pack.sh present"
else
  emit FAIL "skill_pack.install_script" "scripts/install-skill-pack.sh missing"
fi

section "Python mock service"

# Smoke-import the mock module to surface syntax errors fast.
if command -v python >/dev/null 2>&1; then
  mock_main="$(to_native_path "${ROOT}/mock-services/mock_self_coaching.py")"
  mock_plugin="$(to_native_path "${ROOT}/mock-services/plugin_mock.py")"
  if err="$(python -c "import py_compile,sys; py_compile.compile(sys.argv[1], doraise=True)" "${mock_main}" 2>&1)"; then
    emit PASS "mock.compile" "mock_self_coaching.py compiles"
  else
    emit FAIL "mock.compile" "$(printf '%s' "${err}" | tr '\n' ' ' | head -c 200)"
  fi
  if err="$(python -c "import py_compile,sys; py_compile.compile(sys.argv[1], doraise=True)" "${mock_plugin}" 2>&1)"; then
    emit PASS "mock.compile_plugin" "plugin_mock.py compiles"
  else
    emit FAIL "mock.compile_plugin" "$(printf '%s' "${err}" | tr '\n' ' ' | head -c 200)"
  fi
fi

# -------- Summary --------

if [[ "${MODE}" == "json" ]]; then
  printf '{"check":"summary","status":"%s","pass":%d,"warn":%d,"fail":%d}\n' \
    "$([[ ${FAIL_COUNT} -eq 0 ]] && echo PASS || echo FAIL)" \
    "${PASS_COUNT}" "${WARN_COUNT}" "${FAIL_COUNT}"
else
  printf '\nSummary: %d passed, %d warnings, %d failed\n' \
    "${PASS_COUNT}" "${WARN_COUNT}" "${FAIL_COUNT}"
fi

[[ ${FAIL_COUNT} -eq 0 ]]
