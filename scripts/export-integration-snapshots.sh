#!/usr/bin/env bash
# Export OpenAPI snapshots for Phase 0 (integration plan).
# Usage: bash scripts/export-integration-snapshots.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/docs/integration/api-snapshots"
AGENT_URL="${AGENT_API_BASE_URL:-http://10.110.158.146:8000}"
AGENTEVALS_URL="${AGENTEVALS_BASE_URL:-http://10.110.158.144:8080}"

mkdir -p "${OUT}"

_validate_json_file() {
  local dest="$1"
  # Git Bash on Windows: curl/msys use /d/... paths; Windows python.exe does not.
  local py_path="$dest"
  if command -v cygpath >/dev/null 2>&1; then
    py_path="$(cygpath -w "$dest")"
  fi
  JSON_VALIDATE_PATH="$py_path" python -c "import json, os; json.load(open(os.environ['JSON_VALIDATE_PATH'], encoding='utf-8'))"
}

fetch() {
  local url="$1" dest="$2"
  echo "==> ${url} -> ${dest}"
  curl -fsSL "${url}" -o "${dest}"
  _validate_json_file "${dest}"
  echo "    OK ($(wc -c < "${dest}" | tr -d ' ') bytes)"
}

fetch "${AGENT_URL}/openapi.json" "${OUT}/agent-openapi.json"

AGENTEVALS_OK=0
if curl -fsSL --connect-timeout 3 "${AGENTEVALS_URL}/health" >/dev/null 2>&1; then
  fetch "${AGENTEVALS_URL}/openapi.json" "${OUT}/agentevals-openapi.json"
  AGENTEVALS_OK=1
else
  echo "WARN: AgentEvals not reachable at ${AGENTEVALS_URL} — start service and re-run for agentevals-openapi.json"
fi

echo "Snapshots written under ${OUT}/"
if [[ "${AGENTEVALS_OK}" -eq 0 ]]; then
  echo "Partial export: agent-openapi.json only (AgentEvals offline)."
  exit 0
fi
