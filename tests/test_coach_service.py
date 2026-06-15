# SPDX-License-Identifier: MIT
"""Coach clock service — HTTP POST ingress and trigger pipeline."""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_COACH = REPO_ROOT / "modes" / "coach"
_SC = REPO_ROOT / "modes" / "self-coaching"
_MOCK = REPO_ROOT / "mock-services"
for _entry in (str(_COACH), str(_SC), str(_SC / "self-learning"), str(_MOCK), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from loop_env import configure_demo_env  # noqa: E402
from registry import load_registry  # noqa: E402
from service import CoachServiceState, run_http_server  # noqa: E402
from trigger import handle_post_body  # noqa: E402

REGISTRY = _COACH / "agents.clock.yaml"
ROOT = _MOCK / "ci-coach-clock-service"

_ENV_PREFIXES = ("LOOP_", "MOCK_", "ORCHESTRATOR_", "AGENTEVALS_", "TRAINER_", "AGENT_")


@pytest.fixture(autouse=True)
def _isolate_env():
    """Prevent clock.run_tick / configure_demo_env env mutations from leaking."""
    import os
    snapshot = {k: os.environ[k] for k in list(os.environ) if k.startswith(_ENV_PREFIXES)}
    yield
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIXES) and key not in snapshot:
            del os.environ[key]
    for key, value in snapshot.items():
        os.environ[key] = value


@pytest.fixture()
def coaching_root() -> Path:
    configure_demo_env()
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    yield ROOT
    if ROOT.exists():
        shutil.rmtree(ROOT)


def test_handle_post_runs_clock_tick(coaching_root: Path) -> None:
    body = {
        "agent_id": "clock-demo-agent",
        "event": "session_complete",
        "payload": {"action": "full_tick", "reason": "test"},
    }
    result = handle_post_body(body, REGISTRY)
    assert result["plan"]["action"] == "full_tick"
    assert result["tick"] is not None
    assert result["tick"].get("t_path_promoted") is True
    inbox = coaching_root / ".self-coaching" / "coach" / "inbox"
    assert inbox.is_dir()
    assert any(inbox.glob("*.json"))


def test_handle_post_hold(coaching_root: Path) -> None:
    body = {
        "agent_id": "clock-demo-agent",
        "event": "heartbeat",
        "payload": {"action": "hold", "reason": "no signal"},
    }
    result = handle_post_body(body, REGISTRY)
    assert result["plan"]["action"] == "hold"
    assert result["tick"] is None


def test_http_post_ingress(coaching_root: Path) -> None:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    state = CoachServiceState(REGISTRY)
    server = run_http_server(state, "127.0.0.1", 0)
    host, port = server.server_address
    time.sleep(0.2)
    try:
        payload = json.dumps(
            {
                "agent_id": "clock-demo-agent",
                "event": "ws_equivalent_post",
                "payload": {"action": "full_tick"},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"http://{host}:{port}/coach/post",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        assert result["tick"]["t_path_promoted"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_registry_loads_coach_clock() -> None:
    agents = load_registry(REGISTRY)
    assert len(agents) == 1
    assert agents[0].coach_clock is not None
    assert agents[0].coach_clock.enabled is True
    assert agents[0].coach_clock.scenario == "scenarios/clock_loop.json"
