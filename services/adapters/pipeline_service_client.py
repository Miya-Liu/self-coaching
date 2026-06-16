# SPDX-License-Identifier: MIT
"""PipelineServiceClient — Self-Questioning pipeline job lifecycle."""

from __future__ import annotations

import os
import time
import urllib.parse
from typing import Any

from .pipeline_http import PipelineHTTPBase, PipelineHTTPError

_TERMINAL_STATUSES = frozenset({"success", "failed"})


class PipelineServiceClient(PipelineHTTPBase):
    """HTTP client for the Self-Questioning Agent Pipeline Service."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_s: float = 30.0,
        poll_interval_s: float | None = None,
        poll_timeout_s: float | None = None,
    ):
        super().__init__(base_url, timeout_s=timeout_s)
        self.poll_interval_s = float(
            poll_interval_s
            if poll_interval_s is not None
            else os.environ.get("PIPELINE_POLL_INTERVAL_S", "5")
        )
        self.poll_timeout_s = float(
            poll_timeout_s
            if poll_timeout_s is not None
            else os.environ.get("PIPELINE_POLL_TIMEOUT_S", "3600")
        )

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def submit(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/pipeline/submit", body or {})

    def status(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/pipeline/status/{job_id}")

    def wait_for_job(self, job_id: str) -> dict[str, Any]:
        deadline = time.time() + self.poll_timeout_s
        last: dict[str, Any] | None = None
        while time.time() < deadline:
            last = self.status(job_id)
            job_status = str(last.get("status", "")).lower()
            if job_status in _TERMINAL_STATUSES:
                if job_status != "success":
                    raise PipelineHTTPError(
                        f"pipeline job {job_id} ended with status={job_status!r}",
                        body=last,
                    )
                return last
            time.sleep(self.poll_interval_s)
        raise PipelineHTTPError(
            f"pipeline job {job_id} did not complete within {self.poll_timeout_s}s",
            body=last,
        )

    def list_tasks(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"limit": str(limit)}
        if status:
            params["status"] = status
        query = urllib.parse.urlencode(params)
        return self._request("GET", f"/api/pipeline/tasks?{query}")

    def logs(self, job_id: str, *, lines: int = 100) -> dict[str, Any]:
        query = urllib.parse.urlencode({"lines": str(lines)})
        return self._request("GET", f"/api/pipeline/logs/{job_id}?{query}")

    def run_sync(
        self,
        body: dict[str, Any] | None = None,
        *,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        prev_timeout = self.timeout_s
        if timeout_s is not None:
            self.timeout_s = timeout_s
        try:
            return self._request("POST", "/api/pipeline/run_sync", body or {})
        finally:
            self.timeout_s = prev_timeout


__all__ = ["PipelineHTTPError", "PipelineServiceClient"]
