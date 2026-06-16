# SPDX-License-Identifier: MIT
"""Extended tests for production-shaped mock AERL routes (M4.1 Slice 1–2)."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "aerl"
sys.path.insert(0, str(REPO_ROOT / "mock-services"))

from mock_aerl import (  # noqa: E402
    MetricsNotReadyError,
    MockAERLEngine,
    NotCancellableError,
    RolloutRequiredError,
    _AERLHandler,
)


@pytest.fixture
def engine(tmp_path: Path) -> MockAERLEngine:
    return MockAERLEngine(tmp_path / "stack")


@pytest.fixture
def http_server(engine: MockAERLEngine):
    server = HTTPServer(("127.0.0.1", 0), _AERLHandler)
    server.engine = engine  # type: ignore[attr-defined]
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=2)


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    import urllib.error
    import urllib.parse
    import urllib.request

    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    opener = (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if host in ("localhost", "127.0.0.1", "::1")
        else urllib.request.build_opener()
    )
    try:
        with opener.open(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"error": raw}
        return exc.code, data


def _wait_for_terminal(engine: MockAERLEngine, run_id: str, timeout_s: float = 5.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        detail = engine.get_training_run(run_id)
        if detail.get("status") in {"succeeded", "failed", "cancelled", "canceled"}:
            return detail
        time.sleep(0.02)
    raise TimeoutError(f"run {run_id} did not reach terminal status")


def test_backward_compat_fields(engine: MockAERLEngine, tmp_path: Path):
    coaching = tmp_path / "coach"
    coaching.mkdir()
    created = engine.create_training_run(
        {
            "pipeline_id": "sft",
            "base_model": "mock-base",
            "agent_id": "compat-agent",
            "coaching_root": str(coaching),
        }
    )
    detail = _wait_for_terminal(engine, str(created["id"]))
    assert detail["candidate_model_id"].startswith("mock-sft-candidate-")
    assert detail["registry_version_id"]
    assert "trainer" in detail
    assert detail["training_data"]["record_counts"] is not None


def test_grpo_requires_rollout(engine: MockAERLEngine):
    with pytest.raises(RolloutRequiredError):
        engine.create_training_run({"pipeline_id": "grpo", "base_model": "mock-base"})


def test_grpo_requires_rollout_http(http_server: str):
    code, body = _request(
        "POST",
        f"{http_server}/v1/training/runs",
        {"pipeline_id": "grpo", "base_model": "mock-base"},
    )
    assert code == 400
    assert body.get("code") == "rollout_required"


def test_phased_lifecycle(engine: MockAERLEngine, tmp_path: Path):
    coaching = tmp_path / "coach"
    coaching.mkdir()
    rollout = json.loads((FIXTURES / "rollout_validate_ok.json").read_text(encoding="utf-8"))
    created = engine.create_training_run(
        {
            "pipeline_id": "grpo",
            "base_model": "mock-base",
            "coaching_root": str(coaching),
            "rollout": rollout,
            "agent_snapshot": {"skill_bundle_version": "skills-test"},
        }
    )
    run_id = str(created["id"])
    seen_phases: list[str] = []
    deadline = time.time() + 5
    while time.time() < deadline:
        detail = engine.get_training_run(run_id)
        phase = str(detail.get("phase") or "")
        if phase and (not seen_phases or seen_phases[-1] != phase):
            seen_phases.append(phase)
        if detail.get("status") == "succeeded":
            break
        time.sleep(0.01)
    assert "data_prep" in seen_phases
    assert "rollout" in seen_phases
    assert "train" in seen_phases
    assert detail["status"] == "succeeded"
    assert detail["agent_snapshot"]["skill_bundle_version"] == "skills-test"
    assert detail.get("rollout_summary")


def test_cancel_running_and_terminal(engine: MockAERLEngine, tmp_path: Path):
    coaching = tmp_path / "coach"
    coaching.mkdir()
    created = engine.create_training_run(
        {
            "pipeline_id": "sft",
            "base_model": "mock-base",
            "coaching_root": str(coaching),
        }
    )
    run_id = str(created["id"])
    deadline = time.time() + 2
    while time.time() < deadline:
        detail = engine.get_training_run(run_id)
        if detail.get("status") == "running":
            break
        if detail.get("status") in {"succeeded", "cancelled", "failed"}:
            break
        time.sleep(0.005)
    engine.cancel_training_run(run_id)
    detail = _wait_for_terminal(engine, run_id)
    assert detail["status"] == "cancelled"

    finished = engine.create_training_run(
        {"pipeline_id": "sft", "base_model": "mock-base", "coaching_root": str(coaching)}
    )
    done = _wait_for_terminal(engine, str(finished["id"]))
    with pytest.raises(NotCancellableError):
        engine.cancel_training_run(str(done["id"]))


def test_cancel_http(http_server: str, engine: MockAERLEngine, tmp_path: Path):
    coaching = tmp_path / "coach-http"
    coaching.mkdir()
    created = engine.create_training_run(
        {"pipeline_id": "sft", "base_model": "mock-base", "coaching_root": str(coaching)}
    )
    run_id = str(created["id"])
    code, body = _request("POST", f"{http_server}/v1/training/runs/{run_id}/cancel")
    assert code == 200
    assert body["status"] == "cancelled"

    finished = engine.create_training_run(
        {"pipeline_id": "sft", "base_model": "mock-base", "coaching_root": str(coaching)}
    )
    _wait_for_terminal(engine, str(finished["id"]))
    code, body = _request("POST", f"{http_server}/v1/training/runs/{finished['id']}/cancel")
    assert code == 409
    assert body.get("code") == "not_cancellable"


def test_checkpoint_after_success(engine: MockAERLEngine, tmp_path: Path):
    coaching = tmp_path / "coach"
    coaching.mkdir()
    created = engine.create_training_run(
        {
            "pipeline_id": "sft",
            "base_model": "mock-base",
            "coaching_root": str(coaching),
        }
    )
    detail = _wait_for_terminal(engine, str(created["id"]))
    ckpt_id = detail["primary_checkpoint_id"]
    assert ckpt_id.startswith("ckpt-sft-")

    listed = engine.list_checkpoints(training_run_id=str(created["id"]))
    assert len(listed["checkpoints"]) == 1
    assert listed["checkpoints"][0]["id"] == ckpt_id

    ckpt = engine.get_checkpoint(ckpt_id)
    assert ckpt["weights"]["uri"].startswith("mock://")
    assert ckpt["weights"]["adapter_only"] is True


def test_metrics_series(engine: MockAERLEngine, tmp_path: Path):
    engine._save_run(
        {
            "id": "train-metrics-queued",
            "pipeline_id": "sft",
            "status": "queued",
            "phase": "queued",
            "progress_step": 0,
            "progress_total": 100,
        }
    )
    with pytest.raises(MetricsNotReadyError):
        engine.get_training_metrics("train-metrics-queued")

    coaching = tmp_path / "coach"
    coaching.mkdir()
    created = engine.create_training_run(
        {"pipeline_id": "sft", "base_model": "mock-base", "coaching_root": str(coaching)}
    )
    run_id = str(created["id"])
    _wait_for_terminal(engine, run_id)
    metrics = engine.get_training_metrics(run_id)
    assert "train_loss" in metrics["series"]
    assert metrics["complete"] is True


def test_reward_validate_fixtures(engine: MockAERLEngine):
    for name, expected_type in [
        ("reward_sft.jsonl", "sft"),
        ("reward_preference.jsonl", "preference"),
        ("reward_trajectory.jsonl", "trajectory_reward"),
    ]:
        path = FIXTURES / name
        result = engine.validate_rewards(
            {
                "dataset_refs": [str(path)],
                "reward_spec": {"schema_version": "reward.ic.v1"},
            }
        )
        assert result["valid"] is True
        assert result["record_counts"][expected_type] >= 1

    missing = engine.validate_rewards(
        {
            "dataset_refs": [str(FIXTURES / "missing.jsonl")],
            "reward_spec": {"schema_version": "reward.ic.v1"},
        }
    )
    assert missing["valid"] is False


def test_rollout_validate(engine: MockAERLEngine):
    ok = json.loads((FIXTURES / "rollout_validate_ok.json").read_text(encoding="utf-8"))
    assert engine.validate_rollout(ok)["valid"] is True
    bad = {"llm_proxy": {"base_url": "https://invalid-proxy.example/v1"}}
    assert engine.validate_rollout(bad)["valid"] is False


def test_list_runs_and_pipelines(engine: MockAERLEngine, tmp_path: Path):
    coaching = tmp_path / "coach"
    coaching.mkdir()
    engine.create_training_run(
        {
            "pipeline_id": "sft",
            "base_model": "mock-base",
            "agent_id": "list-agent",
            "coaching_root": str(coaching),
        }
    )
    listed = engine.list_training_runs(agent_id="list-agent", pipeline_id="sft")
    assert len(listed["runs"]) >= 1
    pipelines = engine.list_pipelines()
    ids = {p["id"] for p in pipelines["pipelines"]}
    assert ids == {"sft", "grpo"}


def test_health_and_processes(http_server: str):
    code, health = _request("GET", f"{http_server}/health")
    assert code == 200
    assert health["gpu_available"] is True
    assert "sft" in health["supported_pipelines"]

    code, schema = _request("GET", f"{http_server}/v1/rewards/schema")
    assert code == 200
    assert schema["current_version"] == "reward.ic.v1"

    code, processes = _request("GET", f"{http_server}/v1/processes")
    assert code == 200
    assert processes["processes"] == []
