#!/usr/bin/env bash
# Resolve path to an external autoresearch (or compatible) trainer git tree.
# SPDX-License-Identifier: MIT
#
# Priority:
#   1. AUTORESEARCH_ROOT
#   2. TRAINER_REPO (alias)
#   3. ${SKILL_ROOT}/upstream/autoresearch if present (legacy local clone, gitignored)
#
# Usage (source from other scripts):
#   source "$(dirname "${BASH_SOURCE[0]}")/lib-trainer-repo.sh"
#   repo="$(resolve_autoresearch_root "${SKILL_ROOT:-}")" || exit 1

resolve_autoresearch_root() {
  local skill_root="${1:-}"
  local candidate=""

  if [[ -n "${AUTORESEARCH_ROOT:-}" ]]; then
    candidate="${AUTORESEARCH_ROOT}"
  elif [[ -n "${TRAINER_REPO:-}" ]]; then
    candidate="${TRAINER_REPO}"
  elif [[ -n "${skill_root}" && -f "${skill_root}/upstream/autoresearch/train.py" ]]; then
    candidate="${skill_root}/upstream/autoresearch"
  else
    return 1
  fi

  if [[ ! -d "${candidate}" || ! -f "${candidate}/train.py" ]]; then
    echo "lib-trainer-repo: trainer repo missing train.py: ${candidate}" >&2
    return 1
  fi

  printf '%s' "$(cd "${candidate}" && pwd)"
}

autoresearch_root_hint() {
  cat <<'EOF' >&2
Set AUTORESEARCH_ROOT to a separate clone of https://github.com/karpathy/autoresearch
(or any compatible repo with train.py). Example:

  git clone https://github.com/karpathy/autoresearch.git ~/src/autoresearch
  export AUTORESEARCH_ROOT=~/src/autoresearch
  bash scripts/preflight.sh

See docs/guides/runbook.md and upstream/README.md.
EOF
}
