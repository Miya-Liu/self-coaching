# SPDX-License-Identifier: MIT
"""Tests for the HTTP mock service.

Spawns `python mock_self_coaching.py serve` in a subprocess, waits for
/health to come up, exercises every documented endpoint, then kills it.

Endpoints (from mock-services/README.md):
  GET  /health
  POST /learning/events       {"event", "source", "capability"}
  POST /self-play/generate    {"capability", "n"}
  POST /eval/runs             {"candidate", "baseline"}
  GET  /eval/runs/{run_id}/report
  POST /training/runs         {"pipeline"}
  POST /pipeline/run-all      {"capability", "pipeline"}
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_MAIN = REPO_ROOT / "mock-services" / "mock_self_coaching.py"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(port: int, timeout: float = 15.0) -> None:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            last_err = e
            time.sleep(0.15)
    raise RuntimeError(f"mock service /health never came up on port {port}: {last_err}")


def _post(port: int, path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


@pytest.fixture
def mock_server(tmp_path: Path):
    """Yield (port, root) for a running mock HTTP server. Server is killed on teardown."""
    port = _free_port()
    root = tmp_path / "http-demo"
    # Use the same Python that's running pytest to avoid version drift.
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, str(MOCK_MAIN), "serve", "--root", str(root), "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_health(port)
        yield port, root
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)


# -------- endpoints --------

def test_health_endpoint(mock_server):
    port, _ = mock_server
    data = _get(port, "/health")
    assert data["status"] == "ok"
    assert "version" in data


def test_learning_events_post(mock_server):
    port, root = mock_server
    data = _post(port, "/learning/events", {"event": "agent skipped verification"})
    assert data["event"] == "agent skipped verification"
    assert "id" in data
    events_path = root / ".self-coaching" / "events" / "learning_events.jsonl"
    assert events_path.is_file()


def test_self_play_generate_post(mock_server):
    port, _ = mock_server
    data = _post(port, "/self-play/generate", {"capability": "tool_use", "n": 3})
    assert data["status"] == "generated"
    assert data["count"] == 3


def test_eval_runs_post_and_report_get(mock_server):
    port, _ = mock_server
    _post(port, "/self-play/generate", {"capability": "tool_use", "n": 4})
    eval_result = _post(port, "/eval/runs", {"candidate": "cand-x", "baseline": "base-x"})
    assert eval_result["status"] in ("passed", "failed")
    run_id = eval_result["run_id"]

    report = _get(port, f"/eval/runs/{run_id}/report")
    assert report["run_id"] == run_id
    assert report["candidate"] == "cand-x"
    assert "scores" in report


def test_eval_report_missing_returns_404(mock_server):
    port, _ = mock_server
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(port, "/eval/runs/does-not-exist/report")
    assert exc_info.value.code == 404


def test_training_runs_post(mock_server):
    port, _ = mock_server
    _post(port, "/self-play/generate", {"capability": "tool_use", "n": 3})
    data = _post(port, "/training/runs", {"pipeline": "sft"})
    assert data["status"] == "trained"
    assert "candidate" in data


def test_pipeline_run_all_post(mock_server):
    port, _ = mock_server
    data = _post(port, "/pipeline/run-all", {"capability": "tool_use", "pipeline": "sft"})
    assert data["status"] == "ok"
    assert "promotion_allowed" in data


def test_unknown_endpoint_returns_404(mock_server):
    port, _ = mock_server
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(port, "/no/such/path")
    assert exc_info.value.code == 404


def test_unsupported_pipeline_returns_500(mock_server):
    """train() raises SystemExit for unsupported pipelines; the HTTP handler
    catches it and returns 500 with a JSON error body."""
    port, _ = mock_server
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post(port, "/training/runs", {"pipeline": "not-a-pipeline"})
    assert exc_info.value.code == 500
    err_body = json.loads(exc_info.value.read().decode("utf-8"))
    assert "error" in err_body
    assert "type" in err_body
