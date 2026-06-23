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

from loop_env import build_loop_client, configure_demo_env, load_env_file, service_profile  # noqa: E402

_ENV_PREFIXES = ("LOOP_", "MOCK_", "ORCHESTRATOR_", "AGENTEVALS_", "TRAINER_", "AGENT_")


@pytest.fixture(autouse=True)
def _isolate_env():
    """Ensure configure_demo_env side effects don't leak to other test modules.

    configure_demo_env mutates os.environ directly (by design — it configures
    the process for a demo run). In tests we snapshot and restore the relevant
    keys so later test modules aren't affected.
    """
    snapshot = {k: os.environ[k] for k in list(os.environ) if k.startswith(_ENV_PREFIXES)}
    yield
    # Remove any keys added during the test
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIXES) and key not in snapshot:
            del os.environ[key]
    # Restore original values
    for key, value in snapshot.items():
        os.environ[key] = value


def test_load_env_file_sets_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for key in list(os.environ):
        if key.startswith(("LOOP_", "MOCK_", "ORCHESTRATOR_", "AGENTEVALS_", "TRAINER_", "AGENT_")):
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
        if key.startswith(("LOOP_", "MOCK_", "ORCHESTRATOR_", "AGENTEVALS_", "TRAINER_", "AGENT_")):
            monkeypatch.delenv(key, raising=False)

    env_path = tmp_path / "demo.env"
    env_path.write_text("LOOP_SERVICE_MODE=mock-module\n", encoding="utf-8")
    profile = configure_demo_env(env_file=env_path, with_http=True)
    assert profile.mode == "mock-http"


def test_mock_module_clears_service_urls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOOP_SERVICE_MODE", "mock-module")
    monkeypatch.setenv("MOCK_SELF_QUESTIONING_URL", "http://127.0.0.1:8767")
    monkeypatch.setenv("AGENTEVALS_BASE_URL", "http://127.0.0.1:8080")
    profile = configure_demo_env(with_http=False)
    assert profile.mode == "mock-module"
    assert profile.service_urls == {}


def test_build_loop_client_mock_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "mock")
    monkeypatch.setenv("ORCHESTRATOR_TRAIN_BACKEND", "mock")
    monkeypatch.setenv("ORCHESTRATOR_TRANSPORT", "module")

    client = build_loop_client(tmp_path)
    assert hasattr(client, "learn")
    assert hasattr(client, "train")


def test_live_agentevals_only_keeps_mock_train(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOOP_SERVICE_MODE", "live")
    monkeypatch.setenv("AGENTEVALS_BASE_URL", "http://localhost:8080")
    monkeypatch.delenv("TRAINER_BASE_URL", raising=False)
    monkeypatch.delenv("MOCK_AERL_URL", raising=False)
    profile = configure_demo_env()
    assert profile.eval_backend == "agentevals"
    assert profile.train_backend == "mock"


def test_live_mode_keeps_urls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOOP_SERVICE_MODE", "live")
    monkeypatch.setenv("AGENTEVALS_BASE_URL", "https://agentevals.example")
    monkeypatch.setenv("TRAINER_BASE_URL", "https://aerl.example")
    profile = configure_demo_env()
    assert profile.mode == "live"
    assert profile.eval_backend == "agentevals"
    assert profile.train_backend == "aerl"
    assert profile.service_urls["AGENTEVALS_BASE_URL"] == "https://agentevals.example"


def test_mock_http_promotes_aerl_train_backend(monkeypatch: pytest.MonkeyPatch):
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    profile = configure_demo_env(with_http=True)
    assert profile.mode == "mock-http"
    assert profile.train_backend == "aerl"
    assert "TRAINER_BASE_URL" in profile.service_urls
    assert "MOCK_AERL_URL" in profile.service_urls


def test_loop_config_mock_http_does_not_infer_backends(monkeypatch: pytest.MonkeyPatch):
    """mock-http mode uses HTTP transport but keeps mock backends unless explicitly set."""
    from loop_config import LoopConfig

    monkeypatch.setenv("LOOP_SERVICE_MODE", "mock-http")
    monkeypatch.setenv("MOCK_AERL_URL", "http://127.0.0.1:38004")
    monkeypatch.setenv("ORCHESTRATOR_TRAIN_BACKEND", "mock")
    config = LoopConfig.from_env()
    # mock-http does NOT auto-infer backends — only live mode does
    assert config.train_backend == "mock"
    assert config.aerl_url == "http://127.0.0.1:38004"


def test_live_mode_infers_cli_train_when_supabase_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOOP_SERVICE_MODE", "live")
    monkeypatch.delenv("TRAINER_BASE_URL", raising=False)
    monkeypatch.delenv("MOCK_AERL_URL", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "http://db.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    monkeypatch.setenv("BRIDGE_USER_ID", "00000000-0000-0000-0000-000000000001")
    profile = configure_demo_env()
    assert profile.train_backend == "cli"


def test_build_loop_client_cli_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "mock")
    monkeypatch.setenv("ORCHESTRATOR_TRAIN_BACKEND", "cli")
    monkeypatch.setenv("ORCHESTRATOR_TRANSPORT", "module")
    monkeypatch.setenv("SUPABASE_URL", "http://db.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    monkeypatch.setenv("BRIDGE_USER_ID", "00000000-0000-0000-0000-000000000001")

    from services.adapters.cli_train_adapter import CLITrainAdapter
    from services.adapters.composite_client import CompositeClient

    client = build_loop_client(tmp_path)
    assert isinstance(client, CompositeClient)
    assert isinstance(client._train, CLITrainAdapter)
