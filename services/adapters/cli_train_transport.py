# SPDX-License-Identifier: MIT
"""Supabase transport for db_bridge remote shell training commands."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from .cli_train_errors import TransportError, TrainerTimeoutError

REMOTE_COMMANDS_TABLE = "areal_remote_commands"

TERMINAL_STATUSES = frozenset(
    {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "STALE"},
)

DEFAULT_POLL_SELECT = (
    "id,status,exit_code,stdout_tail,stderr_tail,log_bytes,error_message,"
    "started_at,finished_at,tmux_id,command,cwd,timeout_seconds"
)


def _env_float(name: str, default: str) -> float:
    return float(os.environ.get(name, default))


def _env_int(name: str, default: str) -> int:
    return int(os.environ.get(name, default))


class CLITrainTransport:
    """Insert and poll ``areal_remote_commands`` rows via Supabase PostgREST."""

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        user_id: str,
        poll_interval_s: float = 5.0,
        poll_timeout_s: float = 3600.0,
        poll_grace_s: float = 60.0,
        http_timeout_s: float = 30.0,
        client: httpx.Client | None = None,
    ):
        self.supabase_url = supabase_url.rstrip("/")
        self.service_role_key = service_role_key
        self.user_id = user_id
        self.poll_interval_s = poll_interval_s
        self.poll_timeout_s = poll_timeout_s
        self.poll_grace_s = poll_grace_s
        self.http_timeout_s = http_timeout_s
        self._external_client = client  # caller-owned; we never close it
        self._lazy_client: httpx.Client | None = None

    @classmethod
    def from_env(cls, **overrides: Any) -> CLITrainTransport:
        """Build transport from environment variables."""
        supabase_url = overrides.pop("supabase_url", None) or os.environ.get("SUPABASE_URL")
        service_role_key = overrides.pop(
            "service_role_key", None
        ) or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        user_id = overrides.pop("user_id", None) or os.environ.get("BRIDGE_USER_ID")
        if not supabase_url or not service_role_key:
            raise TransportError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        if not user_id:
            raise TransportError("BRIDGE_USER_ID is required")
        poll_interval_s = overrides.pop(
            "poll_interval_s",
            _env_float("CLI_TRAIN_POLL_INTERVAL", os.environ.get("AERL_POLL_INTERVAL_S", "5")),
        )
        poll_timeout_s = overrides.pop(
            "poll_timeout_s",
            _env_float("CLI_TRAIN_TIMEOUT", os.environ.get("AERL_TIMEOUT_S", "3600")),
        )
        poll_grace_s = overrides.pop(
            "poll_grace_s",
            _env_float("CLI_TRAIN_POLL_GRACE", "60"),
        )
        http_timeout_s = overrides.pop("http_timeout_s", 30.0)
        client = overrides.pop("client", None)
        if overrides:
            raise TypeError(f"unexpected keyword arguments: {sorted(overrides)}")
        return cls(
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            user_id=user_id,
            poll_interval_s=poll_interval_s,
            poll_timeout_s=poll_timeout_s,
            poll_grace_s=poll_grace_s,
            http_timeout_s=http_timeout_s,
            client=client,
        )

    @property
    def rest_url(self) -> str:
        return f"{self.supabase_url}/rest/v1"

    def _headers(self, *, prefer_representation: bool = False) -> dict[str, str]:
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
        }
        if prefer_representation:
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "return=representation"
        return headers

    def _http_client(self) -> httpx.Client:
        if self._external_client is not None:
            return self._external_client
        if self._lazy_client is None:
            self._lazy_client = httpx.Client(timeout=self.http_timeout_s)
        return self._lazy_client

    def send(
        self,
        command: str,
        *,
        cwd: str | None = None,
        tmux_id: str | None = None,
        timeout_seconds: int | None = None,
        cmd_id: str | None = None,
    ) -> str:
        """Enqueue a shell command. Returns the command row id."""
        resolved_id = cmd_id or str(uuid.uuid4())
        resolved_tmux = tmux_id or f"train-{uuid.uuid4().hex[:8]}"
        timeout = timeout_seconds if timeout_seconds is not None else _env_int("CLI_TRAIN_TIMEOUT", "3600")
        body: dict[str, Any] = {
            "id": resolved_id,
            "user_id": self.user_id,
            "tmux_id": resolved_tmux,
            "command": command,
            "timeout_seconds": timeout,
            "status": "PENDING",
        }
        if cwd:
            body["cwd"] = cwd

        client = self._http_client()
        try:
            resp = client.post(
                f"{self.rest_url}/{REMOTE_COMMANDS_TABLE}",
                headers=self._headers(prefer_representation=True),
                json=body,
            )
        finally:
            pass

        if resp.status_code not in (200, 201):
            raise TransportError(
                f"insert into {REMOTE_COMMANDS_TABLE} failed: HTTP {resp.status_code}",
                status=resp.status_code,
                body=resp.text,
            )
        return resolved_id

    def poll(self, cmd_id: str, *, select: str = DEFAULT_POLL_SELECT) -> dict[str, Any]:
        """Fetch the latest command row. Returns empty dict when not found."""
        client = self._http_client()
        try:
            resp = client.get(
                f"{self.rest_url}/{REMOTE_COMMANDS_TABLE}",
                headers=self._headers(),
                params={"id": f"eq.{cmd_id}", "select": select},
            )
        finally:
            pass

        if resp.status_code not in (200, 206):
            raise TransportError(
                f"poll {REMOTE_COMMANDS_TABLE} failed: HTTP {resp.status_code}",
                status=resp.status_code,
                body=resp.text,
            )
        rows = resp.json()
        if not rows:
            return {}
        row = rows[0]
        return dict(row) if isinstance(row, dict) else {}

    def wait_for_terminal(
        self,
        cmd_id: str,
        *,
        command_timeout_seconds: int | None = None,
        on_poll: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Poll until the command reaches a terminal status or the budget expires."""
        cmd_timeout = (
            float(command_timeout_seconds)
            if command_timeout_seconds is not None
            else self.poll_timeout_s
        )
        deadline = time.time() + cmd_timeout + self.poll_grace_s
        last: dict[str, Any] = {}
        while time.time() < deadline:
            row = self.poll(cmd_id)
            if row:
                last = row
                if on_poll is not None:
                    on_poll(row)
                status = str(row.get("status") or "")
                if status in TERMINAL_STATUSES:
                    return row
            time.sleep(self.poll_interval_s)
        raise TrainerTimeoutError(
            f"command {cmd_id} did not reach a terminal status within "
            f"{cmd_timeout + self.poll_grace_s:.0f}s",
            cmd_id=cmd_id,
            body=last or None,
        )

    def request_cancel(self, cmd_id: str) -> dict[str, Any] | None:
        """Request cancellation of a pending/running command via Supabase RPC.

        Returns ``{"ok": True, "status": "CANCELLED"|"CANCEL_REQUESTED"}`` on success,
        ``{"ok": False, "status": "<terminal>"}`` if already terminal, or ``None`` on
        network/auth failure.
        """
        client = self._http_client()
        try:
            resp = client.post(
                f"{self.supabase_url}/rest/v1/rpc/areal_shell_request_cancel",
                headers=self._headers(prefer_representation=True),
                json={"p_id": cmd_id, "p_user_id": self.user_id},
            )
        except Exception:
            return None
        if resp.status_code not in (200, 201):
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None

    def send_and_wait(
        self,
        command: str,
        *,
        cwd: str | None = None,
        tmux_id: str | None = None,
        timeout_seconds: int | None = None,
        cmd_id: str | None = None,
        on_poll: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Enqueue a command and block until it reaches a terminal status."""
        resolved_id = self.send(
            command,
            cwd=cwd,
            tmux_id=tmux_id,
            timeout_seconds=timeout_seconds,
            cmd_id=cmd_id,
        )
        return self.wait_for_terminal(
            resolved_id,
            command_timeout_seconds=timeout_seconds,
            on_poll=on_poll,
        )

    def close(self) -> None:
        # Only close the lazy client we created; _external_client is caller-owned.
        if self._lazy_client is not None:
            self._lazy_client.close()
            self._lazy_client = None

    def __enter__(self) -> CLITrainTransport:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
