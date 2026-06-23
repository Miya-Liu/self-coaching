# SPDX-License-Identifier: MIT
"""Shared HTTP utilities for trainer service clients (TrainerClient + RestClient)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class TrainerHTTPError(RuntimeError):
    """Trainer HTTP API failure."""

    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


def resolve_trainer_base_url(base_url: str | None = None) -> str:
    return (
        base_url
        or os.environ.get("TRAINER_BASE_URL")
        or os.environ.get("MOCK_AERL_URL")
        or os.environ.get("AERL_BASE_URL")
        or "http://localhost:8004"
    ).rstrip("/")


def resolve_trainer_api_key(api_key: str | None = None) -> str | None:
    return api_key or os.environ.get("TRAINER_API_KEY") or os.environ.get("AERL_API_KEY")


def build_trainer_opener(base_url: str) -> urllib.request.OpenerDirector:
    """Bypass system proxy for localhost (Windows WinINET returns 503)."""
    host = (urllib.parse.urlparse(base_url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


class TrainerHTTPBase:
    """Base class for typed trainer HTTP clients."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_s: float = 30.0,
        api_key: str | None = None,
    ):
        self.base_url = resolve_trainer_base_url(base_url)
        self.timeout_s = timeout_s
        self.api_key = resolve_trainer_api_key(api_key)
        self._opener = build_trainer_opener(self.base_url)

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
            raise TrainerHTTPError(
                f"{method} {url} failed: HTTP {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TrainerHTTPError(f"{method} {url} failed: {exc}") from exc

    def _request_text(self, method: str, path: str, payload: dict[str, Any] | None = None) -> str:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "text/plain", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                err_body = exc.reason
            raise TrainerHTTPError(
                f"{method} {url} failed: HTTP {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TrainerHTTPError(f"{method} {url} failed: {exc}") from exc
