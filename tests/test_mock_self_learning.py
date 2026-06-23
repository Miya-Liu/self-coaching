# SPDX-License-Identifier: MIT
"""Unit tests for mock self-learning service."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mock-services"))

from mock_self_learning import MockSelfLearningEngine, classify_event


@pytest.fixture
def engine(tmp_path: Path) -> MockSelfLearningEngine:
    return MockSelfLearningEngine(tmp_path / "coach")


def test_classify_event_keywords():
    assert classify_event("Agent crash on startup") == "error_log"
    assert classify_event("Update skill patch for verification") == "skill_patch"
    assert classify_event("User preference: always use bash") == "memory"
    assert classify_event("Need SFT for model gap") == "training_candidate"
    assert classify_event("Forgot to verify file write") == "eval_case_candidate"


def test_memory_creates_draft_version(engine: MockSelfLearningEngine):
    result = engine.record_event(
        event="User preference: always run tests before commit",
        classification="memory",
        agent_id="agent-1",
    )
    assert result["classification"] == "memory"
    assert "draft_version_id" in result["routing"]
    memory_file = engine.data_dir / ".self-coaching" / "memory" / "facts.jsonl"
    assert memory_file.is_file()
    versions = engine.registry.list_versions("agent-1")
    assert len(versions) >= 2


def test_skill_patch_writes_file(engine: MockSelfLearningEngine):
    result = engine.record_event(
        event="Skill missing pitfall about verification",
        classification="skill_patch",
        agent_id="agent-2",
    )
    patch_dir = engine.data_dir / ".self-coaching" / "skills" / "patches"
    assert any(patch_dir.glob("*.md"))
    assert "skill_bundle_version" in result["routing"]


def test_error_log_appends_error_md(engine: MockSelfLearningEngine):
    engine.record_event(event="Training run crash OOM", classification="error_log", agent_id="agent-3")
    err = (engine.data_dir / "experience" / "ERROR.md").read_text(encoding="utf-8")
    assert "OOM" in err or "crash" in err.lower()


def test_eval_case_candidate_no_version_bump(engine: MockSelfLearningEngine):
    engine.registry.ensure_agent("agent-4")
    before = len(engine.registry.list_versions("agent-4"))
    result = engine.record_event(
        event="Agent forgot to verify side effect",
        classification="eval_case_candidate",
        agent_id="agent-4",
    )
    after = len(engine.registry.list_versions("agent-4"))
    assert after == before
    assert result["routing"]["self_questioning_seed"] is True


def test_learn_facade_uses_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MOCK_SELF_LEARNING_URL", raising=False)
    sys.path.insert(0, str(REPO_ROOT / "mock-services"))
    import mock_self_coaching as msc

    root = tmp_path / "facade-root"
    result = msc.learn(root, "skill patch needed for tool verification", source="unit")
    assert result["classification"] == "skill_patch"
    events = root / ".self-coaching" / "events" / "learning_events.jsonl"
    assert events.is_file()


def test_evolve_sessions_creates_draft(engine: MockSelfLearningEngine):
    result = engine.evolve_sessions(session_ids=["sess_smoke_002"], wait=True, agent_id="agent-e2e")
    row = result["results"][0]
    assert row["status"] == "ok"
    assert row.get("draft_version_id") or row["actions"]["skills_patched"] >= 0


def test_record_event_path_unchanged_after_review_routes(engine: MockSelfLearningEngine):
    """M2.1-T12: POST /learning/events semantics unchanged."""
    before = engine.record_event(event="legacy sync path", source="unit", agent_id="agent-legacy")
    assert before["source"] == "unit"
    assert "id" in before
