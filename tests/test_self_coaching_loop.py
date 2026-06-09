# SPDX-License-Identifier: MIT
"""Unit tests for mock-services/self_coaching_loop.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_SERVICES = REPO_ROOT / "mock-services"
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
for _path in (SC_ROOT, SC_ROOT / "self-learning", MOCK_SERVICES, REPO_ROOT):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from self_coaching_loop import load_scenario, run_scenario  # noqa: E402
from state import LoopStateStore  # noqa: E402


def test_run_scenario_full_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)
    monkeypatch.delenv("MOCK_SELF_LEARNING_URL", raising=False)
    monkeypatch.delenv("MOCK_AERL_URL", raising=False)

    root = tmp_path / "loop-run"
    scenario = load_scenario(REPO_ROOT / "scenarios" / "full_loop.json")
    summary = run_scenario(root, scenario)

    assert summary["scenario"] == "full_loop"
    assert summary["generation_after"] >= 1
    assert summary["version_count"] >= 2
    assert summary["t_path_promoted"] is True

    state = LoopStateStore(root).load()
    assert state.generation >= 1
    assert (root / ".self-coaching" / "loop" / "demo_summary.md").is_file()


def test_load_scenario_resolves_repo_relative_paths():
    scenario = load_scenario(REPO_ROOT / "scenarios" / "full_loop.json")
    assert scenario["name"] == "full_loop"
    assert "task_streams" in scenario
