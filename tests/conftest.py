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

if str(MOCK_SERVICES) not in sys.path:
    sys.path.insert(0, str(MOCK_SERVICES))


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
            with urllib.request.urlopen(url, timeout=1.0) as resp:
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


@pytest.fixture
def mock_server(tmp_path: Path):
    """Yield (port, root) for a running mock HTTP server."""
    port = _free_port()
    root = tmp_path / "http-demo"
    proc = _start_mock_server(root, port)
    try:
        yield port, root
    finally:
        _stop_mock_server(proc)


@pytest.fixture
def mock_server_authenticated(tmp_path: Path):
    port = _free_port()
    root = tmp_path / "http-auth-demo"
    proc = _start_mock_server(root, port, extra_env={"MOCK_SERVICE_TOKEN": "test-secret"})
    try:
        yield port, root
    finally:
        _stop_mock_server(proc)


@pytest.fixture
def mock_server_small_body(tmp_path: Path):
    port = _free_port()
    root = tmp_path / "http-body-demo"
    proc = _start_mock_server(root, port, extra_env={"MOCK_MAX_BODY_BYTES": "64"})
    try:
        yield port, root
    finally:
        _stop_mock_server(proc)
