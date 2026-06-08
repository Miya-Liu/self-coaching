# SPDX-License-Identifier: MIT
"""Unit tests for mock AERL service."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mock-services"))

from mock_aerl import MockAERLEngine, _AERLHandler, train_via_http


@pytest.fixture
def engine(tmp_path: Path) -> MockAERLEngine:
    return MockAERLEngine(tmp_path / "stack")


def test_create_training_run_returns_candidate_model_id(engine: MockAERLEngine, tmp_path: Path):
    coaching = tmp_path / "coach"
    coaching.mkdir()
    curated = coaching / ".self-coaching" / "curated"
    curated.mkdir(parents=True)
    (curated / "train.jsonl").write_text(
        '{"id":"ex-1","use_for":["train"]}\n{"id":"ex-2","use_for":["train"]}\n',
        encoding="utf-8",
    )
    created = engine.create_training_run(
        {
            "pipeline_id": "sft",
            "base_model": "mock-base",
            "agent_id": "aerl-agent",
            "coaching_root": str(coaching),
        }
    )
    run_id = str(created["id"])
    deadline = time.time() + 5
    detail: dict = created
    while time.time() < deadline:
        detail = engine.get_training_run(run_id)
        if detail.get("status") == "succeeded":
            break
        time.sleep(0.05)
    assert detail["status"] == "succeeded"
    assert detail["candidate_model_id"].startswith("mock-sft-candidate-")
    assert detail["registry_version_id"]
    manifest = json.loads((coaching / ".self-coaching" / "manifests" / "training_run_manifest.json").read_text())
    assert manifest["candidate"] == detail["candidate_model_id"]


def test_run_pipeline_argv(engine: MockAERLEngine):
    log = engine.run_pipeline_argv("grpo", ["--epochs", "1"])
    assert "pipeline=grpo" in log
    assert "metric.val_loss" in log


def test_train_via_http(engine: MockAERLEngine, tmp_path: Path):
    coaching = tmp_path / "http-coach"
    coaching.mkdir()
    curated = coaching / ".self-coaching" / "curated"
    curated.mkdir(parents=True)
    (curated / "train.jsonl").write_text('{"id":"ex-1"}\n', encoding="utf-8")

    server = HTTPServer(("127.0.0.1", 0), _AERLHandler)
    server.engine = engine  # type: ignore[attr-defined]
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = train_via_http(
            f"http://127.0.0.1:{port}",
            coaching_root=coaching,
            pipeline="sft",
            base_model="mock-base",
            agent_id="http-agent",
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
    assert result["status"] == "trained"
    assert result["candidate"].startswith("mock-sft-candidate-")


def test_unsupported_pipeline_raises(engine: MockAERLEngine):
    with pytest.raises(ValueError, match="unsupported pipeline"):
        engine.create_training_run({"pipeline_id": "dpo"})
