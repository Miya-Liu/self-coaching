# SPDX-License-Identifier: MIT
"""Unit tests for SelfQuestioningPipelineEngine (fake client, no live network)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from services.adapters.pipeline_http import PipelineHTTPError  # noqa: E402
from services.adapters.pipeline_mapping import pipeline_job_succeeded  # noqa: E402
from services.adapters.self_questioning_pipeline_adapter import SelfQuestioningPipelineEngine  # noqa: E402


def _success_job(job_id: str = "job-ok") -> dict:
    return {
        "job_id": job_id,
        "status": "success",
        "stage_results": {"1": True, "2": True, "3": True},
        "error": None,
    }


def test_generate_batch_success_proceeds():
    client = MagicMock()
    client.submit.return_value = {"job_id": "job-batch-1", "status": "pending"}
    client.wait_for_job.return_value = _success_job("job-batch-1")

    engine = SelfQuestioningPipelineEngine(client)
    result = engine.generate_batch(coaching_root=Path("/tmp/coach"), capability="tool_use", n=4)

    assert result["status"] == "generated"
    assert result["proceed"] is True
    assert result["pipeline_service"] is True
    assert result["job_id"] == "job-batch-1"
    assert result["count"] == 4
    assert pipeline_job_succeeded(result)
    client.submit.assert_called_once()
    body = client.submit.call_args[0][0]
    assert body["generate_tasks_limit"] == 4
    assert body["train_eval_flag"] == "train"


def test_generate_batch_failure_holds_loop():
    client = MagicMock()
    client.submit.return_value = {"job_id": "job-fail", "status": "pending"}
    client.wait_for_job.side_effect = PipelineHTTPError(
        "pipeline job job-fail ended with status='failed'",
        body={"job_id": "job-fail", "status": "failed", "error": "stage 2 timeout"},
    )

    engine = SelfQuestioningPipelineEngine(client)
    result = engine.generate_batch(n=2)

    assert result["status"] == "error"
    assert result["proceed"] is False
    assert result["count"] == 0
    assert not pipeline_job_succeeded(result)


def test_generate_suite_success_registered():
    client = MagicMock()
    client.submit.return_value = {"job_id": "job-suite", "status": "pending"}
    client.wait_for_job.return_value = _success_job("job-suite")

    engine = SelfQuestioningPipelineEngine(client)
    result = engine.generate_suite(n_variants=3, user_query="failed task")

    assert result["status"] == "registered"
    assert result["proceed"] is True
    assert result["count"] == 3
    body = client.submit.call_args[0][0]
    assert body["train_eval_flag"] == "eval"
    assert body["generate_tasks_limit"] == 3


def test_partial_stage_failure_maps_to_error():
    client = MagicMock()
    client.submit.return_value = {"job_id": "job-partial", "status": "pending"}
    client.wait_for_job.return_value = {
        "job_id": "job-partial",
        "status": "success",
        "stage_results": {"1": True, "2": False, "3": False},
        "error": None,
    }

    engine = SelfQuestioningPipelineEngine(client)
    result = engine.generate_batch(n=1)

    assert result["status"] == "error"
    assert result["proceed"] is False


def test_sync_mode_uses_run_sync(monkeypatch: pytest.MonkeyPatch):
    client = MagicMock()
    client.run_sync.return_value = _success_job("sync-job")

    engine = SelfQuestioningPipelineEngine(client, use_sync=True)
    result = engine.generate_batch(n=1)

    assert result["proceed"] is True
    client.run_sync.assert_called_once()
    client.submit.assert_not_called()
