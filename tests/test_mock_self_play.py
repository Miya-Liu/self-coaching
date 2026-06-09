# SPDX-License-Identifier: MIT
"""Unit tests for mock self-play service."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mock-services"))

from mock_self_play import MockSelfPlayEngine


@pytest.fixture
def engine(tmp_path: Path) -> MockSelfPlayEngine:
    return MockSelfPlayEngine(tmp_path / "coach")


def test_registered_suite_runs_in_agentevals(engine: MockSelfPlayEngine):
    result = engine.generate_suite(
        user_query="Verify config.yaml exists after write",
        trajectory={
            "messages": [
                {"role": "user", "content": "Write and verify config.yaml"},
                {"role": "assistant", "content": "Done."},
            ],
        },
        eval_score=0.4,
        agent_id="suite-run-agent",
    )
    suite_id = result["suite_id"]
    created = engine.agentevals.create_run(
        {
            "suite_id": suite_id,
            "agent_config": {"agent_id": "suite-run-agent", "version_id": "ver-0001"},
            "num_trials": 2,
        }
    )
    import time

    run_id = str(created["id"])
    for _ in range(50):
        detail = engine.agentevals.get_run(run_id)
        if detail.get("status") == "succeeded":
            assert float(detail["metrics"]["overall"]) > 0
            return
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not succeed")


def test_generate_suite_registers_suite_and_curates(engine: MockSelfPlayEngine):
    result = engine.generate_suite(
        user_query="Create config.yaml and verify it exists",
        trajectory={
            "messages": [
                {"role": "user", "content": "Create config.yaml and verify"},
                {"role": "assistant", "content": "Done, file created."},
            ],
            "tool_trace_summary": ["write file"],
        },
        eval_score=0.35,
        agent_id="play-agent",
        mode="adversarial",
    )
    assert result["status"] == "registered"
    assert result["suite_id"]
    assert result["curation"]["counts"]["train"] >= 0
    root = engine.data_dir
    assert (root / ".self-coaching" / "cases" / "self_play_candidates.jsonl").is_file()
    assert (root / ".self-coaching" / "curated" / "train.jsonl").is_file()
    assert (root / ".self-coaching" / "curated" / "validation.jsonl").is_file()
    assert (root / ".self-coaching" / "curated" / "holdout.jsonl").is_file()
    suites = engine.agentevals.list_suites()
    assert any(s["id"] == result["suite_id"] for s in suites)


def test_generate_batch_legacy(engine: MockSelfPlayEngine):
    events = engine.data_dir / ".self-coaching" / "events"
    events.mkdir(parents=True, exist_ok=True)
    events.joinpath("learning_events.jsonl").write_text(
        '{"id":"learn-x","event":"verification failure","source":"test"}\n',
        encoding="utf-8",
    )
    result = engine.generate_batch(capability="tool_use", n=3)
    assert result["count"] == 3
    assert result["suite_id"]
    assert result["curation"]["status"] == "ok"


def test_self_play_facade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)
    sys.path.insert(0, str(REPO_ROOT / "mock-services"))
    import mock_self_coaching as msc

    root = tmp_path / "facade"
    result = msc.self_play(root, capability="tool_use", n=2)
    assert result["count"] == 2
    assert (root / ".self-coaching" / "curated" / "validation.jsonl").is_file()


def test_orchestrator_run_uses_curation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    coaching = tmp_path / "orch"
    coaching.mkdir()
    (coaching / "experience").mkdir()
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "data").mkdir()

    monkeypatch.setenv("ORCHESTRATOR_TRANSPORT", "module")

    from services.orchestrator.runner import run_improvement

    manifest = run_improvement(
        coaching,
        run_dir=run_dir,
        agent_id="orch-agent",
        force_trigger=True,
    )
    assert manifest["improvement_run_id"]
    import json

    curation = json.loads((run_dir / "data" / "curation.json").read_text(encoding="utf-8"))
    assert curation["status"] == "ok"
    assert "curation" in curation
    assert curation.get("agentevals_suite_id")
