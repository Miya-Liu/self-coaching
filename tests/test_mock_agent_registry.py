# SPDX-License-Identifier: MIT
"""Unit tests for mock agent registry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mock-services"))

from mock_agent_registry import AgentRegistry, RegistryError


@pytest.fixture
def registry(tmp_path: Path) -> AgentRegistry:
    return AgentRegistry(tmp_path / "registry-data")


def test_ensure_agent_bootstrap(registry: AgentRegistry):
    agent = registry.ensure_agent("agent-a", model_id="model-x")
    assert agent["active_version_id"] == "ver-0001"
    assert agent["version"]["components"]["model_id"] == "model-x"


def test_create_and_activate_version(registry: AgentRegistry):
    registry.ensure_agent("agent-b")
    child = registry.create_version(
        "agent-b",
        components={"skill_bundle_version": "skills-v2"},
        source="self-learning",
    )
    assert child["parent_version_id"] == "ver-0001"
    assert child["components"]["skill_bundle_version"] == "skills-v2"
    active = registry.activate("agent-b", child["version_id"])
    assert active["active"] is True
    got = registry.get_agent("agent-b")
    assert got["active_version_id"] == child["version_id"]


def test_score_multiplier_bad(registry: AgentRegistry):
    registry.ensure_agent("agent-c")
    bad = registry.create_version("agent-c", components={"model_id": "model-bad-regress"})
    assert registry.score_multiplier("agent-c", bad["version_id"]) < 0.6


def test_missing_version(registry: AgentRegistry):
    registry.ensure_agent("agent-d")
    with pytest.raises(RegistryError):
        registry.get_version("agent-d", "ver-missing")
