# SPDX-License-Identifier: MIT
"""T-path integration tests for the self-coaching loop driver."""

from __future__ import annotations

import sys
import threading
import time
from http.server import HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
MOCK_SERVICES = REPO_ROOT / "mock-services"
for _path in (SC_ROOT, SC_ROOT / "self-learning", MOCK_SERVICES, REPO_ROOT):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from client import ModuleClient  # noqa: E402
from loop_config import LoopConfig  # noqa: E402
from loop_driver import run_tasks  # noqa: E402
from loop_env import build_loop_client  # noqa: E402
from loop_store import LoopStore, read_jsonl  # noqa: E402
from mock_agent_registry import AgentRegistry  # noqa: E402
from mock_aerl import MockAERLEngine, _AERLHandler  # noqa: E402

TPATH_FIXTURE = MOCK_SERVICES / "fixtures" / "task_stream" / "t_path_v1.jsonl"


def _active_buffer_rows(root: Path) -> list[dict]:
    return LoopStore(root).active_buffer_rows()


def _mock_holdout_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "mock")
    for key in ("AGENTEVALS_BASE_URL", "MOCK_AGENTEVALS_URL"):
        monkeypatch.delenv(key, raising=False)


def test_t_path_trains_and_promotes_when_holdout_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)
    monkeypatch.delenv("MOCK_AERL_URL", raising=False)
    _mock_holdout_env(monkeypatch)

    root = tmp_path / "t-path-promote"
    registry = AgentRegistry(root)
    registry.ensure_agent("demo-agent")
    bad = registry.create_version(
        "demo-agent",
        components={"model_id": "bad-regress-v1"},
        source="test-bad-production",
    )
    registry.activate("demo-agent", bad["version_id"])
    bootstrap_version = bad["version_id"]

    client = ModuleClient(root)
    train_calls: list[dict] = []
    original_train = client.train

    def tracked_train(**kwargs):
        train_calls.append(kwargs)
        return original_train(**kwargs)

    client.train = tracked_train  # type: ignore[method-assign]

    _, state = run_tasks(
        root,
        task_stream_path=TPATH_FIXTURE,
        limit=4,
        enable_e_path=False,
        enable_t_path=True,
        idle_after=0,
        beta=4,
        client=client,
        agent_id="demo-agent",
    )

    assert len(train_calls) >= 1
    assert registry.get_agent("demo-agent")["active_version_id"] != bootstrap_version

    buffer_rows = read_jsonl(root / ".self-coaching" / "loop" / "tuning_buffer.jsonl")
    consumed = [row for row in buffer_rows if row.get("used_for_train")]
    assert len(consumed) >= 4
    assert state.tasks_processed == 4


def test_t_path_rejects_bad_candidate_and_preserves_buffer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)
    monkeypatch.delenv("MOCK_AERL_URL", raising=False)
    _mock_holdout_env(monkeypatch)

    root = tmp_path / "t-path-reject"
    registry = AgentRegistry(root)
    registry.ensure_agent("demo-agent")
    bootstrap_version = registry.get_agent("demo-agent")["active_version_id"]

    client = ModuleClient(root)
    _, _state = run_tasks(
        root,
        task_stream_path=TPATH_FIXTURE,
        limit=4,
        enable_e_path=False,
        enable_t_path=True,
        idle_after=0,
        beta=4,
        client=client,
        agent_id="demo-agent",
        candidate_model_id="bad-regress-v1",
    )

    assert registry.get_agent("demo-agent")["active_version_id"] == bootstrap_version
    active_rows = _active_buffer_rows(root)
    assert len(active_rows) >= 4


@pytest.fixture
def aerl_http_server(tmp_path: Path):
    engine = MockAERLEngine(tmp_path / "aerl-stack")
    server = HTTPServer(("127.0.0.1", 0), _AERLHandler)
    server.engine = engine  # type: ignore[attr-defined]
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", engine
    server.shutdown()
    thread.join(timeout=2)


def test_t_path_trains_via_aerl_http_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    aerl_http_server: tuple[str, MockAERLEngine],
):
    aerl_url, _engine = aerl_http_server
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "mock")
    monkeypatch.setenv("ORCHESTRATOR_TRAIN_BACKEND", "aerl")
    monkeypatch.setenv("ORCHESTRATOR_TRANSPORT", "module")
    monkeypatch.setenv("TRAINER_BASE_URL", aerl_url)
    monkeypatch.setenv("MOCK_AERL_URL", aerl_url)
    monkeypatch.setenv("AERL_POLL_INTERVAL_S", "0.05")
    monkeypatch.setenv("AERL_TIMEOUT_S", "30")
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)
    for key in ("AGENTEVALS_BASE_URL", "MOCK_AGENTEVALS_URL"):
        monkeypatch.delenv(key, raising=False)

    root = tmp_path / "t-path-aerl-http"
    registry = AgentRegistry(root)
    registry.ensure_agent("demo-agent")
    bad = registry.create_version(
        "demo-agent",
        components={"model_id": "bad-regress-v1"},
        source="test-bad-production",
    )
    registry.activate("demo-agent", bad["version_id"])
    bootstrap_version = bad["version_id"]

    config = LoopConfig.from_env()
    client = build_loop_client(root, config=config)
    assert hasattr(client, "_train")
    assert client._train is not None

    _, state = run_tasks(
        root,
        task_stream_path=TPATH_FIXTURE,
        limit=4,
        enable_e_path=False,
        enable_t_path=True,
        idle_after=0,
        beta=4,
        client=client,
        agent_id="demo-agent",
    )

    manifest = root / ".self-coaching" / "manifests" / "training_run_manifest.json"
    assert manifest.is_file()
    assert registry.get_agent("demo-agent")["active_version_id"] != bootstrap_version
    assert state.tasks_processed == 4

    buffer_rows = read_jsonl(root / ".self-coaching" / "loop" / "tuning_buffer.jsonl")
    consumed = [row for row in buffer_rows if row.get("used_for_train")]
    assert len(consumed) >= 4
