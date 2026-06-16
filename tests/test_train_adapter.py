# SPDX-License-Identifier: MIT
"""Tests for train adapter mapping and TrainingClient + RestClient integration."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "aerl"
sys.path.insert(0, str(REPO_ROOT / "mock-services"))
sys.path.insert(0, str(REPO_ROOT))

from mock_aerl import MockAERLEngine, _AERLHandler  # noqa: E402

from services.adapters.train_adapter import AERLTrainAdapter  # noqa: E402
from services.adapters.train_mapping import map_train_result  # noqa: E402
from services.adapters.trainer_rest_client import RestClient  # noqa: E402
from services.adapters.training_client import TrainingClient  # noqa: E402


def test_map_train_result_fixture_replay():
    run = json.loads((FIXTURES / "run_completed_sft.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((FIXTURES / "checkpoint_sft.json").read_text(encoding="utf-8"))
    result = map_train_result(
        run=run,
        checkpoint=checkpoint,
        coaching_root=None,
        pipeline="sft",
    )
    assert result["status"] == "trained"
    assert result["candidate"] == "mock-sft-candidate-def456"
    assert result["primary_checkpoint_id"] == "ckpt-sft-def456"
    assert result["weights_uri"] == "mock://train-abc123def456/weights/ckpt-sft-def456"
    assert result["trainer"]["loss_type"] == "cross_entropy"
    assert result["agent_snapshot"]["skill_bundle_version"] == "skills-fixture"


def test_train_adapter_fixture_replay_with_mocks():
    run = json.loads((FIXTURES / "run_completed_sft.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((FIXTURES / "checkpoint_sft.json").read_text(encoding="utf-8"))

    training = MagicMock(spec=TrainingClient)
    training.create_training_run.return_value = {"id": run["id"], "status": "queued"}
    training.wait_for_training_run.return_value = run
    rest = MagicMock(spec=RestClient)
    rest.get_checkpoint.return_value = checkpoint

    adapter = AERLTrainAdapter(training_client=training, rest_client=rest)
    result = adapter.train(pipeline="sft", base_model="mock-base-v1", dataset="/data/train.jsonl")
    assert result["status"] == "trained"
    assert result["weights_uri"].startswith("mock://")
    training.create_training_run.assert_called_once()
    rest.get_checkpoint.assert_called_once_with("ckpt-sft-def456")


@pytest.fixture
def http_engine(tmp_path: Path) -> MockAERLEngine:
    return MockAERLEngine(tmp_path / "stack")


@pytest.fixture
def http_server(http_engine: MockAERLEngine):
    server = HTTPServer(("127.0.0.1", 0), _AERLHandler)
    server.engine = http_engine  # type: ignore[attr-defined]
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=2)


def test_train_adapter_http_integration(http_server: str, tmp_path: Path):
    coaching = tmp_path / "coach"
    coaching.mkdir()
    curated = coaching / ".self-coaching" / "curated"
    curated.mkdir(parents=True)
    (curated / "train.jsonl").write_text('{"id":"ex-1","type":"sft"}\n', encoding="utf-8")

    training = TrainingClient(http_server, poll_interval_s=0.05, poll_timeout_s=30)
    rest = RestClient(http_server)
    adapter = AERLTrainAdapter(training_client=training, rest_client=rest)

    result = adapter.train(
        pipeline="sft",
        base_model="mock-base",
        dataset=str(curated / "train.jsonl"),
        coaching_root=str(coaching),
        agent_id="adapter-agent",
    )
    assert result["status"] == "trained"
    assert result["candidate"].startswith("mock-sft-candidate-")
    assert result["weights_uri"].startswith("mock://")
    assert result["manifest"]
    assert Path(result["manifest"]).is_file()
    assert result["primary_checkpoint_id"].startswith("ckpt-sft-")

    listed = rest.list_checkpoints(training_run_id=result["run_id"])
    assert len(listed["checkpoints"]) == 1
