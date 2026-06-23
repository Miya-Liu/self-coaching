# SPDX-License-Identifier: MIT
"""Tests for pipeline self-questioning loop wiring (Sprint 2)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
if str(SC_ROOT) not in sys.path:
    sys.path.insert(0, str(SC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from loop_config import LoopConfig  # noqa: E402
from loop_env import build_loop_client, build_self_questioning_engine  # noqa: E402
from self_questioning_factory import build_self_questioning_engine as factory_build  # noqa: E402


_ENV_PREFIXES = ("LOOP_", "MOCK_", "ORCHESTRATOR_", "AGENTEVALS_", "TRAINER_", "PIPELINE_", "AGENT_")


@pytest.fixture(autouse=True)
def _isolate_env():
    snapshot = {k: os.environ[k] for k in list(os.environ) if k.startswith(_ENV_PREFIXES)}
    yield
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIXES) and key not in snapshot:
            del os.environ[key]
    for key, value in snapshot.items():
        os.environ[key] = value


def test_loop_config_infers_pipeline_backend_in_live_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOOP_SERVICE_MODE", "live")
    monkeypatch.setenv("PIPELINE_SERVICE_URL", "http://pipeline.example:8001")
    config = LoopConfig.from_env()
    assert config.self_questioning_backend == "pipeline"
    assert config.pipeline_service_url == "http://pipeline.example:8001"


def test_build_self_questioning_engine_pipeline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATOR_SELF_QUESTIONING_BACKEND", "pipeline")
    monkeypatch.setenv("PIPELINE_SERVICE_URL", "http://pipeline.example:8001")
    config = LoopConfig.from_env()
    engine = factory_build(config, Path("/tmp/coach"))
    from services.adapters.self_questioning_pipeline_adapter import SelfQuestioningPipelineEngine  # noqa: E402

    assert isinstance(engine, SelfQuestioningPipelineEngine)


def test_build_loop_client_wraps_pipeline_self_questioning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATOR_SELF_QUESTIONING_BACKEND", "pipeline")
    monkeypatch.setenv("PIPELINE_SERVICE_URL", "http://127.0.0.1:59999")
    monkeypatch.setenv("ORCHESTRATOR_TRANSPORT", "module")

    client = build_loop_client(tmp_path)
    from services.adapters.composite_client import CompositeClient  # noqa: E402

    assert isinstance(client, CompositeClient)
    assert client._self_questioning is not None

    mock_engine = MagicMock()
    mock_engine.generate_batch.return_value = {
        "status": "generated",
        "proceed": True,
        "pipeline_service": True,
        "count": 2,
        "job_id": "job-x",
        "stage_results": {"1": True, "2": True, "3": True},
    }
    client._self_questioning._engine = mock_engine
    result = client.self_questioning(n=2)
    assert result["proceed"] is True
    mock_engine.generate_batch.assert_called_once()
