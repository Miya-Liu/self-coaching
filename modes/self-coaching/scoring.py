# SPDX-License-Identifier: MIT
"""Task scoring and routing logic for the self-coaching loop."""

from __future__ import annotations

from typing import Any

try:
    from ._paths import _SC_ROOT  # noqa: F401 — triggers sys.path setup
    from .loop_config import DEFAULT_TAU_FAIL, TaskScore
    from .loop_store import LoopStore, SupportEntry
    from .trajectory_simulator import simulate_trajectory
except ImportError:
    from _paths import _SC_ROOT  # noqa: F401
    from loop_config import DEFAULT_TAU_FAIL, TaskScore
    from loop_store import LoopStore, SupportEntry
    from trajectory_simulator import simulate_trajectory

from trajectory_scorer import RubricResult, score_trajectory  # noqa: E402


def route_score(score: float, *, tau_fail: float | None = None) -> str:
    threshold = DEFAULT_TAU_FAIL if tau_fail is None else tau_fail
    return "support" if score < threshold else "buffer"


def failure_event_text(task_id: str, score: float, rubric: RubricResult) -> str:
    breakdown = rubric["breakdown"]
    if not breakdown["tools_ok"]:
        missing = ", ".join(breakdown["missing_tools"]) or "expected tools"
        return f"Task {task_id} missing tools: {missing} (score={score:.2f})"
    return f"Task {task_id} answer incomplete after tool use (score={score:.2f})"


def process_task(
    tau: dict[str, Any],
    *,
    loop_store: LoopStore,
    generation: int,
    version_id: str,
    tau_fail: float | None = None,
    trajectory_fn: Any | None = None,
    override_score: float | None = None,
) -> tuple[TaskScore, dict[str, Any], SupportEntry | None]:
    producer = trajectory_fn if trajectory_fn is not None else simulate_trajectory
    xi = producer(tau)
    rubric = score_trajectory(xi, tau)

    # Use override_score from external evaluator (e.g. AgentEvals trace eval) if provided
    final_score = override_score if override_score is not None else rubric["score"]
    rubric["score"] = final_score

    task_id = str(tau.get("task_id") or "")
    trajectory_id, trajectory_ref = loop_store.save_trajectory(task_id, xi, rubric_result=rubric)
    routed_to = route_score(final_score, tau_fail=tau_fail)

    support_entry: SupportEntry | None = None
    if routed_to == "support":
        event_text = failure_event_text(task_id, rubric["score"], rubric)
        support_entry = SupportEntry(
            task_id=task_id,
            trajectory_id=trajectory_id,
            trajectory_ref=trajectory_ref,
            score=rubric["score"],
            event_text=event_text,
        )
        loop_store.append_support(
            task_id=task_id,
            generation=generation,
            version_id=version_id,
            trajectory_id=trajectory_id,
            trajectory_ref=trajectory_ref,
            score=rubric["score"],
            event_text=event_text,
        )
    else:
        loop_store.append_buffer(
            task_id=task_id,
            generation=generation,
            version_id=version_id,
            score=rubric["score"],
            trajectory_ref=trajectory_ref,
        )

    result = TaskScore(
        task_id=task_id,
        score=rubric["score"],
        rubric=rubric,
        routed_to=routed_to,
        trajectory_ref=trajectory_ref,
    )
    return result, xi, support_entry
