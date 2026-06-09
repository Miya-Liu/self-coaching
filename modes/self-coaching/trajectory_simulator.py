# SPDX-License-Identifier: MIT
"""Deterministic trajectory simulator for mock task-stream fixtures."""

from __future__ import annotations

from typing import Any


def _profile(tau: dict[str, Any]) -> dict[str, Any]:
    profile = tau.get("agent_profile")
    return profile if isinstance(profile, dict) else {}


def _user_request(tau: dict[str, Any]) -> str:
    for key in ("user_request", "prompt", "task_text"):
        value = tau.get(key)
        if value:
            return str(value)
    return f"Complete task {tau.get('task_id', 'unknown')}"


def _ideal_answer(tau: dict[str, Any]) -> str:
    profile = _profile(tau)
    if profile.get("answer"):
        return str(profile["answer"])
    fragments: list[str] = []
    for check in tau.get("answer_checks") or []:
        if isinstance(check, dict) and check.get("type") == "contains":
            fragments.append(str(check.get("value") or ""))
    return ". ".join(fragment for fragment in fragments if fragment)


def _tool_entries(expected_tools: list[str], *, outcome: str) -> list[str]:
    if not expected_tools:
        return []
    if outcome == "missing_tool":
        return [f"invoke {token}" for token in expected_tools[:-1]]
    if outcome == "wrong_order":
        shuffled = list(reversed(expected_tools))
        return [f"invoke {token}" for token in shuffled]
    return [f"invoke {token}" for token in expected_tools]


def simulate_trajectory(tau: dict[str, Any]) -> dict[str, Any]:
    """Produce deterministic xi from task fixture tau and agent_profile hints."""
    profile = _profile(tau)
    outcome = str(profile.get("outcome") or "perfect")
    expected_tools = [str(token) for token in (tau.get("expected_tool_calls") or [])]
    tool_trace_summary = _tool_entries(expected_tools, outcome=outcome)

    if outcome == "hallucinated_answer":
        final_answer = str(profile.get("answer") or "Task completed successfully without verification.")
    elif outcome in {"wrong_order", "tools_only"}:
        final_answer = str(profile.get("answer") or "Tools ran but evidence was not reported.")
    else:
        final_answer = _ideal_answer(tau)

    user_request = _user_request(tau)
    messages = [
        {"role": "user", "content": user_request},
        {"role": "assistant", "content": final_answer},
    ]
    return {
        "task_id": tau.get("task_id"),
        "messages": messages,
        "tool_trace_summary": tool_trace_summary,
        "final_answer": final_answer,
        "capability": tau.get("capability") or ["tool_use"],
    }
