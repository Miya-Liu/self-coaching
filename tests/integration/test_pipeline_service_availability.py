# SPDX-License-Identifier: MIT
"""Live availability probes for the Pipeline Service (opt-in).

Set PIPELINE_INTEGRATION_TESTS=1 to run against PIPELINE_SERVICE_URL.
Uses dry_run only — no GPU/LLM work.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.adapters.pipeline_http import PipelineHTTPError  # noqa: E402
from services.adapters.pipeline_service_client import PipelineServiceClient  # noqa: E402

INTEGRATION_ENABLED = os.environ.get("PIPELINE_INTEGRATION_TESTS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}
DEFAULT_BASE_URL = "http://10.110.158.146:8001"
TIMEOUT_S = float(os.environ.get("PIPELINE_INTEGRATION_TIMEOUT_S", "30"))


def _client() -> PipelineServiceClient:
    base_url = os.environ.get("PIPELINE_SERVICE_URL", DEFAULT_BASE_URL)
    return PipelineServiceClient(base_url, timeout_s=TIMEOUT_S, poll_interval_s=1.0, poll_timeout_s=60)


pytestmark = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="set PIPELINE_INTEGRATION_TESTS=1 to run live pipeline probes",
)


class TestPipelineServiceHealth:
    def test_health_endpoint(self):
        health = _client().health()
        assert health["status"] == "ok"
        assert "version" in health

    def test_openapi_available(self):
        import urllib.request

        base = os.environ.get("PIPELINE_SERVICE_URL", DEFAULT_BASE_URL).rstrip("/")
        with urllib.request.urlopen(f"{base}/openapi.json", timeout=TIMEOUT_S) as resp:
            assert resp.status == 200


class TestPipelineServiceContract:
    def test_submit_dry_run(self):
        client = _client()
        submitted = client.submit(
            {"dry_run": True, "generate_tasks_limit": 1, "train_eval_flag": "eval"},
        )
        assert submitted["job_id"]
        assert submitted["status"] in {"pending", "running", "success", "failed"}

    def test_status_poll_after_dry_run(self):
        client = _client()
        submitted = client.submit(
            {"dry_run": True, "generate_tasks_limit": 1, "train_eval_flag": "eval"},
        )
        finished = client.wait_for_job(submitted["job_id"])
        assert finished["status"] == "success"
        assert "stage_results" in finished
        assert finished["stage_results"]["1"] is True

    def test_tasks_list(self):
        data = _client().list_tasks(limit=5)
        assert "tasks" in data
        assert "total" in data
        assert isinstance(data["tasks"], list)

    def test_logs_after_dry_run(self):
        client = _client()
        submitted = client.submit({"dry_run": True, "generate_tasks_limit": 1})
        client.wait_for_job(submitted["job_id"])
        logs = client.logs(submitted["job_id"], lines=50)
        assert logs["job_id"] == submitted["job_id"]
        assert logs["logs"]

    def test_invalid_job_returns_404(self):
        with pytest.raises(PipelineHTTPError) as exc:
            _client().status("nonexistent_id")
        assert exc.value.status == 404

    def test_validation_error_returns_422(self):
        with pytest.raises(PipelineHTTPError) as exc:
            _client().submit({"start_stage": 99})
        assert exc.value.status == 422


@pytest.mark.skipif(
    os.environ.get("PIPELINE_INTEGRATION_SMOKE_SYNC", "").strip().lower() not in {"1", "true", "yes"},
    reason="set PIPELINE_INTEGRATION_SMOKE_SYNC=1 for blocking run_sync smoke",
)
class TestPipelineServiceSmoke:
    def test_sync_dry_run(self):
        result = _client().run_sync(
            {"dry_run": True, "generate_tasks_limit": 1, "train_eval_flag": "eval"},
            timeout_s=120,
        )
        assert result["status"] in {"success", "failed"}
        if result["status"] == "success":
            assert result["stage_results"]["1"] is True
