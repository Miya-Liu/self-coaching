#!/usr/bin/env bash
# Run the full deterministic mock self-coaching pipeline.
# Usage: bash scripts/mock-run-all.sh [demo-root] [pipeline]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_ROOT="${1:-${ROOT}/mock-services/demo-run}"
PIPELINE="${2:-sft}"

python "${ROOT}/mock-services/mock_self_coaching.py" run-all \
  --root "${DEMO_ROOT}" \
  --capability tool_use \
  --pipeline "${PIPELINE}"
