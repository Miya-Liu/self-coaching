# SPDX-License-Identifier: MIT
"""Smoke test for the meta-eval comparison script."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "modes"))
sys.path.insert(0, str(REPO_ROOT / "modes" / "coach"))
sys.path.insert(0, str(REPO_ROOT / "modes" / "self-coaching"))
sys.path.insert(0, str(REPO_ROOT / "modes" / "self-coaching" / "self-learning"))
sys.path.insert(0, str(REPO_ROOT / "mock-services"))
sys.path.insert(0, str(REPO_ROOT))

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


def test_meta_eval_runs_and_produces_report():
    from meta_eval_coach import run_meta_eval

    result = run_meta_eval(n_ticks=2)
    assert result["n_ticks"] == 2
    assert result["winner"] in ("baseline", "candidate", "tie")
    assert result["baseline"]["ticks_total"] == 2
    assert result["candidate"]["ticks_total"] == 2
    assert result["baseline"]["generations_promoted"] >= 0
    assert result["candidate"]["generations_promoted"] >= 0
    assert "velocity_delta" in result
    assert "efficiency_delta" in result


def test_meta_eval_candidate_at_least_matches_baseline():
    """The smart heuristic should not perform worse than blanket full_tick."""
    from meta_eval_coach import run_meta_eval

    result = run_meta_eval(n_ticks=3)
    # The heuristic is designed to be at least as good; if it's worse something broke.
    assert result["candidate"]["generation_velocity"] >= result["baseline"]["generation_velocity"]
