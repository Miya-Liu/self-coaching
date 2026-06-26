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

from .step_log import step_log


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
        self.base_url = (base_url or os.environ.get("AGENTEVALS_BASE_URL", "http://10.110.158.144:8080")).rstrip("/")
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

    # -----------------------------------------------------------------------
    # Trace Evals API
    # -----------------------------------------------------------------------

    def create_trace_eval(
        self,
        *,
        agent_id: str,
        start_time: str,
        end_time: str,
        sample_count: int,
        agent_config: dict[str, Any],
        seed: int | None = None,
        status_filter: list[str] | None = None,
        parallel: bool = True,
        max_concurrent: int = 4,
    ) -> dict[str, Any]:
        """POST /api/trace-evals — create a trace evaluation run."""
        body: dict[str, Any] = {
            "agent_id": agent_id,
            "start_time": start_time,
            "end_time": end_time,
            "sample_count": sample_count,
            "agent_config": agent_config,
            "parallel": parallel,
            "max_concurrent": max_concurrent,
        }
        if seed is not None:
            body["seed"] = seed
        if status_filter is not None:
            body["status_filter"] = status_filter
        return self._request("POST", "/api/trace-evals", body)

    def get_trace_eval(self, run_id: str) -> dict[str, Any]:
        """GET /api/trace-evals/{run_id} — get trace eval detail."""
        return self._request("GET", f"/api/trace-evals/{run_id}")

    def list_trace_evals(self, *, status: str | None = None) -> list[dict[str, Any]]:
        """GET /api/trace-evals — list trace eval runs."""
        path = "/api/trace-evals"
        if status:
            path += f"?status={urllib.parse.quote(status)}"
        data = self._request("GET", path)
        return data if isinstance(data, list) else []

    def wait_for_trace_eval(self, run_id: str) -> dict[str, Any]:
        """Poll GET /api/trace-evals/{run_id} until terminal status."""
        deadline = time.time() + self.poll_timeout_s
        terminal = {"succeeded", "failed", "cancelled", "canceled"}
        last: dict[str, Any] | None = None
        started = time.time()
        last_status: str | None = None
        last_heartbeat = started
        while time.time() < deadline:
            last = self.get_trace_eval(run_id)
            status = str(last.get("status", "")).lower()
            elapsed = time.time() - started
            if status != last_status:
                step_log("trace-eval", f"run {run_id}: status={status or 'unknown'} ({elapsed:.0f}s elapsed)")
                last_status = status
                last_heartbeat = time.time()
            elif time.time() - last_heartbeat >= 60:
                step_log("trace-eval", f"run {run_id}: still {status or 'unknown'} ({elapsed:.0f}s elapsed)")
                last_heartbeat = time.time()
            if status in terminal:
                if status != "succeeded":
                    raise AgentEvalsError(
                        f"trace eval run {run_id} ended with status={status!r}",
                        body=last,
                    )
                step_log("trace-eval", f"run {run_id}: finished succeeded ({elapsed:.0f}s)")
                return last
            time.sleep(self.poll_interval_s)
        raise AgentEvalsError(
            f"trace eval run {run_id} did not complete within {self.poll_timeout_s}s",
            body=last,
        )

    # -----------------------------------------------------------------------
    # Evolution / Scorecards API
    # -----------------------------------------------------------------------

    def create_protocol_run(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /api/evals/protocols/run — create an evolution protocol run."""
        return self._request("POST", "/api/evals/protocols/run", body)

    def get_protocol_run(self, run_id: str) -> dict[str, Any]:
        """GET /api/evals/protocols/run/{run_id}."""
        return self._request("GET", f"/api/evals/protocols/run/{run_id}")

    def get_scorecard(self, run_id: str) -> dict[str, Any]:
        """GET /api/evals/scorecards/{run_id}."""
        return self._request("GET", f"/api/evals/scorecards/{run_id}")

    def get_evolution_timeline(self, agent_id: str) -> list[dict[str, Any]]:
        """GET /api/evals/evolution/{agent_id}/timeline."""
        data = self._request("GET", f"/api/evals/evolution/{urllib.parse.quote(agent_id)}/timeline")
        return data if isinstance(data, list) else []

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
        started = time.time()
        last_status: str | None = None
        last_heartbeat = started
        while time.time() < deadline:
            last = self.get_run(run_id)
            status = str(last.get("status", "")).lower()
            elapsed = time.time() - started
            if status != last_status:
                step_log("agentevals", f"run {run_id}: status={status or 'unknown'} ({elapsed:.0f}s elapsed)")
                last_status = status
                last_heartbeat = time.time()
            elif time.time() - last_heartbeat >= 60:
                step_log("agentevals", f"run {run_id}: still {status or 'unknown'} ({elapsed:.0f}s elapsed)")
                last_heartbeat = time.time()
            if status in terminal:
                if status != "succeeded":
                    raise AgentEvalsError(
                        f"eval run {run_id} ended with status={status!r}",
                        body=last,
                    )
                step_log("agentevals", f"run {run_id}: finished succeeded ({elapsed:.0f}s)")
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
