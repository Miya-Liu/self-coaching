# SPDX-License-Identifier: MIT
"""HTTP client auth and header passthrough."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mock-services"))

import client as client_mod  # noqa: E402


def test_http_client_raises_auth_error_on_401(mock_server_authenticated):
    port, _ = mock_server_authenticated
    c = client_mod.HTTPClient(f"http://127.0.0.1:{port}", api_key="wrong-token")
    with pytest.raises(client_mod.AuthError):
        c.learn(event="should be unauthorized")


def test_http_client_sends_bearer_when_api_key_set(monkeypatch):
    monkeypatch.setenv("MOCK_SERVICE_TOKEN", "from-env")
    c = client_mod.HTTPClient("http://127.0.0.1:8765")
    assert c.api_key == "from-env"
