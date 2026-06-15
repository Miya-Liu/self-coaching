#!/usr/bin/env bash
# init-experience.sh — bootstrap a project experience workspace.
#
# Usage:
#   init-experience.sh [<project-root>]
#
# If <project-root> is omitted, initializes in the current directory.
# Creates (without overwriting) the canonical experience layout used by the
# self-coaching/self-learning skill:
#
#   <project-root>/experience/EXPERIMENT_LOG.md
#   <project-root>/experience/ERROR.md
#   <project-root>/experience/LEARNINGS.md
#   <project-root>/logs/
#   <project-root>/worktrees/
#
# Exit codes:
#   0 — success (created or already present)
#   1 — failed to create (permissions, bad path)
#   2 — usage error

set -euo pipefail

usage() {
  cat >&2 <<EOF
usage: init-experience.sh [<project-root>]

Initializes a self-coaching experience workspace. If <project-root> is
omitted, uses the current directory.
EOF
  exit 2
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
fi

ROOT="${1:-.}"

if [[ ! -d "$ROOT" ]]; then
  mkdir -p "$ROOT" || { echo "init-experience: cannot create $ROOT" >&2; exit 1; }
fi

mkdir -p "$ROOT/experience" "$ROOT/logs" "$ROOT/worktrees"

for f in EXPERIMENT_LOG.md ERROR.md LEARNINGS.md; do
  path="$ROOT/experience/$f"
  if [[ ! -e "$path" ]]; then
    case "$f" in
      EXPERIMENT_LOG.md)
        cat > "$path" <<'EOF'
# Experiment Log

One entry per run, newest first. Keep entries compact; reference log files
in `../logs/` for raw output. Do not paste full transcripts here.

EOF
        ;;
      ERROR.md)
        cat > "$path" <<'EOF'
# Error Log

Append concise incident blocks, not raw stack traces. Schema:

## <date> <short-title>
- category: crash | oom | parse_error | env | logic_bug | other
- symptom:
- command/log: logs/<run-id>.log lines <start>-<end>
- root_cause:
- fix_or_workaround:
- verification:
- durable_artifact: memory | skill_patch | test | eval_case | training_candidate | none

EOF
        ;;
      LEARNINGS.md)
        cat > "$path" <<'EOF'
# Learnings

Reusable, stable lessons only. Schema:

## <date> <short-title>
- category: optimization | process | metric | stability | best_practice
- context:
- observation:
- reusable_lesson:
- evidence:
- next_artifact: skill_patch | eval_case | self_play_task | training_manifest | none

EOF
        ;;
    esac
    echo "init-experience: created $path"
  else
    echo "init-experience: kept $path (already exists)"
  fi
done

echo "init-experience: ready at $ROOT"
