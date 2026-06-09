#!/usr/bin/env bash
# CI gate for scripts/mock-self-coaching-demo.sh — exit 0 when demo + golden audit PASS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GOLDEN="${ROOT}/tests/fixtures/golden/completeness_report_full_loop.json"
REPORT="${ROOT}/mock-services/demo-loop/.self-coaching/loop/completeness_report.json"

bash "${ROOT}/scripts/mock-self-coaching-demo.sh"

if [[ ! -f "${REPORT}" ]]; then
  echo "test_mock_self_coaching_demo: missing ${REPORT}" >&2
  exit 1
fi

python -c "
import json
import sys
from pathlib import Path

def normalize(report: dict) -> dict:
    return {
        'status': report.get('status'),
        'scenario': report.get('scenario'),
        'rows': [
            {
                'id': row['id'],
                'invocation': row.get('invocation'),
                'semantic': row.get('semantic'),
            }
            for row in report.get('rows', [])
        ],
    }

root = Path(sys.argv[1])
golden_path = root / 'tests/fixtures/golden/completeness_report_full_loop.json'
report_path = root / 'mock-services/demo-loop/.self-coaching/loop/completeness_report.json'

actual = normalize(json.loads(report_path.read_text(encoding='utf-8')))
expected = normalize(json.loads(golden_path.read_text(encoding='utf-8')))

if actual != expected:
    print('completeness_report.json differs from golden:', file=sys.stderr)
    print('expected:', json.dumps(expected, indent=2), file=sys.stderr)
    print('actual:  ', json.dumps(actual, indent=2), file=sys.stderr)
    sys.exit(1)

print('test_mock_self_coaching_demo: OK (golden match)')
" "${ROOT}"
