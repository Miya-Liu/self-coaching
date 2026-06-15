# SPDX-License-Identifier: MIT
"""End-to-end smoke tests for the unified client across all 3 transports.

Each test exercises the full contract surface (health/learn/self_play/evaluate/
eval_report/train/run_all) through one transport, then asserts return-shape
invariants from the OpenAPI contract.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_SERVICES = REPO_ROOT / "mock-services"
SCRIPT = MOCK_SERVICES / "mock_self_coaching.py"

# Make `client` importable.
sys.path.insert(0, str(MOCK_SERVICES))

import client as client_mod  # noqa: E402


# --------------------------------------------------------------------------
# Shared invariants
# --------------------------------------------------------------------------

def _assert_contract_responses(c, root: Path) -> None:
    """Drive a client through the contract and assert response shapes."""
    # init is module-only; for CLI/HTTP we depend on the server having init'd
    # via run_all or the test setup.
    if isinstance(c, client_mod.ModuleClient):
        # Use the module to bootstrap so subsequent calls have a populated root.
        c._mod.init(root)  # type: ignore[attr-defined]

    learn = c.learn(event="agent forgot to verify side effect", capability="tool_use")
    assert "id" in learn and "timestamp" in learn
    assert learn["event"]

    play = c.self_play(capability="tool_use", n=2)
    assert play["status"] == "generated"
    assert play["count"] == len(play["case_ids"]) == 2

    eval_summary = c.evaluate(candidate="cand-A", baseline="cand-B")
    assert eval_summary["status"] in {"passed", "failed"}
    assert eval_summary["recommendation"] in {"promote", "do_not_promote"}
    assert eval_summary["run_id"]

    report = c.eval_report(eval_summary["run_id"])
    assert report["run_id"] == eval_summary["run_id"]
    assert "scores" in report and "overall" in report["scores"]

    train = c.train(pipeline="sft", base_model="mock-base")
    assert train["status"] in {"trained", "accepted"}
    assert train["run_id"]

    full = c.run_all(capability="tool_use", pipeline="sft")
    assert full["status"] == "ok"
    assert "promotion_allowed" in full


# --------------------------------------------------------------------------
# ModuleClient
# --------------------------------------------------------------------------

def test_module_client_full_contract(tmp_path):
    c = client_mod.build_client("module", root=tmp_path)
    _assert_contract_responses(c, tmp_path)


# --------------------------------------------------------------------------
# CLIClient
# --------------------------------------------------------------------------

def test_cli_client_full_contract(tmp_path):
    c = client_mod.build_client("cli", root=tmp_path)
    # Init via the module first (CLI doesn't change semantics).
    sys.path.insert(0, str(MOCK_SERVICES))
    import mock_self_coaching as msc
    msc.init(tmp_path)
    _assert_contract_responses(c, tmp_path)


# --------------------------------------------------------------------------
# HTTPClient
# --------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(base_url: str, timeout_s: float = 15.0) -> None:
    # Bypass system proxy for localhost (Windows WinINET can intercept 127.0.0.1).
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + timeout_s
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            with opener.open(f"{base_url}/health", timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_exc = exc
        time.sleep(0.2)
    raise RuntimeError(f"mock service never became ready: {last_exc}")


@pytest.fixture
def http_service(tmp_path):
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "serve",
         "--host", "127.0.0.1", "--port", str(port),
         "--root", str(tmp_path)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_health(f"http://127.0.0.1:{port}")
        yield f"http://127.0.0.1:{port}", tmp_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_http_client_full_contract(http_service):
    base_url, root = http_service
    c = client_mod.build_client("http", base_url=base_url)
    health = c.health()
    assert health["status"] == "ok"
    # The HTTP server already init'd itself; just run the contract.
    _assert_contract_responses(c, root)


def test_http_client_retry_on_connect_failure():
    """Connect failure to a dead port should raise TransportError, not hang."""
    c = client_mod.HTTPClient(
        "http://127.0.0.1:1",  # reserved port — refuses immediately
        timeout=1.0, max_retries=2, backoff_initial_s=0.05, backoff_factor=1.0,
    )
    with pytest.raises(client_mod.TransportError):
        c.health()


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------

def test_build_client_unknown_transport():
    with pytest.raises(ValueError):
        client_mod.build_client("grpc")
