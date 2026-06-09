# SPDX-License-Identifier: MIT
"""Sparse failure-conditioned self-play (C06) tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
MOCK_SERVICES = REPO_ROOT / "mock-services"
for _path in (SC_ROOT, SC_ROOT / "self-learning", MOCK_SERVICES):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from client import ModuleClient  # noqa: E402
from loop_driver import run_e_path  # noqa: E402
from loop_store import LoopStore, SupportEntry, read_jsonl  # noqa: E402
from mock_agent_registry import AgentRegistry  # noqa: E402
from mock_self_play import MockSelfPlayEngine  # noqa: E402
from state import LoopStateStore  # noqa: E402

SPARSE_FIXTURE = MOCK_SERVICES / "fixtures" / "task_stream" / "sparse_play_v1.jsonl"


def test_generate_suite_runs_before_learn_and_grows_sigma(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)

    root = tmp_path / "sparse-play"
    engine = MockSelfPlayEngine(root)
    registry = AgentRegistry(root)
    registry.ensure_agent("demo-agent")

    call_order: list[str] = []
    original_suite = engine.generate_suite

    def tracked_suite(**kwargs):
        call_order.append("generate_suite")
        return original_suite(**kwargs)

    engine.generate_suite = tracked_suite  # type: ignore[method-assign]

    client = ModuleClient(root)
    original_learn = client.learn

    def tracked_learn(**kwargs):
        call_order.append("learn")
        return original_learn(**kwargs)

    client.learn = tracked_learn  # type: ignore[method-assign]

    from loop_driver import process_task

    store = LoopStateStore(root)
    loop_store = LoopStore(root)
    state = store.load()
    sigma: list[SupportEntry] = []

    for tau in __import__("loop_driver").load_task_stream(SPARSE_FIXTURE):
        version_id = str(registry.get_agent("demo-agent")["active_version_id"])
        result, _xi, support_entry = process_task(
            tau,
            loop_store=loop_store,
            generation=state.generation,
            version_id=version_id,
        )
        if support_entry is not None:
            sigma.append(support_entry)

    assert len(sigma) == 1
    run_e_path(
        sigma,
        client=client,
        registry=registry,
        state=state,
        state_store=store,
        loop_store=loop_store,
        coaching_root=root,
        agent_id="demo-agent",
        sigma_play=3,
        self_play_engine=engine,
    )

    assert call_order == ["generate_suite", "learn"]
    support_rows = read_jsonl(loop_store.support_path)
    assert len(support_rows) == 2
    assert state.generation == 1
