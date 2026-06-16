# SPDX-License-Identifier: MIT
"""Shared HTTP utilities for Pipeline Service clients."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class PipelineHTTPError(RuntimeError):
    """Pipeline Service HTTP API failure."""

    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


def resolve_pipeline_base_url(base_url: str | None = None) -> str:
    return (
        base_url
        or os.environ.get("PIPELINE_SERVICE_URL")
        or os.environ.get("SELF_QUESTIONING_URL")
        or "http://10.110.158.146:8001"
    ).rstrip("/")


def build_pipeline_opener(base_url: str) -> urllib.request.OpenerDirector:
    """Bypass system proxy for localhost (Windows WinINET returns 503)."""
    host = (urllib.parse.urlparse(base_url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


class PipelineHTTPBase:
    """Base class for typed Pipeline Service HTTP clients."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_s: float = 30.0,
    ):
        self.base_url = resolve_pipeline_base_url(base_url)
        self.timeout_s = timeout_s
        self._opener = build_pipeline_opener(self.base_url)

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
            raise PipelineHTTPError(
                f"{method} {url} failed: HTTP {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PipelineHTTPError(f"{method} {url} failed: {exc}") from exc
