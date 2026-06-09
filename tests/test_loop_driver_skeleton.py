# SPDX-License-Identifier: MIT
"""Skeleton loop driver tests for P0 task-stream consumption."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
for _path in (SC_ROOT, SC_ROOT / "self-learning"):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from loop_driver import route_score, run_tasks  # noqa: E402
from state import LoopState, LoopStateStore  # noqa: E402

FIXTURE_PATH = REPO_ROOT / "mock-services" / "fixtures" / "task_stream" / "tool_use_v1.jsonl"


def test_route_score_threshold():
    assert route_score(1.0) == "buffer"
    assert route_score(0.75) == "buffer"
    assert route_score(0.5) == "support"
    assert route_score(0.0) == "support"


def test_run_ten_fixture_tasks_updates_state(tmp_path: Path):
    results, state = run_tasks(
        tmp_path,
        task_stream_path=FIXTURE_PATH,
        limit=10,
        enable_e_path=False,
    )

    assert len(results) == 10
    assert state.tasks_processed == 10
    for result in results:
        assert 0.0 <= result.score <= 1.0
        assert result.routed_to in {"support", "buffer"}

    store = LoopStateStore(tmp_path)
    reloaded = store.load()
    assert reloaded.tasks_processed == 10
    assert reloaded.support_count + reloaded.buffer_count == 10
    assert reloaded.generation == 0

    state_path = tmp_path / ".self-coaching" / "loop" / "state.json"
    assert state_path.is_file()
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["tasks_processed"] == 10


def test_state_round_trip(tmp_path: Path):
    store = LoopStateStore(tmp_path)
    store.save(
        LoopState(
            generation=2,
            support_count=3,
            buffer_count=7,
            tasks_processed=10,
        )
    )
    loaded = store.load()
    assert loaded.generation == 2
    assert loaded.support_count == 3
    assert loaded.buffer_count == 7
    assert loaded.tasks_processed == 10
