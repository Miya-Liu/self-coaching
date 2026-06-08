# SPDX-License-Identifier: MIT
"""Unit tests for mock AgentEvals engine."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mock-services"))

from mock_agentevals import MockAgentEvalsEngine, evaluate_for_coaching_root


@pytest.fixture
def engine(tmp_path: Path) -> MockAgentEvalsEngine:
    eng = MockAgentEvalsEngine(tmp_path / "ae-data")
    eng.init_demo("test-agent")
    return eng


def _wait_succeeded(engine: MockAgentEvalsEngine, run_id: str) -> dict:
    for _ in range(50):
        detail = engine.get_run(run_id)
        if detail.get("status") == "succeeded":
            return detail
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not succeed")


def test_builtin_suites(engine: MockAgentEvalsEngine):
    suites = engine.list_suites()
    ids = {s["id"] for s in suites}
    assert "tool-use-canary" in ids
    assert "tool-use-holdout" in ids


def test_create_suite_and_run(engine: MockAgentEvalsEngine):
    suite = engine.create_suite({"name": "From failure", "task_ids": ["a", "b"]})
    summary = engine.create_run(
        {
            "suite_id": suite["id"],
            "agent_config": {"agent_id": "test-agent", "version_id": "ver-0001"},
        }
    )
    detail = _wait_succeeded(engine, str(summary["id"]))
    assert float(detail["metrics"]["overall"]) >= 0.8


def test_bad_candidate_scores_lower(engine: MockAgentEvalsEngine):
    good = engine.create_run(
        {
            "suite_id": "tool-use-canary",
            "agent_config": {"agent_id": "test-agent", "version_id": "ver-0001"},
        }
    )
    bad = engine.create_run(
        {
            "suite_id": "tool-use-canary",
            "agent_config": {"agent_id": "test-agent", "version_id": "ver-bad-regress"},
        }
    )
    g = _wait_succeeded(engine, str(good["id"]))
    b = _wait_succeeded(engine, str(bad["id"]))
    assert float(b["metrics"]["overall"]) < float(g["metrics"]["overall"])


def test_evaluate_for_coaching_root(engine: MockAgentEvalsEngine, tmp_path: Path):
    coaching = tmp_path / "coach-root"
    coaching.mkdir()
    result = evaluate_for_coaching_root(
        engine,
        candidate="ver-0001",
        baseline="ver-0001",
        suite_id="tool-use-canary",
        agent_id="test-agent",
        coaching_root=coaching,
    )
    assert result["status"] == "passed"
    report = coaching / ".self-coaching" / "reports" / "eval_runs" / result["run_id"] / "report.json"
    assert report.is_file()


def test_record_eval_with_mock_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Orchestrator record-eval against in-process engine via env (no HTTP server)."""
    data_dir = tmp_path / "orch-data"
    coaching = data_dir
    coaching.mkdir()
    (coaching / "experience").mkdir(parents=True, exist_ok=True)

    eng = MockAgentEvalsEngine(data_dir)
    eng.init_demo("orch-agent")

    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "agentevals")
    monkeypatch.setenv("AGENTEVALS_BASE_URL", "http://127.0.0.1:9")  # unused when patched
    monkeypatch.setenv("AGENTEVALS_SUITE_ID", "tool-use-canary")

    from unittest.mock import patch

    with patch("services.adapters.eval_adapter.AgentEvalsClient") as client_cls:
        instance = client_cls.return_value

        def _create_run(**kwargs):
            return eng.create_run(
                {
                    "suite_id": kwargs["suite_id"],
                    "num_trials": kwargs.get("num_trials") or 4,
                    "agent_config": kwargs["agent_config"],
                }
            )

        def _get_run(run_id: str):
            return eng.get_run(run_id)

        def _wait(run_id: str):
            return _wait_succeeded(eng, run_id)

        instance.create_run.side_effect = lambda **kw: _create_run(**kw)
        instance.get_run.side_effect = _get_run
        instance.wait_for_run.side_effect = _wait
        instance.health.return_value = {"status": "ok"}

        from services.orchestrator.runner import record_eval

        metrics = record_eval(
            coaching,
            agent_id="orch-agent",
            candidate="ver-0001",
            baseline="ver-0001",
            baseline_score=0.9,
        )

    assert metrics.score >= 0.8
    assert metrics.agent_id == "orch-agent"
