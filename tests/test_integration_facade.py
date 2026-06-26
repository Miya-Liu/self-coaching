"""Tests for integration.py — public facade for external callers."""

from __future__ import annotations

from pathlib import Path

import pytest

from self_coaching.integration import (
    get_loop_status,
    score_run,
    trigger_e_path,
    trigger_t_path,
)


@pytest.fixture
def coaching_root(tmp_path: Path) -> Path:
    root = tmp_path / "coaching"
    root.mkdir()
    return root


@pytest.fixture
def mock_registry(coaching_root: Path):
    """Use rivercoaching's built-in mock registry."""
    from mock_services.mock_agent_registry import AgentRegistry

    registry = AgentRegistry(coaching_root)
    registry.ensure_agent("test-agent")
    return registry


def _sample_tau(task_id: str = "task-001", success: bool = True) -> dict:
    """Minimal τ fixture."""
    if success:
        return {
            "task_id": task_id,
            "prompt": "Search for latest news",
            "user_request": "Search for latest news",
            "expected_tool_calls": ["web_search"],
            "answer_checks": [{"type": "contains", "value": "latest news"}],
            "capability": ["research"],
            "metadata": {},
        }
    else:
        return {
            "task_id": task_id,
            "prompt": "Run deploy script",
            "user_request": "Run deploy script",
            "expected_tool_calls": [],
            "answer_checks": [{"type": "contains", "value": "__coaching_run_failed__"}],
            "capability": ["shell_ops"],
            "metadata": {},
        }


def _sample_xi(success: bool = True) -> dict:
    """Minimal ξ trajectory."""
    if success:
        return {
            "task_id": "task-001",
            "messages": [
                {"role": "user", "content": "Search for latest news"},
                {"role": "assistant", "content": "Here is the latest news about..."},
            ],
            "tool_trace_summary": ["invoke web_search"],
            "final_answer": "Here is the latest news about...",
            "capability": ["research"],
        }
    else:
        return {
            "task_id": "task-002",
            "messages": [
                {"role": "user", "content": "Run deploy script"},
                {"role": "assistant", "content": "Attempting deploy..."},
            ],
            "tool_trace_summary": ["invoke shell"],
            "final_answer": "Attempting deploy...",
            "capability": ["shell_ops"],
        }


class TestScoreRun:
    def test_successful_task_routes_to_buffer(self, coaching_root: Path) -> None:
        tau = _sample_tau(success=True)
        xi = _sample_xi(success=True)

        result, routed_to = score_run(coaching_root, tau, trajectory_fn=lambda _: xi)

        assert result.score >= 0.75
        assert routed_to == "buffer"

    def test_failed_task_routes_to_support(self, coaching_root: Path) -> None:
        tau = _sample_tau(task_id="task-002", success=False)
        xi = _sample_xi(success=False)

        result, routed_to = score_run(coaching_root, tau, trajectory_fn=lambda _: xi)

        assert result.score < 0.75
        assert routed_to == "support"

    def test_state_updates_after_scoring(self, coaching_root: Path) -> None:
        tau = _sample_tau(success=True)
        xi = _sample_xi(success=True)

        score_run(coaching_root, tau, trajectory_fn=lambda _: xi)

        status = get_loop_status(coaching_root)
        assert status["tasks_processed"] == 1

    def test_multiple_scores_accumulate(self, coaching_root: Path) -> None:
        for i in range(3):
            tau = _sample_tau(task_id=f"task-{i}", success=True)
            xi = _sample_xi(success=True)
            xi["task_id"] = f"task-{i}"
            score_run(coaching_root, tau, trajectory_fn=lambda _: xi)

        status = get_loop_status(coaching_root)
        assert status["tasks_processed"] == 3
        assert status["buffer_size"] == 3


class TestGetLoopStatus:
    def test_empty_root(self, coaching_root: Path) -> None:
        status = get_loop_status(coaching_root)
        assert status["generation"] == 0
        assert status["sigma_size"] == 0
        assert status["buffer_size"] == 0
        assert status["tasks_processed"] == 0


class TestTriggerEPath:
    def test_returns_none_when_sigma_empty(self, coaching_root: Path, mock_registry) -> None:
        result = trigger_e_path(coaching_root, agent_id="test-agent", registry=mock_registry)
        assert result is None

    def test_runs_when_sigma_has_entries(self, coaching_root: Path, mock_registry) -> None:
        # Fill sigma with failures
        for i in range(3):
            tau = _sample_tau(task_id=f"fail-{i}", success=False)
            xi = _sample_xi(success=False)
            xi["task_id"] = f"fail-{i}"
            score_run(coaching_root, tau, trajectory_fn=lambda _: xi)

        status = get_loop_status(coaching_root)
        assert status["sigma_size"] == 3

        # Trigger E-path
        result = trigger_e_path(coaching_root, agent_id="test-agent", registry=mock_registry)
        assert result is not None


class TestTriggerTPath:
    def test_runs_with_buffer_entries(self, coaching_root: Path, mock_registry) -> None:
        # Fill buffer
        for i in range(4):
            tau = _sample_tau(task_id=f"good-{i}", success=True)
            xi = _sample_xi(success=True)
            xi["task_id"] = f"good-{i}"
            score_run(coaching_root, tau, trajectory_fn=lambda _: xi)

        status = get_loop_status(coaching_root)
        assert status["buffer_size"] == 4

        # Trigger T-path
        result = trigger_t_path(coaching_root, agent_id="test-agent", registry=mock_registry)
        # T-path may or may not promote depending on holdout, but should not error
        assert result is not None or result is None  # no crash is the test
