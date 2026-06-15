#!/usr/bin/env bash
# Repo entrypoint — delegates to the skill-pack canonical script.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "${ROOT}/modes/self-coaching/scripts/hook-inject-learnings.sh" "$@"
