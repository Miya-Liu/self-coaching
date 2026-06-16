# SPDX-License-Identifier: MIT
"""M2.4 / P5 smoke: run the full loop demo with LOOP_SERVICE_MODE=mock-http.

This test starts 4 mock HTTP services (AgentEvals, Self-Learning, Self-Play,
AERL), runs the demo loop against them, and asserts the completeness matrix
passes — proving the split-stack HTTP path works end-to-end.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_SERVICES = REPO_ROOT / "mock-services"
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"

for _entry in (str(MOCK_SERVICES), str(SC_ROOT), str(SC_ROOT / "self-learning"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

_ENV_PREFIXES = ("LOOP_", "MOCK_", "ORCHESTRATOR_", "AGENTEVALS_", "TRAINER_", "AGENT_", "SELF_LEARNING_")


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot and restore env to prevent leaks."""
    snapshot = {k: os.environ[k] for k in list(os.environ) if k.startswith(_ENV_PREFIXES)}
    yield
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIXES) and key not in snapshot:
            del os.environ[key]
    for key, value in snapshot.items():
        os.environ[key] = value


def test_demo_mock_http_completeness():
    """Full loop demo with --with-http passes completeness matrix (C01–C18)."""
    demo_script = REPO_ROOT / "scripts" / "mock_self_coaching_demo.py"
    env = os.environ.copy()
    # Give holdout eval more time over HTTP (default 5s is tight on Windows)
    env["LOOP_HOLDOUT_TIMEOUT_S"] = "30"
    result = subprocess.run(
        [sys.executable, str(demo_script), "--with-http"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
        env=env,
    )

    # Print output for debugging on failure
    if result.returncode != 0:
        print("STDOUT:", result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        print("STDERR:", result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)

    assert result.returncode == 0, f"demo --with-http failed:\n{result.stderr[-500:]}"
    assert "completeness: PASS" in result.stdout

    # Verify completeness report artifact exists
    report_path = MOCK_SERVICES / "demo-loop" / ".self-coaching" / "loop" / "completeness_report.json"
    assert report_path.is_file(), f"missing {report_path}"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
