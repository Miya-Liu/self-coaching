# SPDX-License-Identifier: MIT
"""Tests for the coach clock scheduler."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_COACH = REPO_ROOT / "modes" / "coach"
_SC = REPO_ROOT / "modes" / "self-coaching"
_MOCK = REPO_ROOT / "mock-services"
_MODES = REPO_ROOT / "modes"
for _entry in (str(_MODES), str(_COACH), str(_SC), str(_SC / "self-learning"), str(_MOCK), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from scheduler import ClockScheduler, AgentTickState, TickEvent, _append_tick_event  # noqa: E402

_ENV_PREFIXES = ("LOOP_", "MOCK_", "ORCHESTRATOR_", "AGENTEVALS_", "TRAINER_", "AGENT_")

REGISTRY = _COACH / "agents.clock.yaml"


@pytest.fixture(autouse=True)
def _isolate_env():
    snapshot = {k: os.environ[k] for k in list(os.environ) if k.startswith(_ENV_PREFIXES)}
    yield
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIXES) and key not in snapshot:
            del os.environ[key]
    for key, value in snapshot.items():
        os.environ[key] = value


def test_agent_tick_state_timing():
    state = AgentTickState("test-agent", interval_s=2.0)
    assert state.should_tick()  # never ticked → due immediately
    state.last_tick_at = time.time()
    assert not state.should_tick()
    assert state.time_until_next() > 1.5


def test_scheduler_registers_agents():
    scheduler = ClockScheduler(REGISTRY, tick_fn=lambda _: {"status": "mock"})
    scheduler._load_agents()
    states = scheduler.agent_states()
    assert "clock-demo-agent" in states
    assert states["clock-demo-agent"]["interval_s"] == 1800.0


def test_scheduler_start_stop():
    scheduler = ClockScheduler(REGISTRY, tick_fn=lambda _: {"status": "mock"})
    # Set a huge interval so no scheduled tick fires during the test
    scheduler.start()
    assert scheduler.running
    # Override interval to prevent auto-fire
    for state in scheduler._agents.values():
        state.interval_s = 99999
        state.last_tick_at = time.time()
    time.sleep(0.2)
    scheduler.stop(timeout=3.0)
    assert not scheduler.running


def test_scheduler_trigger_now():
    results: list[str] = []

    def mock_tick(agent_id: str) -> dict[str, Any]:
        results.append(agent_id)
        return {"status": "ok", "agent_id": agent_id}

    scheduler = ClockScheduler(REGISTRY, tick_fn=mock_tick)
    scheduler._load_agents()
    # Prevent auto-ticks
    for state in scheduler._agents.values():
        state.interval_s = 99999
        state.last_tick_at = time.time()

    result = scheduler.trigger_now("clock-demo-agent")
    assert result["status"] == "ok"
    assert "clock-demo-agent" in results


def test_scheduler_trigger_busy():
    import threading

    slow_event = threading.Event()

    def slow_tick(agent_id: str) -> dict[str, Any]:
        slow_event.wait(timeout=5)
        return {"status": "ok"}

    scheduler = ClockScheduler(REGISTRY, tick_fn=slow_tick)
    scheduler._load_agents()
    for state in scheduler._agents.values():
        state.interval_s = 99999
        state.last_tick_at = time.time()

    # Start a tick in background
    t = threading.Thread(target=scheduler.trigger_now, args=("clock-demo-agent",))
    t.start()
    time.sleep(0.1)  # Let it acquire the lock

    # Second trigger should get "busy"
    result = scheduler.trigger_now("clock-demo-agent")
    assert result["status"] == "busy"

    slow_event.set()
    t.join(timeout=3)


def test_tick_event_append(tmp_path: Path):
    event = TickEvent(
        agent_id="test-agent",
        tick_id="tick-abc",
        started_at="2026-06-16T00:00:00Z",
        finished_at="2026-06-16T00:00:05Z",
        duration_s=5.0,
        action="full_tick",
        outcome="completed",
    )
    _append_tick_event(tmp_path, event)
    log_path = tmp_path / ".self-coaching" / "coach" / "ticks" / "tick_log.jsonl"
    assert log_path.is_file()
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["agent_id"] == "test-agent"
    assert record["outcome"] == "completed"


from typing import Any  # noqa: E402
