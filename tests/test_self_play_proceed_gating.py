# SPDX-License-Identifier: MIT
"""Proceed gating when pipeline self-play fails."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
MOCK_SERVICES = REPO_ROOT / "mock-services"
for entry in (str(SC_ROOT), str(MOCK_SERVICES), str(REPO_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from loop_config import LoopConfig  # noqa: E402
from loop_store import LoopStore, SupportEntry  # noqa: E402
from e_path import run_e_path  # noqa: E402
from t_path import run_t_path  # noqa: E402
from state import LoopState, LoopStateStore  # noqa: E402
from mock_agent_registry import AgentRegistry  # noqa: E402


def _pipeline_fail_result() -> dict:
    return {
        "status": "error",
        "proceed": False,
        "pipeline_service": True,
        "count": 0,
        "job_id": "job-fail",
        "error": "stage 2 timeout",
        "stage_results": {"1": True, "2": False, "3": False},
    }


def test_e_path_holds_when_pipeline_sparse_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "coach"
    root.mkdir()
    registry = AgentRegistry(root)
    registry.ensure_agent("demo-agent")
    loop_store = LoopStore(root)
    state_store = LoopStateStore(root)
    state = state_store.load()

    traj_path = root / "traj.json"
    traj_path.write_text('{"messages": []}', encoding="utf-8")
    sigma = [
        SupportEntry(
            task_id="t1",
            trajectory_id="tr1",
            trajectory_ref="traj.json",
            score=0.4,
            event_text="failed task",
        )
    ]

    engine = MagicMock()
    engine.generate_suite.return_value = _pipeline_fail_result()

    config = LoopConfig(selfplay_backend="pipeline")
    client = MagicMock()

    result = run_e_path(
        sigma,
        client=client,
        registry=registry,
        state=state,
        state_store=state_store,
        loop_store=loop_store,
        coaching_root=root,
        agent_id="demo-agent",
        self_play_engine=engine,
        config=config,
    )

    assert result is not None
    assert result["status"] == "held"
    assert result["reason"] == "sparse_self_play_failed"
    client.learn.assert_not_called()


def test_t_path_holds_when_pipeline_batch_fails(tmp_path: Path):
    root = tmp_path / "coach"
    root.mkdir()
    registry = AgentRegistry(root)
    registry.ensure_agent("demo-agent")
    loop_store = LoopStore(root)
    state = LoopState(generation=0)

    engine = MagicMock()
    engine.generate_batch.return_value = _pipeline_fail_result()
    config = LoopConfig(selfplay_backend="pipeline", batch_size=4)
    client = MagicMock()

    result = run_t_path(
        client=client,
        registry=registry,
        loop_store=loop_store,
        state=state,
        coaching_root=root,
        agent_id="demo-agent",
        beta=4,
        self_play_engine=engine,
        config=config,
    )

    assert result is not None
    assert result.get("held") is True
    assert "batch_self_play_failed" in result.get("gate_reasons", [])
    client.train.assert_not_called()
