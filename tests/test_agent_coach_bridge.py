# SPDX-License-Identifier: MIT
"""Tests for the live AgentCoachBridge (Phase 1 — planner slice)."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_COACH = REPO_ROOT / "modes" / "coach"
_SC = REPO_ROOT / "modes" / "self-coaching"
_MODES = REPO_ROOT / "modes"
for _entry in (str(_MODES), str(_COACH), str(_SC), str(_SC / "self-learning"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from coach.agent_bridge_live import (  # noqa: E402
    AgentCoachBridge,
    CoachTransportError,
    HttpCoachTransport,
    extract_json,
    parse_chat_response,
)
from coach.post import CoachPost  # noqa: E402
from coach.registry import CoachClockConfig, SupervisedAgent  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _agent(tmp_path: Path) -> SupervisedAgent:
    return SupervisedAgent(
        id="test-agent",
        coaching_root=tmp_path / "coaching",
        coach_clock=CoachClockConfig(enabled=True, interval_s=1800.0),
    )


class _ScriptedTransport:
    """CoachTransport that returns a fixed string (or raises)."""

    def __init__(self, response: str | None = None, *, raise_error: bool = False):
        self.response = response
        self.raise_error = raise_error
        self.last_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        if self.raise_error:
            raise CoachTransportError("simulated transport failure")
        assert self.response is not None
        return self.response


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------


def test_parse_chat_response_openai_shape():
    data = {"choices": [{"message": {"content": '{"action": "hold"}'}}]}
    assert parse_chat_response(data) == '{"action": "hold"}'


def test_parse_chat_response_plain_string():
    assert parse_chat_response("hello") == "hello"


def test_parse_chat_response_unparseable_raises():
    with pytest.raises(CoachTransportError):
        parse_chat_response({"unexpected": "shape"})


def test_extract_json_plain():
    assert extract_json('{"action": "full_tick", "reason": "go"}')["action"] == "full_tick"


def test_extract_json_fenced():
    text = 'Sure!\n```json\n{"action": "hold", "reason": "thin"}\n```\nDone.'
    obj = extract_json(text)
    assert obj["action"] == "hold"


def test_extract_json_embedded_prose():
    text = 'I think we should {"action": "play", "reason": "weak"} proceed.'
    assert extract_json(text)["action"] == "play"


def test_extract_json_garbage_returns_empty():
    assert extract_json("no json here") == {}


# ---------------------------------------------------------------------------
# Bridge behavior (acceptance criteria)
# ---------------------------------------------------------------------------


def test_hold_decision_skips_tick(tmp_path: Path):
    """AC1: coach returns hold → plan.action == hold."""
    transport = _ScriptedTransport('{"action": "hold", "reason": "not enough signal"}')
    bridge = AgentCoachBridge(transport)
    plan = bridge.setup_clock(_agent(tmp_path), CoachPost(agent_id="test-agent", event="scheduled_tick"))
    assert plan.action == "hold"
    assert "not enough signal" in plan.reason


def test_full_tick_decision(tmp_path: Path):
    """AC2: coach returns full_tick → plan.action == full_tick."""
    transport = _ScriptedTransport('{"action": "full_tick", "reason": "ready"}')
    bridge = AgentCoachBridge(transport)
    plan = bridge.setup_clock(_agent(tmp_path), CoachPost(agent_id="test-agent", event="scheduled_tick"))
    assert plan.action == "full_tick"


def test_transport_failure_defaults_to_hold(tmp_path: Path):
    """Fail-safe: transport error → hold (don't burn an evolution cycle)."""
    transport = _ScriptedTransport(raise_error=True)
    bridge = AgentCoachBridge(transport)
    plan = bridge.setup_clock(_agent(tmp_path), CoachPost(agent_id="test-agent", event="scheduled_tick"))
    assert plan.action == "hold"
    assert "transport error" in plan.reason


def test_unparseable_response_defaults_to_hold(tmp_path: Path):
    transport = _ScriptedTransport("I cannot decide right now.")
    bridge = AgentCoachBridge(transport)
    plan = bridge.setup_clock(_agent(tmp_path), CoachPost(agent_id="test-agent", event="scheduled_tick"))
    assert plan.action == "hold"


def test_invalid_action_falls_back_to_hold(tmp_path: Path):
    transport = _ScriptedTransport('{"action": "explode", "reason": "bad action"}')
    bridge = AgentCoachBridge(transport)
    plan = bridge.setup_clock(_agent(tmp_path), CoachPost(agent_id="test-agent", event="scheduled_tick"))
    assert plan.action == "hold"


def test_scheduler_hint_is_not_binding(tmp_path: Path):
    """AC4: scheduled tick with suggested_action → coach still decides."""
    transport = _ScriptedTransport('{"action": "hold", "reason": "override scheduler"}')
    bridge = AgentCoachBridge(transport)
    post = CoachPost(
        agent_id="test-agent",
        event="scheduled_tick",
        payload={"suggested_action": "full_tick"},
    )
    plan = bridge.setup_clock(_agent(tmp_path), post)
    assert plan.action == "hold"  # coach overrode the full_tick hint
    assert transport.last_prompt is not None
    assert "suggested action" in transport.last_prompt


def test_audit_log_written(tmp_path: Path):
    """AC5: prompt + raw response + parsed plan are persisted."""
    transport = _ScriptedTransport('{"action": "full_tick", "reason": "ok"}')
    bridge = AgentCoachBridge(transport)
    agent = _agent(tmp_path)
    bridge.setup_clock(agent, CoachPost(agent_id="test-agent", event="scheduled_tick"))

    audit = agent.coaching_root / ".self-coaching" / "coach" / "audit" / "test-agent"
    assert (audit / "last_setup_prompt.txt").is_file()
    decision = json.loads((audit / "last_decision.json").read_text(encoding="utf-8"))
    assert decision["plan"]["action"] == "full_tick"
    assert decision["raw_response"]


def test_scenario_overrides_passed_through(tmp_path: Path):
    transport = _ScriptedTransport(
        '{"action": "full_tick", "reason": "ok", "scenario_overrides": {"force_regression": true}}'
    )
    bridge = AgentCoachBridge(transport)
    plan = bridge.setup_clock(_agent(tmp_path), CoachPost(agent_id="test-agent", event="scheduled_tick"))
    assert plan.scenario_overrides == {"force_regression": True}


# ---------------------------------------------------------------------------
# HttpCoachTransport against a real local server
# ---------------------------------------------------------------------------


def _make_chat_server(response_body: dict) -> ThreadingHTTPServer:
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            body = json.dumps(response_body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence
            pass

    return ThreadingHTTPServer(("127.0.0.1", 0), _Handler)


def test_http_transport_end_to_end(tmp_path: Path):
    server = _make_chat_server(
        {"choices": [{"message": {"content": '{"action": "full_tick", "reason": "via http"}'}}]}
    )
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        transport = HttpCoachTransport(f"http://{host}:{port}", model="test")
        bridge = AgentCoachBridge(transport)
        plan = bridge.setup_clock(_agent(tmp_path), CoachPost(agent_id="test-agent", event="scheduled_tick"))
        assert plan.action == "full_tick"
        assert plan.reason == "via http"
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# build_coach_bridge() env wiring
# ---------------------------------------------------------------------------


def test_build_coach_bridge_mock_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("COACH_BRIDGE", raising=False)
    monkeypatch.delenv("COACH_AGENT_URL", raising=False)
    from coach.service import build_coach_bridge
    from coach.agent_bridge import MockCoachAgentBridge

    bridge = build_coach_bridge()
    assert isinstance(bridge, MockCoachAgentBridge)


def test_build_coach_bridge_agent_returns_live_bridge(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COACH_BRIDGE", "agent")
    monkeypatch.setenv("COACH_AGENT_URL", "http://127.0.0.1:9999")
    from coach.service import build_coach_bridge

    bridge = build_coach_bridge()
    assert isinstance(bridge, AgentCoachBridge)
    assert bridge._transport.base_url == "http://127.0.0.1:9999"


def test_build_coach_bridge_agent_respects_path_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COACH_BRIDGE", "agent")
    monkeypatch.setenv("COACH_AGENT_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("COACH_AGENT_PATH", "/v1/chat")
    from coach.service import build_coach_bridge

    bridge = build_coach_bridge()
    assert bridge._transport.path == "/v1/chat"


def test_build_coach_bridge_agent_missing_url_exits(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COACH_BRIDGE", "agent")
    monkeypatch.delenv("COACH_AGENT_URL", raising=False)
    from coach.service import build_coach_bridge

    with pytest.raises(SystemExit):
        build_coach_bridge()


def test_build_coach_bridge_unknown_kind_exits(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COACH_BRIDGE", "bogus")
    from coach.service import build_coach_bridge

    with pytest.raises(SystemExit):
        build_coach_bridge()
