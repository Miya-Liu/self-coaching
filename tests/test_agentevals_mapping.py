# SPDX-License-Identifier: MIT
"""Tests for live AgentEvals metric / agent_config mapping."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.adapters.agentevals_mapping import build_agent_config, score_from_run_metrics
from services.orchestrator.eval_metrics import normalize_from_agentevals

MEMORYARENA_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "agentevals" / "run_detail_memoryarena_succeeded.json"
)


def test_score_from_memoryarena_metrics():
    detail = json.loads(MEMORYARENA_FIXTURE.read_text(encoding="utf-8"))
    metrics = detail["metrics"]
    assert score_from_run_metrics(metrics) == pytest.approx(0.0)


def test_normalize_memoryarena_fixture():
    detail = json.loads(MEMORYARENA_FIXTURE.read_text(encoding="utf-8"))
    metrics = normalize_from_agentevals(
        agent_id="demo-agent",
        run_detail=detail,
        skill_bundle_version="v1",
        model_checkpoint_id="ver-smoke",
        split="holdout",
    )
    assert metrics.score == pytest.approx(0.0)
    assert "memoryarena-fixture-ep-alpha" in metrics.task_scores
    assert metrics.cost_per_task == pytest.approx(0.0)


def test_build_agent_config_includes_model_dict(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENTEVALS_MODEL_NAME", "gpt-4o-mini")
    cfg = build_agent_config(
        agent_id="demo-agent",
        version_id="v1",
        baseline_version_id="v0",
    )
    assert cfg["model"] == {"name": "gpt-4o-mini"}
