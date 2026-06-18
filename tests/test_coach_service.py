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
_MODES = REPO_ROOT / "modes"
for _entry in (str(_MODES), str(_COACH), str(_SC), str(_SC / "self-learning"), str(_MOCK), str(REPO_ROOT)):
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


# ---------------------------------------------------------------------------
# Integration: AgentCoachBridge end-to-end (scripted coach + HTTP service + tick)
# ---------------------------------------------------------------------------


def _start_scripted_coach_server(response_action: str, response_reason: str):
    """Start a tiny HTTP server that returns a fixed ClockPlan JSON on any POST."""
    import http.server

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            plan = json.dumps({
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "action": response_action,
                            "reason": response_reason,
                        })
                    }
                }]
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(plan)))
            self.end_headers()
            self.wfile.write(plan)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_agent_bridge_hold_skips_tick_via_http_service(coaching_root: Path) -> None:
    """E2E: scripted coach returns 'hold' → service skips tick, no error."""
    from coach.agent_bridge_live import AgentCoachBridge, HttpCoachTransport

    coach_server = _start_scripted_coach_server("hold", "not enough signal")
    coach_host, coach_port = coach_server.server_address
    try:
        transport = HttpCoachTransport(f"http://{coach_host}:{coach_port}", model="test")
        bridge = AgentCoachBridge(transport)
        state = CoachServiceState(REGISTRY, bridge=bridge)
        server = run_http_server(state, "127.0.0.1", 0)
        host, port = server.server_address
        time.sleep(0.2)
        try:
            payload = json.dumps({
                "agent_id": "clock-demo-agent",
                "event": "scheduled_tick",
                "payload": {"suggested_action": "full_tick"},
            }).encode("utf-8")
            req = urllib.request.Request(
                f"http://{host}:{port}/coach/post",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            assert result["plan"]["action"] == "hold"
            assert result["tick"] is None
            # Audit should be written
            audit = coaching_root / ".self-coaching" / "coach" / "audit" / "clock-demo-agent"
            assert (audit / "last_decision.json").is_file()
            decision = json.loads((audit / "last_decision.json").read_text(encoding="utf-8"))
            assert decision["plan"]["action"] == "hold"
        finally:
            server.shutdown()
            server.server_close()
    finally:
        coach_server.shutdown()
        coach_server.server_close()


def test_agent_bridge_full_tick_runs_evolution(coaching_root: Path) -> None:
    """E2E: scripted coach returns 'full_tick' → service runs clock.run_tick → promoted."""
    from coach.agent_bridge_live import AgentCoachBridge, HttpCoachTransport

    coach_server = _start_scripted_coach_server("full_tick", "buffer ready")
    coach_host, coach_port = coach_server.server_address
    try:
        transport = HttpCoachTransport(f"http://{coach_host}:{coach_port}", model="test")
        bridge = AgentCoachBridge(transport)
        state = CoachServiceState(REGISTRY, bridge=bridge)
        server = run_http_server(state, "127.0.0.1", 0)
        host, port = server.server_address
        time.sleep(0.2)
        try:
            payload = json.dumps({
                "agent_id": "clock-demo-agent",
                "event": "session_complete",
                "payload": {},
            }).encode("utf-8")
            req = urllib.request.Request(
                f"http://{host}:{port}/coach/post",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            assert result["plan"]["action"] == "full_tick"
            assert result["tick"] is not None
            assert result["tick"].get("t_path_promoted") is True
        finally:
            server.shutdown()
            server.server_close()
    finally:
        coach_server.shutdown()
        coach_server.server_close()


# ---------------------------------------------------------------------------
# Phase 1.5: Partial-action routing (learn / play / tune)
# ---------------------------------------------------------------------------


def test_partial_learn_runs_e_path_only(coaching_root: Path) -> None:
    """action=learn → E-path fires (tasks scored, failures learned) without T-path."""
    body = {
        "agent_id": "clock-demo-agent",
        "event": "failure_cluster",
        "payload": {"action": "learn", "reason": "3 failures on tool_use"},
    }
    result = handle_post_body(body, REGISTRY)
    assert result["plan"]["action"] == "learn"
    assert result["tick"] is not None
    assert result["tick"]["action"] == "learn"
    assert "generation" in result["tick"]
    # T-path artifacts should NOT exist
    t_path_last = coaching_root / ".self-coaching" / "loop" / "t_path_last.json"
    assert not t_path_last.is_file()


def test_partial_play_runs_batch_self_play_only(coaching_root: Path) -> None:
    """action=play → C07 batch self-play fills buffer; no learn, no train."""
    body = {
        "agent_id": "clock-demo-agent",
        "event": "idle_window",
        "payload": {"action": "play", "reason": "buffer low"},
    }
    result = handle_post_body(body, REGISTRY)
    assert result["plan"]["action"] == "play"
    assert result["tick"] is not None
    assert result["tick"]["action"] == "play"
    assert "batch_fill" in result["tick"]
    assert "buffer_size" in result["tick"]


def test_partial_tune_runs_t_path_only(coaching_root: Path) -> None:
    """action=tune → T-path fires (fill + train + holdout gate) with promotion."""
    # Seed enough buffer first (play) so tune has data
    play_body = {
        "agent_id": "clock-demo-agent",
        "event": "idle_window",
        "payload": {"action": "play"},
    }
    handle_post_body(play_body, REGISTRY)

    body = {
        "agent_id": "clock-demo-agent",
        "event": "scheduled_tick",
        "payload": {"action": "tune", "reason": "buffer full"},
    }
    result = handle_post_body(body, REGISTRY)
    assert result["plan"]["action"] == "tune"
    assert result["tick"] is not None
    assert result["tick"]["action"] == "tune"
    assert "t_path" in result["tick"]
    assert "t_path_promoted" in result["tick"]
    # agents.clock.yaml scenario has force_regression: true → promotion should succeed
    assert result["tick"]["t_path_promoted"] is True


# ---------------------------------------------------------------------------
# Phase 2: Live subject driving via subject_chat_url
# ---------------------------------------------------------------------------


def _start_subject_server(content: str, tool_calls=None):
    """HTTP server simulating the supervised subject's /chat/completions."""
    import http.server

    message = {"content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            body = json.dumps({"choices": [{"message": message}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _write_subject_registry(tmp: Path, subject_url: str) -> Path:
    """Write a registry whose agent points coach_clock.subject_chat_url at subject_url."""
    reg = tmp / "agents.subject.yaml"
    reg.write_text(
        "agents:\n"
        "  - id: clock-demo-agent\n"
        f"    coaching_root: {(_MOCK / 'ci-coach-clock-service').as_posix()}\n"
        "    model: mock-model-clock\n"
        "    prefer_skill_first: true\n"
        "    coach_clock:\n"
        "      enabled: true\n"
        "      scenario: scenarios/clock_loop.json\n"
        "      interval_s: 1800\n"
        f"      subject_chat_url: {subject_url}\n"
        "    eval:\n"
        "      suite_id_canary: tool-use-canary\n"
        "      suite_id_holdout: tool-use-holdout\n"
        "    improvement:\n"
        "      train_pipeline: sft\n"
        "      min_cases_for_model_path: 2\n",
        encoding="utf-8",
    )
    return reg


def test_full_tick_uses_live_subject(coaching_root: Path, tmp_path: Path) -> None:
    """E2E: subject_chat_url set → trajectories come from the live subject server."""
    # Subject answers without tools → E-path tasks will route to failures (faithful)
    subject = _start_subject_server("I believe the task is complete.", tool_calls=None)
    host, port = subject.server_address
    try:
        reg = _write_subject_registry(tmp_path, f"http://{host}:{port}")
        body = {
            "agent_id": "clock-demo-agent",
            "event": "session_complete",
            "payload": {"action": "full_tick"},
        }
        result = handle_post_body(body, reg)
        assert result["plan"]["action"] == "full_tick"
        assert result["tick"] is not None
        # A live trajectory was written and scored
        traj_dir = coaching_root / ".self-coaching" / "loop" / "trajectories"
        assert traj_dir.is_dir()
        live = [
            p for p in traj_dir.glob("*.json")
            if json.loads(p.read_text(encoding="utf-8")).get("_source") == "live_subject"
        ]
        assert live, "expected at least one live_subject trajectory"
    finally:
        subject.shutdown()
        subject.server_close()


def test_registry_subject_chat_url_alias(tmp_path: Path) -> None:
    """Backward compat: old agent_chat_url still parses into subject_chat_url."""
    reg = tmp_path / "agents.legacy.yaml"
    reg.write_text(
        "agents:\n"
        "  - id: legacy-agent\n"
        "    coaching_root: /tmp/legacy\n"
        "    coach_clock:\n"
        "      enabled: true\n"
        "      agent_chat_url: http://legacy:8000/chat\n",
        encoding="utf-8",
    )
    agents = load_registry(reg)
    assert agents[0].coach_clock.subject_chat_url == "http://legacy:8000/chat"


def test_partial_play_skips_when_buffer_full(coaching_root: Path) -> None:
    """Two consecutive play ticks must not over-fill beyond beta (top-up semantics)."""
    play = {
        "agent_id": "clock-demo-agent",
        "event": "idle_window",
        "payload": {"action": "play"},
    }
    first = handle_post_body(play, REGISTRY)
    first_size = first["tick"]["buffer_size"]
    second = handle_post_body(play, REGISTRY)
    second_size = second["tick"]["buffer_size"]
    # Buffer should not keep growing past beta on repeated play
    assert second_size <= max(first_size, 4)
    # Second play with a full buffer should report a skipped/zero fill
    bf = second["tick"]["batch_fill"]
    assert bf.get("count", 0) == 0 or second_size <= 4


def test_partial_learn_with_live_subject(coaching_root: Path, tmp_path: Path) -> None:
    """action=learn + subject_chat_url → E-path consumes live subject trajectories."""
    subject = _start_subject_server("I think it is done.", tool_calls=None)
    host, port = subject.server_address
    try:
        reg = _write_subject_registry(tmp_path, f"http://{host}:{port}")
        body = {
            "agent_id": "clock-demo-agent",
            "event": "failure_cluster",
            "payload": {"action": "learn"},
        }
        result = handle_post_body(body, reg)
        assert result["plan"]["action"] == "learn"
        assert result["tick"]["action"] == "learn"
        # Live trajectory produced during the E-path scoring
        traj_dir = coaching_root / ".self-coaching" / "loop" / "trajectories"
        live = [
            p for p in traj_dir.glob("*.json")
            if json.loads(p.read_text(encoding="utf-8")).get("_source") == "live_subject"
        ]
        assert live, "expected a live_subject trajectory from learn route"
    finally:
        subject.shutdown()
        subject.server_close()
