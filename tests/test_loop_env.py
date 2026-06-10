# SPDX-License-Identifier: MIT
"""Tests for modes/self-coaching/loop_env.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
if str(SC_ROOT) not in sys.path:
    sys.path.insert(0, str(SC_ROOT))

from loop_env import configure_demo_env, load_env_file, service_profile  # noqa: E402


def test_load_env_file_sets_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for key in list(os.environ):
        if key.startswith(("LOOP_", "MOCK_", "ORCHESTRATOR_", "AGENTEVALS_", "TRAINER_")):
            monkeypatch.delenv(key, raising=False)

    env_path = tmp_path / "demo.env"
    env_path.write_text(
        "LOOP_SERVICE_MODE=mock-http\nMOCK_SELF_LEARNING_PORT=39999\n",
        encoding="utf-8",
    )
    load_env_file(env_path)
    profile = configure_demo_env(env_file=env_path, with_http=False)
    assert profile.mode == "mock-http"
    assert os.environ["MOCK_SELF_LEARNING_URL"] == "http://127.0.0.1:39999"


def test_with_http_overrides_env_file_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for key in list(os.environ):
        if key.startswith(("LOOP_", "MOCK_", "ORCHESTRATOR_", "AGENTEVALS_", "TRAINER_")):
            monkeypatch.delenv(key, raising=False)

    env_path = tmp_path / "demo.env"
    env_path.write_text("LOOP_SERVICE_MODE=mock-module\n", encoding="utf-8")
    profile = configure_demo_env(env_file=env_path, with_http=True)
    assert profile.mode == "mock-http"


def test_mock_module_clears_service_urls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOOP_SERVICE_MODE", "mock-module")
    monkeypatch.setenv("MOCK_SELF_PLAY_URL", "http://127.0.0.1:8767")
    monkeypatch.setenv("AGENTEVALS_BASE_URL", "http://127.0.0.1:8080")
    profile = configure_demo_env(with_http=False)
    assert profile.mode == "mock-module"
    assert profile.service_urls == {}


def test_live_mode_keeps_urls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOOP_SERVICE_MODE", "live")
    monkeypatch.setenv("AGENTEVALS_BASE_URL", "https://agentevals.example")
    monkeypatch.setenv("TRAINER_BASE_URL", "https://aerl.example")
    profile = configure_demo_env()
    assert profile.mode == "live"
    assert profile.eval_backend == "agentevals"
    assert profile.train_backend == "aerl"
    assert profile.service_urls["AGENTEVALS_BASE_URL"] == "https://agentevals.example"
