# SPDX-License-Identifier: MIT
"""Tests for coach tools (B4 — tool gateway for fine-grained coach actions)."""

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

from coach.coach_tools import TOOL_DEFINITIONS, execute_tool  # noqa: E402
from coach.agent_bridge_live import AgentCoachBridge, HttpCoachTransport  # noqa: E402
from coach.post import CoachPost  # noqa: E402
from coach.registry import CoachClockConfig, SupervisedAgent  # noqa: E402


def _agent(tmp_path: Path) -> SupervisedAgent:
    return SupervisedAgent(
        id="test-agent",
        coaching_root=tmp_path / "coaching",
        coach_clock=CoachClockConfig(enabled=True, interval_s=1800.0),
    )


# ---------------------------------------------------------------------------
# Tool definitions schema
# ---------------------------------------------------------------------------


def test_tool_definitions_are_valid():
    assert len(TOOL_DEFINITIONS) >= 5
    for tool in TOOL_DEFINITIONS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn


# ---------------------------------------------------------------------------
# Individual tool execution
# ---------------------------------------------------------------------------


def test_get_loop_state(tmp_path: Path):
    root = tmp_path / "coaching"
    root.mkdir()
    result = execute_tool("get_loop_state", {}, coaching_root=root)
    assert result["generation"] == 0
    assert result["support_set_size"] == 0
    assert result["buffer_size"] == 0


def test_record_learning(tmp_path: Path):
    root = tmp_path / "coaching"
    root.mkdir()
    result = execute_tool(
        "record_learning",
        {"title": "test", "observation": "obs", "lesson": "les"},
        coaching_root=root,
    )
    assert result["status"] == "recorded"
    path = root / "experience" / "LEARNINGS.md"
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "test" in content
    assert "les" in content


def test_record_error(tmp_path: Path):
    root = tmp_path / "coaching"
    root.mkdir()
    result = execute_tool(
        "record_error",
        {"title": "crash", "symptom": "OOM on train"},
        coaching_root=root,
    )
    assert result["status"] == "recorded"
    assert (root / "experience" / "ERROR.md").is_file()


def test_create_eval_case(tmp_path: Path):
    root = tmp_path / "coaching"
    root.mkdir()
    result = execute_tool(
        "create_eval_case",
        {"case_id": "eval-001", "capability": "tool_use", "prompt": "do X", "must_contain": ["done"]},
        coaching_root=root,
    )
    assert result["status"] == "created"
    path = root / ".self-coaching" / "cases" / "eval_cases.jsonl"
    assert path.is_file()
    case = json.loads(path.read_text(encoding="utf-8").strip())
    assert case["case_id"] == "eval-001"
    assert case["checks"]["must_contain"] == ["done"]


def test_get_tick_history_empty(tmp_path: Path):
    root = tmp_path / "coaching"
    root.mkdir()
    result = execute_tool("get_tick_history", {"n": 5}, coaching_root=root)
    assert result["total_ticks"] == 0
    assert result["recent"] == []


def test_unknown_tool(tmp_path: Path):
    result = execute_tool("nonexistent", {}, coaching_root=tmp_path)
    assert "error" in result


# ---------------------------------------------------------------------------
# Tool-calling loop integration (AgentCoachBridge + tools_enabled)
# ---------------------------------------------------------------------------


def _make_tool_calling_server(tool_responses: dict[str, str], final_answer: str):
    """Server that returns tool_calls on first request, then final answer after tool results."""
    call_count = {"n": 0}

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            call_count["n"] += 1

            messages = body.get("messages", [])
            # If messages contain tool results, return the final answer
            has_tool_result = any(m.get("role") == "tool" for m in messages)

            if not has_tool_result and tool_responses:
                # First call: return tool_calls
                tool_calls = [
                    {"id": f"call_{name}", "function": {"name": name, "arguments": "{}"}}
                    for name in tool_responses
                ]
                resp_body = json.dumps({
                    "choices": [{"message": {"content": None, "tool_calls": tool_calls}}]
                }).encode("utf-8")
            else:
                # After tools executed: return final answer
                resp_body = json.dumps({
                    "choices": [{"message": {"content": final_answer}}]
                }).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, call_count


def test_bridge_with_tools_executes_and_returns_plan(tmp_path: Path):
    """Coach calls get_loop_state tool, then returns a plan based on the result."""
    server, call_count = _make_tool_calling_server(
        tool_responses={"get_loop_state": "{}"},
        final_answer='{"action": "hold", "reason": "buffer empty after inspection"}',
    )
    host, port = server.server_address
    try:
        transport = HttpCoachTransport(f"http://{host}:{port}", model="test")
        bridge = AgentCoachBridge(transport, tools_enabled=True)
        plan = bridge.setup_clock(
            _agent(tmp_path),
            CoachPost(agent_id="test-agent", event="scheduled_tick"),
        )
        assert plan.action == "hold"
        assert "inspection" in plan.reason
        assert call_count["n"] == 2  # tool_calls round + final answer round

        # Audit should record tool calls
        audit = tmp_path / "coaching" / ".self-coaching" / "coach" / "audit" / "test-agent"
        decision = json.loads((audit / "last_decision.json").read_text(encoding="utf-8"))
        assert decision.get("tool_calls")
        assert decision["tool_calls"][0]["tool"] == "get_loop_state"
    finally:
        server.shutdown()
        server.server_close()


def test_bridge_without_tools_skips_tool_calling(tmp_path: Path):
    """When tools_enabled=False, the bridge uses simple complete() path."""
    server, call_count = _make_tool_calling_server(
        tool_responses={"get_loop_state": "{}"},
        final_answer='{"action": "full_tick", "reason": "no tools"}',
    )
    host, port = server.server_address
    try:
        transport = HttpCoachTransport(f"http://{host}:{port}", model="test")
        bridge = AgentCoachBridge(transport, tools_enabled=False)
        plan = bridge.setup_clock(
            _agent(tmp_path),
            CoachPost(agent_id="test-agent", event="scheduled_tick"),
        )
        # Without tools, server only gets one call and may return tool_calls
        # but bridge ignores them and parses content
        assert plan.action in ("hold", "full_tick")  # depends on server response path
        assert call_count["n"] == 1  # single call, no tool loop
    finally:
        server.shutdown()
        server.server_close()
