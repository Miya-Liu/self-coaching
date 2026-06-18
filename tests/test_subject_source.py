# SPDX-License-Identifier: MIT
"""Tests for SubjectTaskSource (Phase 2 — live subject trajectory producer)."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_SC = REPO_ROOT / "modes" / "self-coaching"
for _entry in (str(_SC), str(_SC / "self-learning"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from subject_source import (  # noqa: E402
    SubjectSourceError,
    SubjectTaskSource,
    build_subject_source,
    build_xi,
    extract_assistant_content,
    extract_tool_trace,
    resolve_endpoint,
)


# ---------------------------------------------------------------------------
# Endpoint resolution (guards the /chat + /chat/completions footgun, issue #1)
# ---------------------------------------------------------------------------


def test_resolve_endpoint_bare_base_appends_path():
    assert resolve_endpoint("http://host:8000", "/chat/completions") == "http://host:8000/chat/completions"


def test_resolve_endpoint_trailing_slash():
    assert resolve_endpoint("http://host:8000/", "/chat/completions") == "http://host:8000/chat/completions"


def test_resolve_endpoint_with_path_used_as_is():
    # Legacy agent_chat_url style — must NOT become /chat/chat/completions
    assert resolve_endpoint("http://host:8000/chat", "/chat/completions") == "http://host:8000/chat"


def test_resolve_endpoint_full_path_used_as_is():
    assert resolve_endpoint("http://host:8000/v1/chat/completions", "/chat/completions") == "http://host:8000/v1/chat/completions"


def test_subject_source_endpoint_no_double_path():
    src = SubjectTaskSource("http://host:8000/chat", model="x")
    assert src.endpoint == "http://host:8000/chat"
    bare = SubjectTaskSource("http://host:8000", model="x")
    assert bare.endpoint == "http://host:8000/chat/completions"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_extract_assistant_content_openai():
    data = {"choices": [{"message": {"content": "the answer"}}]}
    assert extract_assistant_content(data) == "the answer"


def test_extract_assistant_content_plain():
    assert extract_assistant_content("plain text") == "plain text"


def test_extract_tool_trace_from_tool_calls():
    data = {
        "choices": [
            {"message": {"content": "done", "tool_calls": [
                {"function": {"name": "write_file"}},
                {"function": {"name": "validate_yaml"}},
            ]}}
        ]
    }
    assert extract_tool_trace(data) == ["invoke write_file", "invoke validate_yaml"]


def test_extract_tool_trace_direct_report():
    data = {"tool_trace_summary": ["invoke a", "invoke b"]}
    assert extract_tool_trace(data) == ["invoke a", "invoke b"]


def test_extract_tool_trace_empty_when_no_tools():
    data = {"choices": [{"message": {"content": "no tools used"}}]}
    assert extract_tool_trace(data) == []


def test_build_xi_shape():
    tau = {"task_id": "t1", "user_request": "do X", "capability": ["tool_use"]}
    xi = build_xi(tau, final_answer="done", tool_trace=["invoke f"])
    assert xi["task_id"] == "t1"
    assert xi["final_answer"] == "done"
    assert xi["tool_trace_summary"] == ["invoke f"]
    assert xi["messages"][0]["role"] == "user"
    assert xi["messages"][1]["content"] == "done"
    assert xi["_source"] == "live_subject"


def test_build_subject_source_none_when_no_url():
    assert build_subject_source(None) is None
    assert build_subject_source("") is None


def test_subject_source_requires_url():
    with pytest.raises(SubjectSourceError):
        SubjectTaskSource("")


# ---------------------------------------------------------------------------
# Live HTTP round-trip + scoring integration
# ---------------------------------------------------------------------------


def _make_subject_server(content: str, tool_calls: list[dict] | None = None):
    message: dict = {"content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls

    class _Handler(BaseHTTPRequestHandler):
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

    return ThreadingHTTPServer(("127.0.0.1", 0), _Handler)


def test_subject_source_end_to_end():
    server = _make_subject_server(
        "Created config.yaml and validated it.",
        tool_calls=[{"function": {"name": "write_file"}}, {"function": {"name": "validate"}}],
    )
    host, port = server.server_address
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        source = SubjectTaskSource(f"http://{host}:{port}", model="test")
        tau = {"task_id": "t1", "user_request": "create and validate config", "capability": ["tool_use"]}
        xi = source(tau)
        assert xi["final_answer"] == "Created config.yaml and validated it."
        assert xi["tool_trace_summary"] == ["invoke write_file", "invoke validate"]
        assert xi["task_id"] == "t1"
    finally:
        server.shutdown()
        server.server_close()


def test_subject_source_feeds_scorer():
    """A live xi should score correctly against a task rubric."""
    from trajectory_scorer import score_trajectory

    server = _make_subject_server(
        "validated config.yaml successfully",
        tool_calls=[{"function": {"name": "write_config"}}],
    )
    host, port = server.server_address
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        source = SubjectTaskSource(f"http://{host}:{port}", model="test")
        tau = {
            "task_id": "t1",
            "user_request": "write and validate config",
            "expected_tool_calls": ["write_config"],
            "answer_checks": [{"type": "contains", "value": "validated"}],
        }
        xi = source(tau)
        rubric = score_trajectory(xi, tau)
        assert rubric["score"] == 1.0
        assert rubric["breakdown"]["tools_ok"] is True
        assert rubric["breakdown"]["answer_ok"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_subject_source_missing_tools_scores_low():
    """Subject that answers without invoking required tools → low score (faithful)."""
    from trajectory_scorer import score_trajectory

    server = _make_subject_server("I think it is done.", tool_calls=None)
    host, port = server.server_address
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        source = SubjectTaskSource(f"http://{host}:{port}", model="test")
        tau = {
            "task_id": "t1",
            "user_request": "write and validate config",
            "expected_tool_calls": ["write_config"],
            "answer_checks": [{"type": "contains", "value": "validated"}],
        }
        xi = source(tau)
        rubric = score_trajectory(xi, tau)
        assert rubric["score"] == 0.0
        assert rubric["breakdown"]["tools_ok"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_subject_source_transport_error():
    # Unused port → connection refused → SubjectSourceError
    source = SubjectTaskSource("http://127.0.0.1:1", model="test", timeout_s=2.0)
    with pytest.raises(SubjectSourceError):
        source({"task_id": "t1", "user_request": "x"})
