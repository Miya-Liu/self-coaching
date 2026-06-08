# SPDX-License-Identifier: MIT
"""Unit tests for AERL train adapter and composite client train delegation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.adapters.aerl_client import AERLClient
from services.adapters.composite_client import CompositeClient, build_composite_client
from services.adapters.train_adapter import AERLTrainAdapter


def test_build_composite_client_aerl_train_only():
    inner = MagicMock()
    client = build_composite_client(inner, train_backend="aerl")
    assert isinstance(client, CompositeClient)
    assert client._train is not None
    assert client._eval is None


def test_composite_client_delegates_train(tmp_path: Path):
    inner = MagicMock()
    inner._root = tmp_path
    aerl = MagicMock(spec=AERLClient)
    aerl.create_training_run.return_value = {"id": "train-abc123def456"}
    aerl.wait_for_training_run.return_value = {
        "id": "train-abc123def456",
        "status": "succeeded",
        "candidate_model_id": "mock-sft-candidate-def456",
        "log_file": "/tmp/train.log",
        "registry_version_id": "ver-deadbeef",
        "metrics": {"val_loss": 0.8},
    }
    aerl.health.return_value = {"status": "ok"}

    client = CompositeClient(inner, train_adapter=AERLTrainAdapter(aerl))
    result = client.train(pipeline="sft", base_model="mock-base-v1")
    assert result["status"] == "trained"
    assert result["candidate"] == "mock-sft-candidate-def456"
    assert result["_train_backend"] == "aerl"
    inner.train.assert_not_called()

    health = client.health()
    assert health["train_backend"] == "aerl"
    assert health["aerl"]["status"] == "ok"
