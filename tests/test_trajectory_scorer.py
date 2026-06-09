# SPDX-License-Identifier: MIT
"""Golden triple tests for §3.2.1 trajectory rubric."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
sys.path.insert(0, str(SC_ROOT / "self-learning"))

from trajectory_scorer import score_trajectory  # noqa: E402


PERFECT_TAU = {
    "task_id": "golden-perfect",
    "expected_tool_calls": ["write config.yaml", "validate yaml", "read back artifact"],
    "answer_checks": [
        {"type": "contains", "value": "config.yaml"},
        {"type": "contains", "value": "validated"},
    ],
}

PERFECT_XI = {
    "messages": [
        {"role": "user", "content": "Create config.yaml and verify it exists."},
        {
            "role": "assistant",
            "content": "Wrote config.yaml and validated the file on disk.",
        },
    ],
    "tool_trace_summary": [
        "invoke write config.yaml",
        "invoke validate yaml",
        "invoke read back artifact",
    ],
}

MISSING_TOOL_XI = {
    "messages": [
        {"role": "user", "content": "Create config.yaml and verify it exists."},
        {"role": "assistant", "content": "config.yaml validated"},
    ],
    "tool_trace_summary": [
        "invoke write config.yaml",
        "invoke validate yaml",
    ],
}

WRONG_ORDER_XI = {
    "messages": [
        {"role": "user", "content": "Create config.yaml and verify it exists."},
        {"role": "assistant", "content": "Finished running tools."},
    ],
    "tool_trace_summary": [
        "invoke read back artifact",
        "invoke validate yaml",
        "invoke write config.yaml",
    ],
}

HALLUCINATED_XI = {
    "messages": [
        {"role": "user", "content": "Create config.yaml and verify it exists."},
        {"role": "assistant", "content": "Task completed successfully without verification."},
    ],
    "tool_trace_summary": [
        "invoke write config.yaml",
        "invoke validate yaml",
        "invoke read back artifact",
    ],
}


@pytest.mark.parametrize(
    ("xi", "tau", "expected_score"),
    [
        (PERFECT_XI, PERFECT_TAU, 1.0),
        (MISSING_TOOL_XI, PERFECT_TAU, 0.0),
        (WRONG_ORDER_XI, PERFECT_TAU, 0.5),
        (HALLUCINATED_XI, PERFECT_TAU, 0.5),
    ],
    ids=["perfect", "missing_tool", "wrong_order", "hallucinated_answer"],
)
def test_score_trajectory_golden_triples(xi, tau, expected_score):
    result = score_trajectory(xi, tau)
    assert result["score"] == pytest.approx(expected_score, abs=1e-3)
    assert 0.0 <= result["score"] <= 1.0
    assert "breakdown" in result
    assert "tools_ok" in result["breakdown"]
    assert "answer_ok" in result["breakdown"]


def test_score_trajectory_uses_last_assistant_message():
    xi = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "ignored"},
            {"role": "assistant", "content": "config.yaml validated"},
        ],
        "tool_trace_summary": [
            "invoke write config.yaml",
            "invoke validate yaml",
            "invoke read back artifact",
        ],
    }
    result = score_trajectory(xi, PERFECT_TAU)
    assert result["score"] == pytest.approx(1.0, abs=1e-3)
    assert result["breakdown"]["answer_ok"] is True
