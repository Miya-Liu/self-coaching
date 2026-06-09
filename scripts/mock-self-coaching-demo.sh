#!/usr/bin/env bash
# Self-coaching loop demo — thin wrapper around cross-platform Python driver.
#
# Usage:
#   bash scripts/mock-self-coaching-demo.sh            # module transport (default)
#   bash scripts/mock-self-coaching-demo.sh --with-http
#
# Windows (no bash): python scripts/mock_self_coaching_demo.py
#   or:  powershell -File scripts/mock-self-coaching-demo.ps1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python "${ROOT}/scripts/mock_self_coaching_demo.py" "$@"
