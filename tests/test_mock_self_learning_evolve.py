# SPDX-License-Identifier: MIT
"""Mock self-learning evolve endpoint tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_SERVICES = REPO_ROOT / "mock-services"
if str(MOCK_SERVICES) not in sys.path:
    sys.path.insert(0, str(MOCK_SERVICES))

from mock_self_learning import MockSelfLearningEngine  # noqa: E402


def test_evolve_sessions_sync_creates_skill_patch(tmp_path: Path) -> None:
    engine = MockSelfLearningEngine(tmp_path)
    engine.registry.ensure_agent("demo-agent")
    result = engine.evolve_sessions(
        coaching_root=tmp_path,
        session_ids=["sess_smoke_002"],
        agent_id="demo-agent",
        wait=True,
    )
    assert result["status"] == "completed"
    assert len(result["results"]) == 1
    assert result["results"][0]["status"] == "ok"
    assert result["results"][0]["actions"]["skills_patched"] == 1


def test_evolve_sessions_rejects_missing_session(tmp_path: Path) -> None:
    engine = MockSelfLearningEngine(tmp_path)
    with pytest.raises(KeyError, match="session_not_found"):
        engine.evolve_sessions(session_ids=["sess_missing"], wait=True)


def test_evolve_recent_async_returns_job_id(tmp_path: Path) -> None:
    engine = MockSelfLearningEngine(tmp_path)
    engine.registry.ensure_agent("demo-agent")
    result = engine.evolve_recent(
        coaching_root=tmp_path,
        hours=24,
        max_sessions=1,
        agent_id="demo-agent",
        wait=False,
    )
    assert result["status"] == "queued"
    job_id = result["job_id"]
    status = engine.get_job_status(job_id)
    assert status["status"] == "completed"
    assert status["sessions_reviewed"] == 1
