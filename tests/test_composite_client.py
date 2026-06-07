# SPDX-License-Identifier: MIT
"""Unit tests for CompositeClient (integration Phase 2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.adapters.composite_client import CompositeClient, build_composite_client
from services.adapters.eval_adapter import AgentEvalsEvalAdapter
from services.adapters.agentevals_client import AgentEvalsClient

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "agentevals" / "run_detail_succeeded.json"


def test_build_composite_client_mock_passthrough():
    inner = MagicMock()
    client = build_composite_client(inner, eval_backend="mock")
    assert client is inner


def test_composite_client_delegates_non_eval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENTEVALS_SUITE_ID", "tool-use-canary")
    mock_services = REPO_ROOT / "mock-services"
    if str(mock_services) not in sys.path:
        sys.path.insert(0, str(mock_services))
    import client as client_mod  # noqa: E402

    inner = client_mod.ModuleClient(root=tmp_path)
    run_detail = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ae = MagicMock(spec=AgentEvalsClient)
    ae.create_run.return_value = {"id": "run-a1b2c3d4e5f6"}
    ae.wait_for_run.return_value = run_detail
    ae.health.return_value = {"status": "ok"}

    client = CompositeClient(inner, AgentEvalsEvalAdapter(ae))
    learn = client.learn(event="evt", source="unit")
    assert isinstance(learn, dict)
    assert learn.get("event_id") or learn.get("id")

    summary = client.evaluate(candidate="c1", baseline="b0")
    assert summary["run_id"] == "run-a1b2c3d4e5f6"
    assert summary["_eval_backend"] == "agentevals"

    health = client.health()
    assert health["eval_backend"] == "agentevals"
    assert health["agentevals"]["status"] == "ok"
