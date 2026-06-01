#!/usr/bin/env bash
# Export OpenAPI snapshots for Phase 0 (integration plan).
# Usage: bash scripts/export-integration-snapshots.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/docs/integration/api-snapshots"
AGENT_URL="${AGENT_API_BASE_URL:-http://10.110.158.146:8000}"
AGENTEVALS_URL="${AGENTEVALS_BASE_URL:-http://localhost:8080}"

mkdir -p "${OUT}"

fetch() {
  local url="$1" dest="$2"
  echo "==> ${url} -> ${dest}"
  curl -fsSL "${url}" -o "${dest}"
  python -c "import json; json.load(open('${dest}', encoding='utf-8'))"
  echo "    OK ($(wc -c < "${dest}" | tr -d ' ') bytes)"
}

fetch "${AGENT_URL}/openapi.json" "${OUT}/agent-openapi.json"

if curl -fsSL --connect-timeout 3 "${AGENTEVALS_URL}/health" >/dev/null 2>&1; then
  fetch "${AGENTEVALS_URL}/openapi.json" "${OUT}/agentevals-openapi.json"
else
  echo "WARN: AgentEvals not reachable at ${AGENTEVALS_URL} — start service and re-run for agentevals-openapi.json"
  exit 1
fi

echo "Snapshots written under ${OUT}/"
