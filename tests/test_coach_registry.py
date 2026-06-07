# SPDX-License-Identifier: MIT
"""Unit tests for coach mode supervision registry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modes.coach.registry import RegistryError, load_registry, parse_registry


def test_parse_registry_minimal():
    agents = parse_registry(
        {
            "agents": [
                {
                    "id": "a1",
                    "coaching_root": "/data/a1",
                    "eval": {"suite_id_canary": "canary-suite"},
                }
            ]
        }
    )
    assert len(agents) == 1
    assert agents[0].id == "a1"
    assert agents[0].coaching_root == Path("/data/a1")
    assert agents[0].eval is not None
    assert agents[0].eval.suite_id_canary == "canary-suite"


def test_parse_registry_duplicate_id():
    with pytest.raises(RegistryError, match="duplicate agent id"):
        parse_registry(
            {
                "agents": [
                    {"id": "same", "coaching_root": "/a"},
                    {"id": "same", "coaching_root": "/b"},
                ]
            }
        )


def test_load_registry_json_example():
    path = REPO_ROOT / "modes" / "coach" / "agents.example.json"
    agents = load_registry(path)
    assert len(agents) == 1
    assert agents[0].id == "example-agent"
    assert agents[0].improvement is not None
    assert agents[0].improvement.min_cases_for_model_path == 100
