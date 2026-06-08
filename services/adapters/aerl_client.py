# SPDX-License-Identifier: MIT
"""Low-level HTTP client for AERL (POST/GET /v1/training/runs)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


class AERLError(RuntimeError):
    """AERL API or poll failure."""

    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


class AERLClient:
    """Minimal AERL REST client (no extra dependencies)."""

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
            or os.environ.get("TRAINER_BASE_URL")
            or os.environ.get("AERL_BASE_URL")
            or "http://localhost:8004"
        ).rstrip("/")
        self.timeout_s = timeout_s
        self.poll_interval_s = float(
            poll_interval_s if poll_interval_s is not None
            else os.environ.get("AERL_POLL_INTERVAL_S", "2")
        )
        self.poll_timeout_s = float(
            poll_timeout_s if poll_timeout_s is not None
            else os.environ.get("AERL_TIMEOUT_S", "3600")
        )
        self.api_key = api_key or os.environ.get("TRAINER_API_KEY") or os.environ.get("AERL_API_KEY")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def create_training_run(
        self,
        *,
        pipeline_id: str,
        base_model: str,
        dataset_refs: list[str] | None = None,
        agent_id: str | None = None,
        coaching_root: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "pipeline_id": pipeline_id,
            "base_model": base_model,
        }
        if dataset_refs:
            body["dataset_refs"] = dataset_refs
        if agent_id:
            body["agent_id"] = agent_id
        if coaching_root:
            body["coaching_root"] = coaching_root
        return self._request("POST", "/v1/training/runs", body)

    def get_training_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/training/runs/{run_id}")

    def wait_for_training_run(self, run_id: str) -> dict[str, Any]:
        deadline = time.time() + self.poll_timeout_s
        terminal = {"succeeded", "failed", "cancelled", "canceled"}
        last: dict[str, Any] | None = None
        while time.time() < deadline:
            last = self.get_training_run(run_id)
            status = str(last.get("status", "")).lower()
            if status in terminal:
                if status != "succeeded":
                    raise AERLError(
                        f"training run {run_id} ended with status={status!r}",
                        body=last,
                    )
                return last
            time.sleep(self.poll_interval_s)
        raise AERLError(
            f"training run {run_id} did not complete within {self.poll_timeout_s}s",
            body=last,
        )

    def run_pipeline_argv(self, pipeline_id: str, argv: list[str]) -> str:
        url = f"{self.base_url}/v1/pipelines/{pipeline_id}/run"
        body = json.dumps({"argv": argv}).encode("utf-8")
        headers = {"Accept": "text/plain", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                err_body = exc.reason
            raise AERLError(
                f"POST {url} failed: HTTP {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AERLError(f"POST {url} failed: {exc}") from exc

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
            except Exception:
                err_body = exc.reason
            raise AERLError(
                f"{method} {url} failed: HTTP {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AERLError(f"{method} {url} failed: {exc}") from exc
