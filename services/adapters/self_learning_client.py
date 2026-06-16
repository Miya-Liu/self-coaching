# SPDX-License-Identifier: MIT
"""HTTP client for the self-learning service (POST /learning/events, /learning/evolve*)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class SelfLearningError(RuntimeError):
    """Self-learning API failure."""

    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


class SelfLearningClient:
    """HTTP client for the self-learning service.

    Endpoints:
        POST /learning/events         — record a learning event
        POST /learning/classify       — classify an event string
        POST /learning/evolve         — evolve from specific sessions
        POST /learning/evolve/recent  — evolve from recent events
        GET  /learning/status/{id}    — poll evolve job status
        POST /learning/optout         — opt-out a session from training
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_s: float = 30.0,
        poll_interval_s: float | None = None,
        poll_timeout_s: float | None = None,
        api_key: str | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("SELF_LEARNING_BASE_URL")
            or os.environ.get("MOCK_SELF_LEARNING_URL")
            or "http://localhost:8766"
        ).rstrip("/")
        self.timeout_s = timeout_s
        self.poll_interval_s = float(
            poll_interval_s if poll_interval_s is not None
            else os.environ.get("SELF_LEARNING_POLL_INTERVAL_S", "2")
        )
        self.poll_timeout_s = float(
            poll_timeout_s if poll_timeout_s is not None
            else os.environ.get("SELF_LEARNING_TIMEOUT_S", "300")
        )
        self.api_key = (
            api_key
            or os.environ.get("AGENT_API_TOKEN")
            or os.environ.get("SELF_LEARNING_API_KEY")
        )
        self._opener = self._build_opener(self.base_url)

    @staticmethod
    def _build_opener(base_url: str) -> urllib.request.OpenerDirector:
        """Bypass system proxy for localhost targets."""
        host = (urllib.parse.urlparse(base_url).hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            return urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return urllib.request.build_opener()

    # ── Public API ──────────────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/learning/health")

    def learn(
        self,
        *,
        event: str,
        source: str = "client",
        capability: str = "tool_use",
        coaching_root: str | None = None,
    ) -> dict[str, Any]:
        """Record a learning event."""
        body: dict[str, Any] = {
            "event": event,
            "source": source,
            "capability": capability,
        }
        if coaching_root:
            body["coaching_root"] = coaching_root
        return self._request("POST", "/learning/events", body)

    def classify(self, event: str, *, capability: str = "tool_use") -> dict[str, Any]:
        """Classify a learning event into artifact types."""
        return self._request("POST", "/learning/classify", {
            "event": event,
            "capability": capability,
        })

    def evolve(
        self,
        *,
        session_ids: list[str],
        coaching_root: str | None = None,
        capability: str = "tool_use",
        wait: bool = True,
    ) -> dict[str, Any]:
        """Trigger evolution from specific session IDs.

        If wait=True (default), polls until the job completes or times out.
        """
        body: dict[str, Any] = {
            "session_ids": session_ids,
            "capability": capability,
        }
        if coaching_root:
            body["coaching_root"] = coaching_root
        result = self._request("POST", "/learning/evolve", body)
        if not wait:
            return result
        job_id = result.get("job_id")
        if job_id:
            return self.wait_for_job(job_id)
        return result

    def evolve_recent(
        self,
        *,
        coaching_root: str | None = None,
        capability: str = "tool_use",
        limit: int | None = None,
        wait: bool = True,
    ) -> dict[str, Any]:
        """Trigger evolution from recent events.

        If wait=True (default), polls until the job completes or times out.
        """
        body: dict[str, Any] = {"capability": capability}
        if coaching_root:
            body["coaching_root"] = coaching_root
        if limit is not None:
            body["limit"] = limit
        result = self._request("POST", "/learning/evolve/recent", body)
        if not wait:
            return result
        job_id = result.get("job_id")
        if job_id:
            return self.wait_for_job(job_id)
        return result

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Poll a running evolve job."""
        return self._request("GET", f"/learning/status/{job_id}")

    def wait_for_job(self, job_id: str) -> dict[str, Any]:
        """Poll until an evolve job reaches a terminal state."""
        terminal = {"succeeded", "completed", "failed", "cancelled", "canceled"}
        deadline = time.time() + self.poll_timeout_s
        last: dict[str, Any] | None = None
        while time.time() < deadline:
            last = self.get_job_status(job_id)
            status = str(last.get("status", "")).lower()
            if status in terminal:
                if status in ("failed", "cancelled", "canceled"):
                    raise SelfLearningError(
                        f"evolve job {job_id} ended with status={status!r}",
                        body=last,
                    )
                return last
            time.sleep(self.poll_interval_s)
        raise SelfLearningError(
            f"evolve job {job_id} did not complete within {self.poll_timeout_s}s",
            body=last,
        )

    def optout(self, session_id: str) -> dict[str, Any]:
        """Opt-out a session from training data."""
        return self._request("POST", "/learning/optout", {"session_id": session_id})

    # ── Low-level ───────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers: dict[str, str] = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
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
            raise SelfLearningError(
                f"{method} {url} failed: HTTP {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SelfLearningError(f"{method} {url} failed: {exc}") from exc
