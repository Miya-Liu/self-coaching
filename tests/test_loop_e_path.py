# SPDX-License-Identifier: MIT
"""E-path integration tests for the self-coaching loop driver."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
MOCK_SERVICES = REPO_ROOT / "mock-services"
for _path in (SC_ROOT, SC_ROOT / "self-learning", MOCK_SERVICES):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from client import ModuleClient  # noqa: E402
from loop_driver import count_store_rows, run_tasks  # noqa: E402
from loop_store import read_jsonl  # noqa: E402
from mock_agent_registry import AgentRegistry  # noqa: E402
from state import LoopStateStore  # noqa: E402

EPATH_FIXTURE = MOCK_SERVICES / "fixtures" / "task_stream" / "e_path_v1.jsonl"
DEFAULT_FIXTURE = MOCK_SERVICES / "fixtures" / "task_stream" / "tool_use_v1.jsonl"


def _support_rows(root: Path) -> list[dict]:
    return read_jsonl(root / ".self-coaching" / "loop" / "support.jsonl")


def _buffer_rows(root: Path) -> list[dict]:
    return read_jsonl(root / ".self-coaching" / "loop" / "tuning_buffer.jsonl")


def test_e_path_triggers_after_three_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.setenv("LOOP_AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_LEARNING_URL", raising=False)

    root = tmp_path / "e-path-root"
    client = ModuleClient(root)
    learn_calls: list[dict] = []
    original_learn = client.learn

    def tracked_learn(**kwargs):
        learn_calls.append(kwargs)
        return original_learn(**kwargs)

    client.learn = tracked_learn  # type: ignore[method-assign]

    registry = AgentRegistry(root)
    registry.ensure_agent("demo-agent")
    bootstrap_version = registry.get_agent("demo-agent")["active_version_id"]

    results, state = run_tasks(
        root,
        task_stream_path=EPATH_FIXTURE,
        limit=10,
        sigma_min=3,
        sigma_play=0,
        client=client,
        agent_id="demo-agent",
    )

    assert len(results) == 10
    assert len(learn_calls) == 1
    assert learn_calls[0]["source"] == "loop-e-path"
    assert "skill patch needed" in learn_calls[0]["event"]

    assert state.tasks_processed == 10
    assert state.generation == 1
    assert state.support_count == 0
    assert state.buffer_count == 7

    support_rows = _support_rows(root)
    buffer_rows = _buffer_rows(root)
    assert len(support_rows) == 3
    assert len(buffer_rows) == 7
    assert all(row["score"] < 0.75 for row in support_rows)
    assert all(row["score"] >= 0.75 for row in buffer_rows)

    agent = registry.get_agent("demo-agent")
    assert agent["active_version_id"] != bootstrap_version
    skill_bundle = agent["version"]["components"].get("skill_bundle_version", "")
    assert skill_bundle != "skills-bootstrap"

    store = LoopStateStore(root)
    reloaded = store.load()
    assert reloaded.generation == store.registry_generation(agent_id="demo-agent") == 1


def test_exit_gate_reflects_injected_failure_rate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_LEARNING_URL", raising=False)

    root = tmp_path / "exit-gate-root"
    client = ModuleClient(root)

    _, state = run_tasks(
        root,
        task_stream_path=DEFAULT_FIXTURE,
        limit=10,
        sigma_min=3,
        sigma_play=0,
        client=client,
        agent_id="demo-agent",
    )

    support_count, buffer_count = count_store_rows(root)
    assert support_count == 6
    assert buffer_count == 1
    assert state.tasks_processed == 10
    assert state.support_count == 0
    assert state.generation == 2

    state_path = root / ".self-coaching" / "loop" / "state.json"
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["tasks_processed"] == 10
    assert on_disk["generation"] == 2
    assert on_disk["buffer_count"] == 1
    assert on_disk["support_count"] == 0


def test_learn_from_sigma_delegates_single_event():
    from loop_driver import SupportEntry, learn_from_sigma

    sigma = [
        SupportEntry(
            task_id="t1",
            trajectory_id="traj-1",
            trajectory_ref=".self-coaching/loop/trajectories/traj-1.json",
            score=0.0,
            event_text="missing tools",
        )
    ]
    client = MagicMock()
    client.learn.return_value = {"status": "ok"}

    learn_from_sigma(client, sigma)

    client.learn.assert_called_once()
    kwargs = client.learn.call_args.kwargs
    assert kwargs["source"] == "loop-e-path"
    assert kwargs["event"].startswith("skill patch needed:")
