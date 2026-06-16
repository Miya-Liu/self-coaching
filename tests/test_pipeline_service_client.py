# SPDX-License-Identifier: MIT
"""Unit tests for PipelineServiceClient (offline mock HTTP server)."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "pipeline"
sys.path.insert(0, str(REPO_ROOT))

from services.adapters.pipeline_http import PipelineHTTPError  # noqa: E402
from services.adapters.pipeline_service_client import PipelineServiceClient  # noqa: E402


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class _PipelineHandler(BaseHTTPRequestHandler):
    jobs: dict[str, dict] = {}
    poll_count: dict[str, int] = {}

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            self._send_json(200, _load("health_ok.json"))
            return
        if path.startswith("/api/pipeline/status/"):
            job_id = path.rsplit("/", 1)[-1]
            if job_id == "missing":
                self._send_json(404, {"detail": "job not found"})
                return
            job = self.jobs.get(job_id)
            if job is None:
                self._send_json(404, {"detail": "job not found"})
                return
            job_status = str(job.get("status", "")).lower()
            if job_status in {"success", "failed"}:
                self._send_json(200, job)
                return
            count = self.poll_count.get(job_id, 0)
            self.poll_count[job_id] = count + 1
            if count == 0:
                self._send_json(200, job)
                return
            self._send_json(200, _load("status_dry_run_success.json"))
            return
        if path == "/api/pipeline/tasks":
            self._send_json(200, _load("tasks_list.json"))
            return
        if path.startswith("/api/pipeline/logs/"):
            job_id = path.rsplit("/", 1)[-1]
            if job_id not in self.jobs:
                self._send_json(404, {"detail": "job not found"})
                return
            self._send_json(200, _load("logs_sample.json"))
            return
        self._send_json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/pipeline/submit":
            body = self._read_json()
            if body.get("start_stage") == 99:
                self._send_json(422, {"detail": [{"loc": ["body", "start_stage"], "msg": "out of range"}]})
                return
            pending = _load("submit_dry_run_pending.json")
            self.jobs[pending["job_id"]] = pending
            self.poll_count[pending["job_id"]] = 0
            self._send_json(200, pending)
            return
        if parsed.path == "/api/pipeline/run_sync":
            success = _load("status_dry_run_success.json")
            self.jobs[success["job_id"]] = success
            self._send_json(200, success)
            return
        self._send_json(404, {"detail": "not found"})


@pytest.fixture
def pipeline_server():
    _PipelineHandler.jobs = {}
    _PipelineHandler.poll_count = {}
    server = HTTPServer(("127.0.0.1", 0), _PipelineHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=2)


def test_health(pipeline_server: str):
    client = PipelineServiceClient(pipeline_server)
    health = client.health()
    assert health["status"] == "ok"
    assert health["version"] == "1.0.0"


def test_submit_and_wait(pipeline_server: str):
    client = PipelineServiceClient(
        pipeline_server,
        poll_interval_s=0.05,
        poll_timeout_s=5,
    )
    submitted = client.submit({"dry_run": True, "generate_tasks_limit": 1, "train_eval_flag": "eval"})
    assert submitted["status"] == "pending"
    assert submitted["job_id"]

    finished = client.wait_for_job(submitted["job_id"])
    assert finished["status"] == "success"
    assert finished["stage_results"]["1"] is True
    assert finished["stage_results"]["3"] is True


def test_list_tasks_and_logs(pipeline_server: str):
    client = PipelineServiceClient(pipeline_server)
    submitted = client.submit({"dry_run": True})
    tasks = client.list_tasks(limit=10)
    assert tasks["total"] >= 1
    assert tasks["tasks"][0]["job_id"]

    logs = client.logs(submitted["job_id"], lines=20)
    assert logs["job_id"] == submitted["job_id"]
    assert logs["logs"]


def test_run_sync(pipeline_server: str):
    client = PipelineServiceClient(pipeline_server)
    result = client.run_sync({"dry_run": True, "generate_tasks_limit": 1})
    assert result["status"] == "success"
    assert result["stage_results"]["2"] is True


def test_status_404_raises(pipeline_server: str):
    client = PipelineServiceClient(pipeline_server)
    with pytest.raises(PipelineHTTPError) as exc:
        client.status("missing")
    assert exc.value.status == 404


def test_wait_for_failed_job(pipeline_server: str):
    client = PipelineServiceClient(pipeline_server, poll_interval_s=0.05, poll_timeout_s=2)
    _PipelineHandler.jobs["failed-job"] = {
        "job_id": "failed-job",
        "status": "failed",
        "created_at": "2026-06-16T00:00:00",
        "error": "stage 2 exploded",
        "stage_results": {"1": True, "2": False, "3": False},
    }
    with pytest.raises(PipelineHTTPError, match="status='failed'"):
        client.wait_for_job("failed-job")


def test_fixture_replay_mapping():
    success = _load("status_dry_run_success.json")
    assert success["status"] == "success"
    assert all(success["stage_results"][str(i)] for i in (1, 2, 3))
