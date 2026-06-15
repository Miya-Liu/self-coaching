#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
[self-coaching reminder]
- Run training via scripts/run-pipeline.sh or python -m self_coaching.demo; redirect stdout/stderr to logs/<id>.log.
- Parse metrics from log files with Read (small ranges); do not flood context with full train output.
- Experience: outcomes in experience/EXPERIMENT_LOG.md; bugs in experience/ERROR.md; insights in experience/LEARNINGS.md.
- Promote model or skill changes only after eval gates and explicit user approval.
- See references/hooks-setup.md for experiment / learnings / errors hook commands.
EOF
