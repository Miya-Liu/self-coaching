# SPDX-License-Identifier: MIT
"""Shared pytest fixtures and import path for mock-services."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_SERVICES = REPO_ROOT / "mock-services"
MOCK_MAIN = MOCK_SERVICES / "mock_self_coaching.py"
MODES = REPO_ROOT / "modes"

if str(MOCK_SERVICES) not in sys.path:
    sys.path.insert(0, str(MOCK_SERVICES))

# modes/ on path so `import coach.registry` etc. resolves (package-style imports)
if str(MODES) not in sys.path:
    sys.path.insert(0, str(MODES))


# Localhost mock servers must never be reached through a system HTTP proxy
# (on Windows urllib honors WinINET proxy settings, which return 503 for
# 127.0.0.1 and make every fixture time out). This opener disables proxies.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(port: int, timeout: float = 15.0) -> None:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with _NO_PROXY_OPENER.open(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            last_err = e
            time.sleep(0.15)
    raise RuntimeError(f"mock service /health never came up on port {port}: {last_err}")


def _start_mock_server(root: Path, port: int, *, extra_env: dict[str, str] | None = None):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, str(MOCK_MAIN), "serve", "--root", str(root), "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _wait_for_health(port)
    return proc


def _stop_mock_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5.0)


@pytest.fixture(scope="module")
def mock_server(tmp_path_factory: pytest.TempPathFactory):
    """Yield (port, root) for a running mock HTTP server (one per test module)."""
    port = _free_port()
    root = tmp_path_factory.mktemp("http-demo")
    proc = _start_mock_server(root, port)
    try:
        yield port, root
    finally:
        _stop_mock_server(proc)


@pytest.fixture(scope="module")
def mock_server_authenticated(tmp_path_factory: pytest.TempPathFactory):
    port = _free_port()
    root = tmp_path_factory.mktemp("http-auth-demo")
    proc = _start_mock_server(root, port, extra_env={"MOCK_SERVICE_TOKEN": "test-secret"})
    try:
        yield port, root
    finally:
        _stop_mock_server(proc)


@pytest.fixture(scope="module")
def mock_server_small_body(tmp_path_factory: pytest.TempPathFactory):
    port = _free_port()
    root = tmp_path_factory.mktemp("http-body-demo")
    proc = _start_mock_server(root, port, extra_env={"MOCK_MAX_BODY_BYTES": "64"})
    try:
        yield port, root
    finally:
        _stop_mock_server(proc)
