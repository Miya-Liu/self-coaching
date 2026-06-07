# SPDX-License-Identifier: MIT
"""Unit tests for AgentEvals adapter (no live :8080 required)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.adapters.agentevals_client import AgentEvalsClient, AgentEvalsError
from services.adapters.composite_client import with_agentevals_eval
from services.adapters.eval_adapter import AgentEvalsEvalAdapter, run_detail_to_mock_report
from services.orchestrator.eval_metrics import normalize_from_agentevals

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "agentevals" / "run_detail_succeeded.json"


@pytest.fixture
def run_detail() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_normalize_from_agentevals_fixture(run_detail: dict):
    metrics = normalize_from_agentevals(
        agent_id="fallback-agent",
        run_detail=run_detail,
        baseline_score=0.9,
        skill_bundle_version="v1",
        model_checkpoint_id="ver-candidate-001",
    )
    assert metrics.run_id == "run-a1b2c3d4e5f6"
    assert metrics.agent_id == "550e8400-e29b-41d4-a716-446655440000"
    assert metrics.score == pytest.approx(0.82)
    assert metrics.baseline_score == pytest.approx(0.9)
    assert metrics.cost_per_task == pytest.approx(0.42 / 8)
    assert metrics.latency_p95_ms == pytest.approx(1200.0)
    assert metrics.safety_pass_rate == pytest.approx(1.0)
    assert "tool_use" in metrics.task_scores


def test_run_detail_to_mock_report(run_detail: dict):
    report = run_detail_to_mock_report(
        run_detail,
        candidate="ver-candidate-001",
        baseline="ver-baseline-000",
    )
    assert report["scores"]["overall"] == pytest.approx(0.82)
    assert report["run_detail"] is run_detail
    assert report["status"] == "passed"


def test_eval_adapter_evaluate_and_report(run_detail: dict, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENTEVALS_SUITE_ID", "tool-use-canary")
    client = MagicMock(spec=AgentEvalsClient)
    client.create_run.return_value = {"id": "run-a1b2c3d4e5f6"}
    client.wait_for_run.return_value = run_detail

    adapter = AgentEvalsEvalAdapter(client)
    summary = adapter.evaluate(candidate="ver-candidate-001", baseline="ver-baseline-000")
    assert summary["run_id"] == "run-a1b2c3d4e5f6"
    assert summary["_eval_backend"] == "agentevals"

    report = adapter.eval_report("run-a1b2c3d4e5f6")
    assert report["scores"]["overall"] == pytest.approx(0.82)
    client.create_run.assert_called_once()
    assert client.create_run.call_args.kwargs["suite_id"] == "tool-use-canary"


def test_eval_adapter_requires_suite_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENTEVALS_SUITE_ID", raising=False)
    adapter = AgentEvalsEvalAdapter(MagicMock())
    with pytest.raises(AgentEvalsError, match="AGENTEVALS_SUITE_ID"):
        adapter.evaluate(candidate="c1", baseline="b0")


def test_with_agentevals_eval_delegates_learn(tmp_path: Path, run_detail: dict, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENTEVALS_SUITE_ID", "tool-use-canary")
    mock_services = REPO_ROOT / "mock-services"
    if str(mock_services) not in sys.path:
        sys.path.insert(0, str(mock_services))
    import client as client_mod  # noqa: E402

    inner = client_mod.ModuleClient(root=tmp_path)
    ae = MagicMock(spec=AgentEvalsClient)
    ae.create_run.return_value = {"id": "run-a1b2c3d4e5f6"}
    ae.wait_for_run.return_value = run_detail
    ae.health.return_value = {"status": "ok"}

    wrapped = with_agentevals_eval(inner, AgentEvalsEvalAdapter(ae))
    wrapped.learn(event="test", source="unit")
    summary = wrapped.evaluate(candidate="c1", baseline="b0")
    assert summary["run_id"] == "run-a1b2c3d4e5f6"


def test_agentevals_client_wait_for_run_failed():
    client = AgentEvalsClient(base_url="http://example.invalid", poll_interval_s=0.01, poll_timeout_s=0.05)
    with patch.object(client, "get_run", return_value={"id": "r1", "status": "failed"}):
        with pytest.raises(AgentEvalsError, match="ended with status"):
            client.wait_for_run("r1")


def test_record_eval_agentevals_backend(tmp_path: Path, run_detail: dict, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "agentevals")
    monkeypatch.setenv("AGENTEVALS_SUITE_ID", "tool-use-canary")

    with patch("services.adapters.eval_adapter.AgentEvalsClient") as client_cls:
        instance = client_cls.return_value
        instance.create_run.return_value = {"id": "run-a1b2c3d4e5f6"}
        instance.wait_for_run.return_value = run_detail
        instance.health.return_value = {"status": "ok"}

        from services.orchestrator.runner import record_eval

        metrics = record_eval(
            tmp_path / "coach",
            agent_id="test-agent",
            candidate="ver-candidate-001",
            baseline="ver-baseline-000",
            baseline_score=0.9,
        )
    assert metrics.score == pytest.approx(0.82)
    assert metrics.agent_id == "550e8400-e29b-41d4-a716-446655440000"
