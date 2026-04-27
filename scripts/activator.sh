#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
[self-coaching reminder]
- Use git + Bash: worktree for experiments; only edit inside worktrees/<id>/; merge to upstream/main only after user authorizes.
- Run training with stdout/stderr redirected to logs/<id>.log; parse metrics with Read, do not flood context.
- Experience: outcomes in experience/EXPERIMENT_LOG.md; bugs in experience/ERROR.md; training/model insights in experience/LEARNINGS.md.
- See references/hooks-setup.md for experiment / learnings / errors hook commands.
EOF
