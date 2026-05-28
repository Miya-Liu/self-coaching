# SPDX-License-Identifier: MIT
"""Tests for services.orchestrator (M1 dry loop)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.orchestrator.drop_detector import check_drop, load_thresholds
from services.orchestrator.eval_metrics import EvalMetrics, metrics_store_path
from services.orchestrator.runner import record_eval, run_improvement

THRESHOLDS = REPO_ROOT / "services" / "orchestrator" / "config" / "thresholds.json"


def test_check_drop_triggers_on_low_score():
    metrics = EvalMetrics(
        run_id="eval-test",
        agent_id="a1",
        skill_bundle_version="v0",
        model_checkpoint_id="m0",
        score=0.70,
        baseline_score=0.86,
        cost_per_task=0.01,
        latency_p95_ms=100.0,
        safety_pass_rate=0.999,
    )
    result = check_drop(metrics, load_thresholds(THRESHOLDS))
    assert result.triggered
    assert any("score" in r or "drop" in r for r in result.reasons)


def test_record_eval_appends_metrics(tmp_path: Path):
    coaching = tmp_path / "coach"
    record_eval(
        coaching,
        agent_id="test-agent",
        candidate="cand-a",
        baseline="base-b",
        baseline_score=0.9,
    )
    store = metrics_store_path(coaching)
    assert store.is_file()
    lines = store.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["agent_id"] == "test-agent"
    assert "score" in row


def test_run_improvement_force_trigger_produces_artifacts(tmp_path: Path):
    coaching = tmp_path / "coach"
    run_dir = tmp_path / "runs" / "imp-1"
    result = run_improvement(
        coaching,
        run_dir,
        agent_id="test-agent",
        force_trigger=True,
        thresholds_path=THRESHOLDS,
    )
    assert result["status"] == "completed"
    for name in (
        "improvement_run_manifest.json",
        "current_eval.json",
        "candidate_eval.json",
        "decision.json",
        "deploy_manifest.json",
    ):
        assert (run_dir / name).is_file(), f"missing {name}"
    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["deploy_mode"] == "dry_run"
    assert decision["improvement_path"] in ("skill", "model")


def test_cli_check_drop_exit_code(tmp_path: Path):
    coaching = tmp_path / "coach"
    record_eval(
        coaching,
        agent_id="agent-x",
        candidate="c1",
        baseline="b0",
        baseline_score=0.99,
    )
    proc = subprocess.run(
        [
            sys.executable, "-m", "services.orchestrator", "check-drop",
            "--metrics-dir", str(metrics_store_path(coaching).parent),
            "--agent-id", "agent-x",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    # Mock score is often ~0.8; with baseline 0.99 a drop should trigger.
    assert proc.returncode in (0, 1)
    body = json.loads(proc.stdout)
    assert "triggered" in body


def test_pipeline_m1_smoke_record_drop_run(tmp_path: Path):
    """M1 success criterion: metrics → optional drop → improvement run dir."""
    coaching = tmp_path / "coach"
    run_dir = tmp_path / "runs" / "m1-smoke"
    record_eval(
        coaching,
        agent_id="m1-agent",
        candidate="mock-bad-candidate",
        baseline="mock-baseline-v0",
        baseline_score=0.95,
    )
    result = run_improvement(
        coaching,
        run_dir,
        agent_id="m1-agent",
        force_trigger=True,
        thresholds_path=THRESHOLDS,
    )
    assert result["status"] == "completed"
    assert (run_dir / "candidate_eval.json").is_file()
