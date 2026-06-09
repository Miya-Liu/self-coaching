#!/usr/bin/env bash
# Production-readiness harness for mock self-coaching (artifact + pipeline checks).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT}/mock-services/ci-production-readiness"
rm -rf "${DATA_DIR}"
mkdir -p "${DATA_DIR}"

python "${ROOT}/mock-services/production_readiness.py" --root "${DATA_DIR}"
echo "mock-production-readiness: OK"
