# SPDX-License-Identifier: MIT
"""Tests for holdout eval engine factory and metrics mapping."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.adapters.agentevals_client import AgentEvalsClient
from services.adapters.holdout_engine import (
    AgentEvalsHoldoutEngine,
    build_holdout_engine,
    collect_holdout_metrics,
    holdout_poll_interval_s,
    wait_for_holdout_run,
)

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "agentevals" / "run_detail_succeeded.json"


@pytest.fixture
def run_detail() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_build_holdout_engine_mock_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "mock")
    for key in ("AGENTEVALS_BASE_URL", "MOCK_AGENTEVALS_URL"):
        monkeypatch.delenv(key, raising=False)

    engine = build_holdout_engine(tmp_path)
    from mock_agentevals import MockAgentEvalsEngine  # noqa: E402

    assert isinstance(engine, MockAgentEvalsEngine)


def test_build_holdout_engine_http_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "mock")
    monkeypatch.setenv("MOCK_AGENTEVALS_URL", "http://127.0.0.1:38180")

    engine = build_holdout_engine(tmp_path)
    assert isinstance(engine, AgentEvalsHoldoutEngine)
    assert engine._client.base_url == "http://127.0.0.1:38180"


def test_build_holdout_engine_live_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "agentevals")
    monkeypatch.setenv("AGENTEVALS_BASE_URL", "https://agentevals.example")

    engine = build_holdout_engine(tmp_path)
    assert isinstance(engine, AgentEvalsHoldoutEngine)
    assert engine._client.base_url == "https://agentevals.example"


def test_collect_holdout_metrics_from_fixture(tmp_path: Path, run_detail: dict, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENTEVALS_SUITE_ID_HOLDOUT", "tool-use-holdout")
    mock_services = REPO_ROOT / "mock-services"
    if str(mock_services) not in sys.path:
        sys.path.insert(0, str(mock_services))
    from mock_agent_registry import AgentRegistry  # noqa: E402

    registry = AgentRegistry(tmp_path)
    registry.ensure_agent("demo-agent")
    version = registry.create_version("demo-agent", components={"model_id": "model-v1"}, source="test")

    client = MagicMock(spec=AgentEvalsClient)
    client.create_run.return_value = {"id": "run-a1b2c3d4e5f6"}
    client.get_run.return_value = run_detail
    engine = AgentEvalsHoldoutEngine(tmp_path, client)

    metrics = collect_holdout_metrics(
        engine,
        agent_id="demo-agent",
        version_id=str(version["version_id"]),
        coaching_root=tmp_path,
    )

    assert metrics.run_id == "run-a1b2c3d4e5f6"
    assert metrics.score == pytest.approx(0.82)
    assert metrics.split == "holdout"
    assert metrics.model_checkpoint_id == "model-v1"
    client.create_run.assert_called_once()
    assert client.create_run.call_args.kwargs["suite_id"] == "tool-use-holdout"


def test_holdout_poll_interval_short_for_mock(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "mock")
    for key in ("AGENTEVALS_BASE_URL", "MOCK_AGENTEVALS_URL"):
        monkeypatch.delenv(key, raising=False)
    assert holdout_poll_interval_s() == pytest.approx(0.02)


def test_holdout_poll_interval_from_env_for_http(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MOCK_AGENTEVALS_URL", "http://127.0.0.1:38180")
    monkeypatch.setenv("AGENTEVALS_POLL_INTERVAL_S", "2.5")
    assert holdout_poll_interval_s() == pytest.approx(2.5)


def test_wait_for_holdout_run_succeeds(run_detail: dict):
    engine = MagicMock()
    engine.get_run.return_value = run_detail
    detail = wait_for_holdout_run(engine, "run-a1b2c3d4e5f6", timeout_s=1.0, poll_interval_s=0.001)
    assert detail["status"] == "succeeded"
