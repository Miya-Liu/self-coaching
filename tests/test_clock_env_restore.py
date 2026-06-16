# SPDX-License-Identifier: MIT
"""Test that clock.run_tick restores AGENT_ID env vars after execution."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "mock-services"), str(REPO_ROOT), str(REPO_ROOT / "modes" / "self-coaching"), str(REPO_ROOT / "modes" / "self-coaching" / "self-learning"), str(REPO_ROOT / "modes" / "coach")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

_ENV_PREFIXES = ("LOOP_", "MOCK_", "ORCHESTRATOR_", "AGENTEVALS_", "TRAINER_", "AGENT_")


@pytest.fixture(autouse=True)
def _isolate_env():
    snapshot = {k: os.environ[k] for k in list(os.environ) if k.startswith(_ENV_PREFIXES)}
    yield
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIXES) and key not in snapshot:
            del os.environ[key]
    for key, value in snapshot.items():
        os.environ[key] = value


def test_run_tick_restores_agent_id(tmp_path: Path) -> None:
    """After run_tick completes, AGENT_ID is restored to its previous value."""
    from coach.clock import run_tick, load_scenario

    # Set a sentinel value
    os.environ["AGENT_ID"] = "sentinel-before-tick"
    os.environ["LOOP_AGENT_ID"] = "sentinel-before-tick"

    scenario = load_scenario(REPO_ROOT / "scenarios" / "clock_loop.json")
    coaching_root = tmp_path / "clock-test"

    # run_tick should set AGENT_ID to scenario agent then restore
    run_tick(coaching_root, scenario)

    assert os.environ.get("AGENT_ID") == "sentinel-before-tick"
    assert os.environ.get("LOOP_AGENT_ID") == "sentinel-before-tick"


def test_run_tick_restores_when_agent_id_unset(tmp_path: Path) -> None:
    """After run_tick, if AGENT_ID wasn't set before, it's removed."""
    from coach.clock import run_tick, load_scenario

    os.environ.pop("AGENT_ID", None)
    os.environ.pop("LOOP_AGENT_ID", None)

    scenario = load_scenario(REPO_ROOT / "scenarios" / "clock_loop.json")
    coaching_root = tmp_path / "clock-test-unset"

    run_tick(coaching_root, scenario)

    assert "AGENT_ID" not in os.environ
    assert "LOOP_AGENT_ID" not in os.environ
