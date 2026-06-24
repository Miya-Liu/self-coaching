# SPDX-License-Identifier: MIT
"""PipelineServiceClient — Self-Questioning pipeline job lifecycle."""

from __future__ import annotations

import os
import time
import urllib.parse
from typing import Any

from .pipeline_http import PipelineHTTPBase, PipelineHTTPError
from .step_log import step_log

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
        started = time.time()
        last_status: str | None = None
        last_heartbeat = started
        while time.time() < deadline:
            last = self.status(job_id)
            job_status = str(last.get("status", "")).lower()
            stage_results = last.get("stage_results")
            stage_hint = ""
            if isinstance(stage_results, dict) and stage_results:
                done = sum(1 for v in stage_results.values() if v)
                stage_hint = f", stages={done}/{len(stage_results)}"
            elapsed = time.time() - started
            if job_status != last_status:
                step_log(
                    "pipeline",
                    f"job {job_id}: status={job_status or 'unknown'}{stage_hint} ({elapsed:.0f}s elapsed)",
                )
                last_status = job_status
                last_heartbeat = time.time()
            elif time.time() - last_heartbeat >= 60:
                step_log(
                    "pipeline",
                    f"job {job_id}: still {job_status or 'unknown'}{stage_hint} ({elapsed:.0f}s elapsed)",
                )
                last_heartbeat = time.time()
            if job_status in _TERMINAL_STATUSES:
                if job_status != "success":
                    raise PipelineHTTPError(
                        f"pipeline job {job_id} ended with status={job_status!r}",
                        body=last,
                    )
                step_log("pipeline", f"job {job_id}: finished success ({elapsed:.0f}s)")
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
        effective_timeout = timeout_s if timeout_s is not None else self.timeout_s
        return self._request(
            "POST", "/api/pipeline/run_sync", body or {}, timeout_s=effective_timeout
        )


__all__ = ["PipelineHTTPError", "PipelineServiceClient"]
