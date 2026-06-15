# SPDX-License-Identifier: MIT
"""Unit tests for production-shaped self-learning review routes (M2.1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "self_learning"
sys.path.insert(0, str(REPO_ROOT / "mock-services"))

from mock_self_learning import MockSelfLearningEngine


@pytest.fixture
def engine(tmp_path: Path) -> MockSelfLearningEngine:
    return MockSelfLearningEngine(tmp_path / "coach")


def test_list_sessions_excludes_optout_by_default(engine: MockSelfLearningEngine):
    listing = engine.list_sessions(hours=24, limit=50)
    ids = {s["session_id"] for s in listing["sessions"]}
    assert "sess_smoke_001" in ids
    assert "sess_smoke_optout" not in ids


def test_list_sessions_include_optout(engine: MockSelfLearningEngine):
    listing = engine.list_sessions(hours=24, limit=50, include_optout=True)
    ids = {s["session_id"] for s in listing["sessions"]}
    assert "sess_smoke_optout" in ids


def test_evolve_sessions_sync_wait_true(engine: MockSelfLearningEngine):
    result = engine.evolve_sessions(
        session_ids=["sess_smoke_001"],
        agent_id="agent-review",
        wait=True,
    )
    assert result["status"] == "completed"
    assert len(result["results"]) == 1
    assert result["results"][0]["status"] == "ok"
    assert result["results"][0]["actions"]["skills_patched"] >= 0


def test_evolve_sessions_async_when_many_sessions(engine: MockSelfLearningEngine):
    result = engine.evolve_sessions(
        session_ids=["sess_smoke_001", "sess_smoke_002"] * 3,
        wait=False,
    )
    assert result["status"] == "queued"
    assert "job_id" in result
    assert result["poll_url"] == f"/learning/status/{result['job_id']}"
    job = engine.get_job_status(result["job_id"])
    assert job["status"] == "completed"
    assert len(job["results"]) == 6


def test_evolve_sessions_skips_optout(engine: MockSelfLearningEngine):
    engine.set_optout("sess_smoke_001", optout=True)
    result = engine.evolve_sessions(session_ids=["sess_smoke_001"], wait=True)
    assert result["results"][0]["status"] == "skipped"


def test_evolve_sessions_missing_session(engine: MockSelfLearningEngine):
    with pytest.raises(KeyError, match="session_not_found"):
        engine.evolve_sessions(session_ids=["missing_sid"], wait=True)


def test_evolve_sessions_invalid_flags(engine: MockSelfLearningEngine):
    with pytest.raises(ValueError, match="invalid_request"):
        engine.evolve_sessions(
            session_ids=["sess_smoke_001"],
            evolve_memory=False,
            evolve_skills=False,
            wait=True,
        )
    with pytest.raises(ValueError, match="invalid_request"):
        engine.evolve_sessions(session_ids=[], wait=True)


def test_evolve_recent_sync(engine: MockSelfLearningEngine):
    result = engine.evolve_recent(hours=24, max_sessions=2, wait=True)
    assert result["status"] == "completed"
    assert result["sessions_reviewed"] >= 1
    assert "window" in result


def test_evolve_recent_empty_window(engine: MockSelfLearningEngine):
    for sid in ("sess_smoke_001", "sess_smoke_002", "sess_smoke_optout"):
        engine.set_optout(sid, optout=True)
    result = engine.evolve_recent(hours=24, max_sessions=5, wait=True)
    assert result["status"] == "completed"
    assert result["sessions_reviewed"] == 0
    assert result["results"] == []


def test_get_job_status_not_found(engine: MockSelfLearningEngine):
    with pytest.raises(KeyError, match="job_not_found"):
        engine.get_job_status("learn_missing")


def test_set_optout(engine: MockSelfLearningEngine):
    out = engine.set_optout("sess_smoke_002", optout=True)
    assert out["optout"] is True
    listing = engine.list_sessions(include_optout=False)
    ids = {s["session_id"] for s in listing["sessions"]}
    assert "sess_smoke_002" not in ids


def test_fixture_shapes_match_engine(engine: MockSelfLearningEngine):
    sync = json.loads((FIXTURES / "evolve_sync_completed.json").read_text(encoding="utf-8"))
    assert sync["status"] == "completed"
    assert "results" in sync

    queued = json.loads((FIXTURES / "evolve_async_queued.json").read_text(encoding="utf-8"))
    assert queued["status"] == "queued"
    assert queued["poll_url"].startswith("/learning/status/")

    live = engine.evolve_sessions(session_ids=["sess_smoke_001"], wait=True)
    assert set(live.keys()) >= {"status", "duration_ms", "results"}
    assert live["results"][0]["session_id"] == "sess_smoke_001"
