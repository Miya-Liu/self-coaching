# SPDX-License-Identifier: MIT
"""M2.3 smoke: loop learn() flows through SelfLearningAdapter to mock HTTP service."""

from __future__ import annotations

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
MOCK_SERVICES = REPO_ROOT / "mock-services"
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
MOCK_SELF_LEARNING = MOCK_SERVICES / "mock_self_learning.py"

for _entry in (str(MOCK_SERVICES), str(SC_ROOT), str(SC_ROOT / "self-learning"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with _NO_PROXY.open(f"{url}/learning/health", timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.15)
    raise RuntimeError(f"mock self-learning never came up at {url}")


@pytest.fixture(scope="module")
def self_learning_server(tmp_path_factory: pytest.TempPathFactory):
    """Start mock_self_learning.py serve on a free port."""
    port = _free_port()
    data_dir = tmp_path_factory.mktemp("sl-data")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, str(MOCK_SELF_LEARNING), "serve",
         "--data-dir", str(data_dir), "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base_url = f"http://127.0.0.1:{port}"
    _wait_for_health(base_url)
    try:
        yield base_url, data_dir
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_learn_via_adapter(self_learning_server: tuple[str, Path]) -> None:
    """SelfLearningAdapter.learn() reaches the mock HTTP service and gets a response."""
    base_url, _data_dir = self_learning_server

    from services.adapters.self_learning_client import SelfLearningClient
    from services.adapters.learn_adapter import SelfLearningAdapter

    client = SelfLearningClient(base_url=base_url)
    adapter = SelfLearningAdapter(client=client)

    result = adapter.learn(
        event="agent forgot to verify file write",
        source="test",
        capability="tool_use",
    )

    assert "id" in result
    assert result.get("event") == "agent forgot to verify file write"
    assert result.get("source") == "test"


def test_build_loop_client_with_learn_backend(
    self_learning_server: tuple[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_loop_client produces a CompositeClient that delegates learn() to HTTP."""
    base_url, _data_dir = self_learning_server

    monkeypatch.setenv("LOOP_SERVICE_MODE", "mock-http")
    monkeypatch.setenv("ORCHESTRATOR_LEARN_BACKEND", "self-learning")
    monkeypatch.setenv("SELF_LEARNING_BASE_URL", base_url)
    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "mock")
    monkeypatch.setenv("ORCHESTRATOR_TRAIN_BACKEND", "mock")
    monkeypatch.setenv("ORCHESTRATOR_TRANSPORT", "module")

    from loop_config import LoopConfig
    from loop_env import build_loop_client

    config = LoopConfig.from_env()
    assert config.learn_backend == "self-learning"

    coaching_root = tmp_path / "coaching"
    coaching_root.mkdir()
    client = build_loop_client(coaching_root, config=config)

    # The composite client should delegate learn() to the HTTP adapter
    result = client.learn(event="test via composite", source="m2.3-smoke", capability="tool_use")
    assert "id" in result
    assert result["event"] == "test via composite"


def test_loop_config_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LoopConfig.from_env_file loads a .env and resolves backends correctly."""
    # Clean env
    for key in list(os.environ):
        if key.startswith(("LOOP_", "MOCK_", "ORCHESTRATOR_", "SELF_LEARNING_", "AGENTEVALS_", "TRAINER_", "AGENT_", "AERL_")):
            monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / "test.env"
    env_file.write_text(
        "LOOP_SERVICE_MODE=live\n"
        "SELF_LEARNING_BASE_URL=http://localhost:9999\n"
        "LOOP_AGENT_ID=test-agent\n"
        "LOOP_TAU_FAIL=0.6\n",
        encoding="utf-8",
    )

    from loop_config import LoopConfig

    config = LoopConfig.from_env_file(env_file)
    assert config.service_mode == "live"
    assert config.learn_backend == "self-learning"
    assert config.self_learning_url == "http://localhost:9999"
    assert config.agent_id == "test-agent"
    assert config.tau_fail == 0.6
