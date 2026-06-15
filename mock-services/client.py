# SPDX-License-Identifier: MIT
"""Unified Python client for the self-coaching service contract.

Three interchangeable transports, ALL exposing the same method names so callers
can swap between them without code changes:

  - ModuleClient (in-process): direct calls into mock_self_coaching.py.
                               Fastest, zero serialization, only works when the
                               target IS the mock implementation (same process).

  - CLIClient   (subprocess):  shells out to `python mock_self_coaching.py <cmd>`.
                               Useful for sandboxed/isolated runs and for testing
                               that the CLI contract is intact.

  - HTTPClient  (network):     POSTs JSON to a running service. This is the
                               interface real production services implement (see
                               `contracts/openapi.yaml`).

Usage:
    from client import HTTPClient, ModuleClient, CLIClient, build_client

    client = build_client("http", base_url="http://127.0.0.1:8765")
    client.learn(event="agent forgot verification", capability="tool_use")
    play = client.self_play(capability="tool_use", n=4)
    eval_summary = client.evaluate(candidate="cand-v2", baseline="cand-v1")
    report = client.eval_report(eval_summary["run_id"])

The shared interface is the `SelfCoachingClient` Protocol below.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ----------------------------------------------------------------------------
# Shared interface
# ----------------------------------------------------------------------------

@runtime_checkable
class SelfCoachingClient(Protocol):
    """Common interface every transport implements."""

    def health(self) -> dict[str, Any]: ...
    def learn(self, *, event: str, source: str = "client",
              capability: str = "tool_use") -> dict[str, Any]: ...
    def self_play(self, *, capability: str = "tool_use",
                  n: int = 3) -> dict[str, Any]: ...
    def evaluate(self, *, candidate: str = "mock-candidate-v1",
                 baseline: str = "mock-baseline-v0") -> dict[str, Any]: ...
    def eval_report(self, run_id: str) -> dict[str, Any]: ...
    def train(self, *, pipeline: str = "sft",
              dataset: str | None = None,
              base_model: str = "mock-base") -> dict[str, Any]: ...
    def run_all(self, *, capability: str = "tool_use",
                pipeline: str = "sft") -> dict[str, Any]: ...


# ----------------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------------

class SelfCoachingError(RuntimeError):
    """Base error for any client transport."""


class ServiceError(SelfCoachingError):
    """Service returned a non-2xx response or a structured error body."""

    def __init__(self, status: int, body: dict[str, Any] | str):
        self.status = status
        self.body = body
        super().__init__(f"service returned {status}: {body!r}")


class AuthError(ServiceError):
    """Missing or invalid bearer token (HTTP 401)."""


class TransportError(SelfCoachingError):
    """Network / subprocess / import-level failure."""


# ----------------------------------------------------------------------------
# In-process module client
# ----------------------------------------------------------------------------

class ModuleClient:
    """Direct calls into the mock implementation (or any module exposing the
    same six top-level functions)."""

    def __init__(self, root: str | Path, *, module_name: str = "mock_self_coaching"):
        try:
            self._mod = __import__(module_name)
        except ImportError as exc:
            raise TransportError(
                f"cannot import '{module_name}' — add mock-services/ to sys.path or "
                f"point module_name= at your real implementation"
            ) from exc
        self._root = Path(root)

    def health(self) -> dict[str, Any]:
        # No health primitive in the module API; synthesize one.
        version = getattr(self._mod, "VERSION", "unknown")
        return {"status": "ok", "version": version, "root": str(self._root)}

    def learn(self, *, event: str, source: str = "client",
              capability: str = "tool_use") -> dict[str, Any]:
        return self._mod.learn(self._root, event, source, capability)

    def self_play(self, *, capability: str = "tool_use", n: int = 3) -> dict[str, Any]:
        return self._mod.self_play(self._root, capability, n)

    def evaluate(self, *, candidate: str = "mock-candidate-v1",
                 baseline: str = "mock-baseline-v0") -> dict[str, Any]:
        return self._mod.evaluate(self._root, candidate, baseline)

    def eval_report(self, run_id: str) -> dict[str, Any]:
        path = self._root / ".self-coaching" / "reports" / "eval_runs" / run_id / "report.json"
        if not path.is_file():
            raise ServiceError(404, {"error": "report not found", "run_id": run_id})
        return json.loads(path.read_text(encoding="utf-8"))

    def train(self, *, pipeline: str = "sft", dataset: str | None = None,
              base_model: str = "mock-base") -> dict[str, Any]:
        return self._mod.train(self._root, pipeline, dataset, base_model)

    def run_all(self, *, capability: str = "tool_use",
                pipeline: str = "sft") -> dict[str, Any]:
        return self._mod.run_all(self._root, capability, pipeline)


# ----------------------------------------------------------------------------
# CLI subprocess client
# ----------------------------------------------------------------------------

class CLIClient:
    """Shells out to `python mock_self_coaching.py ...`.

    Useful for isolated runs (separate process, separate env) and for asserting
    the CLI contract documented in README.md is intact.
    """

    def __init__(self, root: str | Path, *, script: str | Path | None = None,
                 python: str | None = None):
        self._root = Path(root)
        self._script = Path(script) if script else (
            Path(__file__).resolve().parent / "mock_self_coaching.py"
        )
        if not self._script.is_file():
            raise TransportError(f"CLI script not found: {self._script}")
        self._python = python or sys.executable

    def _run(self, *args: str) -> dict[str, Any]:
        cmd = [self._python, str(self._script), *args]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                check=False, timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TransportError(f"CLI invocation failed: {exc}") from exc
        if proc.returncode != 0:
            raise ServiceError(
                status=proc.returncode,
                body={"stderr": proc.stderr.strip(), "stdout": proc.stdout.strip()},
            )
        text = proc.stdout.strip()
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
            # Pretty-printed multi-line JSON: find the first object.
            start = text.find("{")
            if start >= 0:
                try:
                    return json.loads(text[start:])
                except json.JSONDecodeError:
                    pass
        return {"status": "ok", "stdout": proc.stdout, "stderr": proc.stderr}

    def health(self) -> dict[str, Any]:
        # No `health` CLI subcommand; we infer by trying `init` on a temp dir
        # would be invasive. Just affirm the script is invocable.
        return {"status": "ok", "transport": "cli", "script": str(self._script)}

    def learn(self, *, event: str, source: str = "client",
              capability: str = "tool_use") -> dict[str, Any]:
        return self._run("learn", "--root", str(self._root),
                         "--event", event, "--source", source,
                         "--capability", capability)

    def self_play(self, *, capability: str = "tool_use", n: int = 3) -> dict[str, Any]:
        return self._run("self-play", "--root", str(self._root),
                         "--capability", capability, "--n", str(n))

    def evaluate(self, *, candidate: str = "mock-candidate-v1",
                 baseline: str = "mock-baseline-v0") -> dict[str, Any]:
        return self._run("evaluate", "--root", str(self._root),
                         "--candidate", candidate, "--baseline", baseline)

    def eval_report(self, run_id: str) -> dict[str, Any]:
        # No dedicated CLI verb for fetching a report; read from disk directly.
        path = self._root / ".self-coaching" / "reports" / "eval_runs" / run_id / "report.json"
        if not path.is_file():
            raise ServiceError(404, {"error": "report not found", "run_id": run_id})
        return json.loads(path.read_text(encoding="utf-8"))

    def train(self, *, pipeline: str = "sft", dataset: str | None = None,
              base_model: str = "mock-base") -> dict[str, Any]:
        args = ["train", "--root", str(self._root), "--pipeline", pipeline,
                "--base-model", base_model]
        if dataset is not None:
            args += ["--dataset", dataset]
        return self._run(*args)

    def run_all(self, *, capability: str = "tool_use",
                pipeline: str = "sft") -> dict[str, Any]:
        return self._run("run-all", "--root", str(self._root),
                         "--capability", capability, "--pipeline", pipeline)


# ----------------------------------------------------------------------------
# HTTP client (THE integration surface real services implement)
# ----------------------------------------------------------------------------

class HTTPClient:
    """JSON-over-HTTP client for the contract in `contracts/openapi.yaml`.

    Includes retry-with-backoff for transient network failures (connect errors
    and 5xx). Idempotent verbs (GET, health) are always retried; POST is
    retried only on connect-time failures to avoid double-submitting work.

    Localhost targets bypass any system HTTP proxy by default. On Windows,
    urllib honors WinINET proxy settings, which can intercept 127.0.0.1 and
    return 503; bypassing avoids that. Set ``trust_env_proxy=True`` (or env
    ``SELF_COACHING_TRUST_PROXY=1``) to honor proxy settings even for
    localhost.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8765", *,
                 api_key: str | None = None,
                 default_headers: dict[str, str] | None = None,
                 timeout: float = 30.0,
                 max_retries: int = 3,
                 backoff_initial_s: float = 0.5,
                 backoff_factor: float = 2.0,
                 trust_env_proxy: bool | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("MOCK_SERVICE_TOKEN")
        self.default_headers = dict(default_headers or {})
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.backoff_initial_s = backoff_initial_s
        self.backoff_factor = backoff_factor
        if trust_env_proxy is None:
            trust_env_proxy = os.environ.get("SELF_COACHING_TRUST_PROXY", "").lower() in ("1", "true", "yes")
        self._opener = self._build_opener(self.base_url, trust_env_proxy)

    @staticmethod
    def _build_opener(base_url: str, trust_env_proxy: bool) -> urllib.request.OpenerDirector:
        host = (urllib.parse.urlparse(base_url).hostname or "").lower()
        is_local = host in ("localhost", "127.0.0.1", "::1")
        if is_local and not trust_env_proxy:
            # Empty ProxyHandler disables all proxies for this opener.
            return urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return urllib.request.build_opener()

    # ---- low-level ----

    def _request(self, method: str, path: str,
                 payload: dict[str, Any] | None = None,
                 *, idempotent: bool = False,
                 headers: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        hdrs: dict[str, str] = {"Accept": "application/json", **self.default_headers}
        if headers:
            hdrs.update(headers)
        if self.api_key:
            hdrs["Authorization"] = f"Bearer {self.api_key}"
        if body is not None:
            hdrs["Content-Type"] = "application/json"
            if method == "POST" and "Idempotency-Key" not in hdrs:
                hdrs["Idempotency-Key"] = str(uuid.uuid4())
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)

        retries_allowed = self.max_retries if (idempotent or method == "GET") else 1
        delay = self.backoff_initial_s
        last_exc: Exception | None = None

        for attempt in range(1, max(retries_allowed, 1) + 1):
            try:
                with self._opener.open(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    if not raw:
                        return {}
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise TransportError(f"non-JSON response from {url}: {raw[:200]!r}") from exc
            except urllib.error.HTTPError as exc:
                # 5xx is retryable for idempotent calls; 4xx surfaces immediately.
                err_body: dict[str, Any] | str
                try:
                    err_body = json.loads(exc.read().decode("utf-8"))
                except Exception:
                    err_body = str(exc)
                if exc.code == 401:
                    raise AuthError(exc.code, err_body) from exc
                if 500 <= exc.code < 600 and idempotent and attempt < retries_allowed:
                    last_exc = exc
                else:
                    raise ServiceError(exc.code, err_body) from exc
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
                last_exc = exc
                if attempt >= retries_allowed:
                    raise TransportError(f"{method} {url} failed: {exc}") from exc
            time.sleep(delay)
            delay *= self.backoff_factor

        # Should be unreachable.
        raise TransportError(f"{method} {url} exhausted retries: {last_exc}")

    # ---- contract methods ----

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", idempotent=True)

    def learn(self, *, event: str, source: str = "client",
              capability: str = "tool_use") -> dict[str, Any]:
        return self._request("POST", "/learning/events",
                             {"event": event, "source": source, "capability": capability})

    def self_play(self, *, capability: str = "tool_use", n: int = 3) -> dict[str, Any]:
        return self._request("POST", "/self-play/generate",
                             {"capability": capability, "n": n})

    def evaluate(self, *, candidate: str = "mock-candidate-v1",
                 baseline: str = "mock-baseline-v0") -> dict[str, Any]:
        return self._request("POST", "/eval/runs",
                             {"candidate": candidate, "baseline": baseline})

    def eval_report(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/eval/runs/{run_id}/report", idempotent=True)

    def train(self, *, pipeline: str = "sft", dataset: str | None = None,
              base_model: str = "mock-base") -> dict[str, Any]:
        payload: dict[str, Any] = {"pipeline": pipeline, "base_model": base_model}
        if dataset is not None:
            payload["dataset"] = dataset
        return self._request("POST", "/training/runs", payload)

    def run_all(self, *, capability: str = "tool_use",
                pipeline: str = "sft") -> dict[str, Any]:
        return self._request("POST", "/pipeline/run-all",
                             {"capability": capability, "pipeline": pipeline})


# ----------------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------------

def build_client(transport: str, **kwargs: Any) -> SelfCoachingClient:
    """Construct a client by transport name.

    Args:
        transport: One of "module", "cli", "http".
        **kwargs: Forwarded to the constructor. The required kwargs are:
            module: root=...
            cli:    root=..., script=... (optional), python=... (optional)
            http:   base_url=...

    Returns:
        A client satisfying the SelfCoachingClient protocol.
    """
    transport = transport.lower()
    if transport == "module":
        return ModuleClient(**kwargs)
    if transport == "cli":
        return CLIClient(**kwargs)
    if transport == "http":
        return HTTPClient(**kwargs)
    raise ValueError(f"unknown transport: {transport!r} (use 'module', 'cli', or 'http')")


__all__ = [
    "SelfCoachingClient",
    "ModuleClient",
    "CLIClient",
    "HTTPClient",
    "SelfCoachingError",
    "ServiceError",
    "AuthError",
    "TransportError",
    "build_client",
]
