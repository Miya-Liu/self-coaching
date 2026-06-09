# SPDX-License-Identifier: MIT
"""Online rubric scorer R_online per self-coaching-demo-pipeline-plan §3.2.1."""

from __future__ import annotations

from typing import Any, TypedDict


class RubricBreakdown(TypedDict):
    tools_ok: bool
    answer_ok: bool
    missing_tools: list[str]
    failed_checks: list[dict[str, Any]]


class RubricResult(TypedDict):
    score: float
    breakdown: RubricBreakdown


def _final_answer(xi: dict[str, Any]) -> str:
    if "final_answer" in xi and xi["final_answer"] is not None:
        return str(xi["final_answer"])
    messages = xi.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            return str(msg.get("content") or "")
    return ""


def _tool_trace(xi: dict[str, Any]) -> list[str]:
    raw = xi.get("tool_trace_summary") or []
    return [str(entry) for entry in raw]


def _expected_tools(tau: dict[str, Any]) -> list[str]:
    raw = tau.get("expected_tool_calls") or []
    return [str(token) for token in raw]


def _answer_checks(tau: dict[str, Any]) -> list[dict[str, Any]]:
    raw = tau.get("answer_checks") or []
    return [check for check in raw if isinstance(check, dict)]


def _tool_token_present(token: str, trace: list[str]) -> bool:
    needle = token.casefold()
    return any(needle in entry.casefold() for entry in trace)


def _check_answer(check: dict[str, Any], answer: str) -> bool:
    check_type = str(check.get("type") or "contains")
    if check_type != "contains":
        return False
    value = str(check.get("value") or "")
    return value.casefold() in answer.casefold()


def score_trajectory(xi: dict[str, Any], tau: dict[str, Any]) -> RubricResult:
    """Score trajectory xi against task fixture tau using the §3.2.1 rubric."""
    expected = _expected_tools(tau)
    trace = _tool_trace(xi)
    answer = _final_answer(xi)
    checks = _answer_checks(tau)

    missing_tools = [token for token in expected if not _tool_token_present(token, trace)]
    tools_ok = not missing_tools

    failed_checks = [check for check in checks if not _check_answer(check, answer)]
    answer_ok = not failed_checks

    if tools_ok and answer_ok:
        score = 1.0
    elif tools_ok:
        score = 0.5
    else:
        score = 0.0

    breakdown: RubricBreakdown = {
        "tools_ok": tools_ok,
        "answer_ok": answer_ok,
        "missing_tools": missing_tools,
        "failed_checks": failed_checks,
    }
    return {"score": score, "breakdown": breakdown}
