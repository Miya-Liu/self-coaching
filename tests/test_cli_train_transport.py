# SPDX-License-Identifier: MIT
"""Unit tests for CLITrainTransport (offline, mocked httpx)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from services.adapters.cli_train_errors import (  # noqa: E402
    TransportError,
    TrainerTimeoutError,
)
from services.adapters.cli_train_transport import (  # noqa: E402
    CLITrainTransport,
    TERMINAL_STATUSES,
)


USER_ID = "00000000-0000-0000-0000-000000000001"
CMD_ID = "11111111-1111-1111-1111-111111111111"


def _make_transport(handler: httpx.MockTransport) -> CLITrainTransport:
    client = httpx.Client(transport=handler)
    return CLITrainTransport(
        supabase_url="http://example.test:54321",
        service_role_key="test-key",
        user_id=USER_ID,
        poll_interval_s=0.01,
        poll_timeout_s=5.0,
        poll_grace_s=0.05,
        client=client,
    )


def test_terminal_statuses_frozen():
    assert "SUCCEEDED" in TERMINAL_STATUSES
    assert "PENDING" not in TERMINAL_STATUSES


def test_from_env_requires_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("BRIDGE_USER_ID", raising=False)
    with pytest.raises(TransportError, match="SUPABASE_URL"):
        CLITrainTransport.from_env()


def test_from_env_builds_transport(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_URL", "http://db.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    monkeypatch.setenv("BRIDGE_USER_ID", USER_ID)
    monkeypatch.setenv("CLI_TRAIN_POLL_INTERVAL", "3")
    transport = CLITrainTransport.from_env(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    assert transport.supabase_url == "http://db.test"
    assert transport.poll_interval_s == 3.0


def test_send_inserts_pending_row():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/areal_remote_commands")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(201, json=[captured["body"]])

    transport = _make_transport(httpx.MockTransport(handler))
    cmd_id = transport.send("echo hello", cwd="/workspace", tmux_id="train-1", cmd_id=CMD_ID)

    assert cmd_id == CMD_ID
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["id"] == CMD_ID
    assert body["user_id"] == USER_ID
    assert body["command"] == "echo hello"
    assert body["cwd"] == "/workspace"
    assert body["tmux_id"] == "train-1"
    assert body["status"] == "PENDING"


def test_send_insert_failure_raises_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    transport = _make_transport(httpx.MockTransport(handler))
    with pytest.raises(TransportError, match="insert") as exc:
        transport.send("echo fail")
    assert exc.value.status == 500


def test_poll_returns_row():
    row = {
        "id": CMD_ID,
        "status": "RUNNING",
        "stdout_tail": "working\n",
        "stderr_tail": "",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert f"eq.{CMD_ID}" in str(request.url)
        return httpx.Response(200, json=[row])

    transport = _make_transport(httpx.MockTransport(handler))
    assert transport.poll(CMD_ID) == row


def test_poll_missing_row_returns_empty_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    transport = _make_transport(httpx.MockTransport(handler))
    assert transport.poll(CMD_ID) == {}


def test_wait_for_terminal_returns_succeeded_row():
    calls = {"n": 0}
    row_running = {"id": CMD_ID, "status": "RUNNING", "stdout_tail": "step1\n"}
    row_done = {"id": CMD_ID, "status": "SUCCEEDED", "exit_code": 0, "stdout_tail": "done\n"}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(200, json=[row_running])
        return httpx.Response(200, json=[row_done])

    transport = _make_transport(httpx.MockTransport(handler))
    seen: list[str] = []

    def on_poll(row: dict) -> None:
        seen.append(str(row.get("status")))

    result = transport.wait_for_terminal(CMD_ID, on_poll=on_poll)
    assert result["status"] == "SUCCEEDED"
    assert result["exit_code"] == 0
    assert "RUNNING" in seen
    assert seen[-1] == "SUCCEEDED"


def test_wait_for_terminal_returns_failed_row_without_raising():
    row = {"id": CMD_ID, "status": "FAILED", "exit_code": 1, "stderr_tail": "boom"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[row])

    transport = _make_transport(httpx.MockTransport(handler))
    result = transport.wait_for_terminal(CMD_ID)
    assert result["status"] == "FAILED"
    assert result["exit_code"] == 1


def test_wait_for_terminal_poll_budget_raises_timeout():
    row = {"id": CMD_ID, "status": "RUNNING"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[row])

    transport = _make_transport(httpx.MockTransport(handler))
    with pytest.raises(TrainerTimeoutError, match="terminal status") as exc:
        transport.wait_for_terminal(CMD_ID, command_timeout_seconds=0)
    assert exc.value.cmd_id == CMD_ID
    assert exc.value.body == row


def test_send_and_wait_end_to_end():
    state = {"status": "PENDING"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content.decode())
            state["id"] = body["id"]
            return httpx.Response(201, json=[body])
        cmd_id = state["id"]
        if state["status"] == "PENDING":
            state["status"] = "RUNNING"
            return httpx.Response(200, json=[{"id": cmd_id, "status": "RUNNING"}])
        return httpx.Response(
            200,
            json=[{"id": cmd_id, "status": "SUCCEEDED", "exit_code": 0, "stdout_tail": "ok\n"}],
        )

    transport = _make_transport(httpx.MockTransport(handler))
    result = transport.send_and_wait("echo ok", tmux_id="train-e2e", timeout_seconds=30)
    assert result["status"] == "SUCCEEDED"
    assert result["stdout_tail"] == "ok\n"
