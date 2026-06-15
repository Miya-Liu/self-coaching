# SPDX-License-Identifier: MIT
"""Low-level HTTP client for AgentEvals (POST/GET /api/runs)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class AgentEvalsError(RuntimeError):
    """AgentEvals API or poll failure."""

    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


class AgentEvalsClient:
    """Minimal AgentEvals REST client (no extra dependencies)."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_s: float = 30.0,
        poll_interval_s: float | None = None,
        poll_timeout_s: float | None = None,
    ):
        self.base_url = (base_url or os.environ.get("AGENTEVALS_BASE_URL", "http://localhost:8080")).rstrip("/")
        self.timeout_s = timeout_s
        self._opener = self._build_opener(self.base_url)
        self.poll_interval_s = float(
            poll_interval_s if poll_interval_s is not None
            else os.environ.get("AGENTEVALS_POLL_INTERVAL_S", "5")
        )
        self.poll_timeout_s = float(
            poll_timeout_s if poll_timeout_s is not None
            else os.environ.get("AGENTEVALS_TIMEOUT_S", "3600")
        )

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_suites(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/api/suites")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "suites" in data:
            suites = data["suites"]
            return suites if isinstance(suites, list) else []
        return []

    def create_run(
        self,
        *,
        suite_id: str,
        agent_config: dict[str, Any],
        num_trials: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"suite_id": suite_id, "agent_config": agent_config}
        if num_trials is not None:
            body["num_trials"] = num_trials
        return self._request("POST", "/api/runs", body)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/runs/{run_id}")

    def wait_for_run(self, run_id: str) -> dict[str, Any]:
        deadline = time.time() + self.poll_timeout_s
        terminal = {"succeeded", "failed", "cancelled", "canceled"}
        last: dict[str, Any] | None = None
        while time.time() < deadline:
            last = self.get_run(run_id)
            status = str(last.get("status", "")).lower()
            if status in terminal:
                if status != "succeeded":
                    raise AgentEvalsError(
                        f"eval run {run_id} ended with status={status!r}",
                        body=last,
                    )
                return last
            time.sleep(self.poll_interval_s)
        raise AgentEvalsError(
            f"eval run {run_id} did not complete within {self.poll_timeout_s}s",
            body=last,
        )

    @staticmethod
    def _build_opener(base_url: str) -> urllib.request.OpenerDirector:
        """Bypass system proxy for localhost (Windows WinINET returns 503)."""
        host = (urllib.parse.urlparse(base_url).hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            return urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return urllib.request.build_opener()

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
            except Exception:
                err_body = exc.reason
            raise AgentEvalsError(
                f"{method} {url} failed: HTTP {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AgentEvalsError(f"{method} {url} failed: {exc}") from exc
