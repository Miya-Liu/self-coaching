# SPDX-License-Identifier: MIT
"""T-path integration tests for the self-coaching loop driver."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
MOCK_SERVICES = REPO_ROOT / "mock-services"
for _path in (SC_ROOT, SC_ROOT / "self-learning", MOCK_SERVICES, REPO_ROOT):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from client import ModuleClient  # noqa: E402
from loop_driver import run_tasks  # noqa: E402
from loop_store import LoopStore, read_jsonl  # noqa: E402
from mock_agent_registry import AgentRegistry  # noqa: E402

TPATH_FIXTURE = MOCK_SERVICES / "fixtures" / "task_stream" / "t_path_v1.jsonl"


def _active_buffer_rows(root: Path) -> list[dict]:
    return LoopStore(root).active_buffer_rows()


def test_t_path_trains_and_promotes_when_holdout_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)
    monkeypatch.delenv("MOCK_AERL_URL", raising=False)

    root = tmp_path / "t-path-promote"
    registry = AgentRegistry(root)
    registry.ensure_agent("demo-agent")
    bad = registry.create_version(
        "demo-agent",
        components={"model_id": "bad-regress-v1"},
        source="test-bad-production",
    )
    registry.activate("demo-agent", bad["version_id"])
    bootstrap_version = bad["version_id"]

    client = ModuleClient(root)
    train_calls: list[dict] = []
    original_train = client.train

    def tracked_train(**kwargs):
        train_calls.append(kwargs)
        return original_train(**kwargs)

    client.train = tracked_train  # type: ignore[method-assign]

    _, state = run_tasks(
        root,
        task_stream_path=TPATH_FIXTURE,
        limit=4,
        enable_e_path=False,
        enable_t_path=True,
        idle_after=0,
        beta=4,
        client=client,
        agent_id="demo-agent",
    )

    assert len(train_calls) >= 1
    assert registry.get_agent("demo-agent")["active_version_id"] != bootstrap_version

    buffer_rows = read_jsonl(root / ".self-coaching" / "loop" / "tuning_buffer.jsonl")
    consumed = [row for row in buffer_rows if row.get("used_for_train")]
    assert len(consumed) >= 4
    assert state.tasks_processed == 4


def test_t_path_rejects_bad_candidate_and_preserves_buffer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)
    monkeypatch.delenv("MOCK_AERL_URL", raising=False)

    root = tmp_path / "t-path-reject"
    registry = AgentRegistry(root)
    registry.ensure_agent("demo-agent")
    bootstrap_version = registry.get_agent("demo-agent")["active_version_id"]

    client = ModuleClient(root)
    _, _state = run_tasks(
        root,
        task_stream_path=TPATH_FIXTURE,
        limit=4,
        enable_e_path=False,
        enable_t_path=True,
        idle_after=0,
        beta=4,
        client=client,
        agent_id="demo-agent",
        candidate_model_id="bad-regress-v1",
    )

    assert registry.get_agent("demo-agent")["active_version_id"] == bootstrap_version
    active_rows = _active_buffer_rows(root)
    assert len(active_rows) >= 4
