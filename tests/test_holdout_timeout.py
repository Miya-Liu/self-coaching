# SPDX-License-Identifier: MIT
"""Holdout eval timeout behavior (LOOP_HOLDOUT_TIMEOUT_S)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
MOCK_SERVICES = REPO_ROOT / "mock-services"
for _path in (SC_ROOT, MOCK_SERVICES, REPO_ROOT):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from services.adapters.holdout_engine import collect_holdout_metrics, wait_for_holdout_run  # noqa: E402


def test_wait_for_holdout_run_times_out(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOOP_HOLDOUT_TIMEOUT_S", "0.15")

    engine = MagicMock()
    engine.get_run.return_value = {"id": "run-slow", "status": "running"}

    with pytest.raises(RuntimeError, match="did not succeed within"):
        wait_for_holdout_run(engine, "run-slow", poll_interval_s=0.02)


def test_collect_holdout_metrics_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOOP_HOLDOUT_TIMEOUT_S", "0.15")
    monkeypatch.setenv("AGENTEVALS_SUITE_ID_HOLDOUT", "tool-use-holdout")

    from mock_agent_registry import AgentRegistry  # noqa: E402

    registry = AgentRegistry(tmp_path)
    registry.ensure_agent("demo-agent")
    version = registry.create_version("demo-agent", components={"model_id": "model-v1"}, source="test")

    engine = MagicMock()
    engine.registry = registry
    engine.create_run.return_value = {"id": "run-never-done"}
    engine.get_run.return_value = {"id": "run-never-done", "status": "running"}

    with pytest.raises(RuntimeError, match="did not succeed within"):
        collect_holdout_metrics(
            engine,
            agent_id="demo-agent",
            version_id=str(version["version_id"]),
            coaching_root=tmp_path,
            timeout_s=0.15,
        )
