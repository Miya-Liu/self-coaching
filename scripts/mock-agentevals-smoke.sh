#!/usr/bin/env bash
# Smoke test mock AgentEvals + registry (in-process, no background server).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT}/mock-services/ci-mock-agentevals"
rm -rf "${DATA_DIR}"
mkdir -p "${DATA_DIR}"

python "${ROOT}/mock-services/mock_agentevals.py" init --data-dir "${DATA_DIR}" --agent-id ci-agent

ROOT="${ROOT}"
export ROOT
python - <<'PY'
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ["ROOT"])
sys.path.insert(0, str(ROOT / "mock-services"))

from mock_agentevals import MockAgentEvalsEngine

data = ROOT / "mock-services/ci-mock-agentevals"
engine = MockAgentEvalsEngine(data)
suite = engine.create_suite({"name": "CI Custom", "task_ids": ["t1", "t2"]})
run = engine.create_run(
    {
        "suite_id": "tool-use-canary",
        "num_trials": 4,
        "agent_config": {"agent_id": "ci-agent", "version_id": "ver-0001"},
    }
)
import time

rid = run["id"]
for _ in range(50):
    detail = engine.get_run(rid)
    if detail.get("status") == "succeeded":
        break
    time.sleep(0.05)
else:
    raise SystemExit("run did not succeed")

score = float(detail["metrics"]["overall"])
assert score >= 0.8, score
bad = engine.create_run(
    {
        "suite_id": suite["id"],
        "agent_config": {"agent_id": "ci-agent", "version_id": "ver-bad-001"},
    }
)
import time as _t

for _ in range(50):
    d2 = engine.get_run(bad["id"])
    if d2.get("status") == "succeeded":
        break
    _t.sleep(0.05)
assert float(d2["metrics"]["overall"]) < float(detail["metrics"]["overall"])
print(json.dumps({"status": "ok", "canary_score": score, "custom_suite": suite["id"]}))
PY

echo "mock-agentevals-smoke: OK"
