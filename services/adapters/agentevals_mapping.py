# SPDX-License-Identifier: MIT
"""Shared AgentEvals RunDetail / agent_config mapping helpers."""

from __future__ import annotations

import os
from typing import Any

_SCORE_KEYS = ("overall", "pass_rate", "overall_pass_rate", "score")

_RESERVED_METRIC_KEYS = frozenset(
    {
        "overall",
        "pass_rate",
        "overall_pass_rate",
        "score",
        "safety",
        "cost_usd",
        "latency_p95_ms",
        "suite_id",
        "num_trials",
        "started_at",
        "completed_at",
        "artifact_paths",
        "suite_metrics",
        "statistics_summary",
        "task_pass_rates",
        "error",
    }
)


def score_from_run_metrics(metrics: dict[str, Any]) -> float:
    """Map AgentEvals metrics blob to a single gate score."""
    for key in _SCORE_KEYS:
        val = metrics.get(key)
        if isinstance(val, (int, float)):
            return float(val)

    suite_metrics = metrics.get("suite_metrics")
    if isinstance(suite_metrics, dict):
        val = suite_metrics.get("average_overall_score")
        if isinstance(val, (int, float)):
            return float(val)

    stats = metrics.get("statistics_summary")
    if isinstance(stats, dict):
        val = stats.get("average_overall_score")
        if isinstance(val, (int, float)):
            return float(val)

    task_rates = metrics.get("task_pass_rates")
    if isinstance(task_rates, dict) and task_rates:
        nums = [float(v) for v in task_rates.values() if isinstance(v, (int, float))]
        if nums:
            return sum(nums) / len(nums)

    nums = [float(v) for v in metrics.values() if isinstance(v, (int, float))]
    return sum(nums) / len(nums) if nums else 0.0


def task_scores_from_run_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    task_rates = metrics.get("task_pass_rates")
    if isinstance(task_rates, dict):
        for key, val in task_rates.items():
            if isinstance(val, (int, float)):
                scores[str(key)] = float(val)
    for key, val in metrics.items():
        if key not in _RESERVED_METRIC_KEYS and isinstance(val, (int, float)):
            scores[key] = float(val)
    return scores


def trials_from_run_detail(run_detail: dict[str, Any], metrics: dict[str, Any]) -> int:
    for source in (run_detail, metrics):
        val = source.get("num_trials")
        if val is not None:
            parsed = int(val)
            if parsed > 0:
                return parsed
    task_rates = metrics.get("task_pass_rates")
    if isinstance(task_rates, dict) and task_rates:
        return len(task_rates)
    suite_metrics = metrics.get("suite_metrics")
    if isinstance(suite_metrics, dict):
        total = suite_metrics.get("total_tasks")
        if isinstance(total, int) and total > 0:
            return total
    return 1


def resolve_model_name(*, components: dict[str, Any] | None = None, fallback: str | None = None) -> str | None:
    if components:
        for key in ("model_id", "model", "model_name"):
            val = components.get(key)
            if val:
                return str(val)
    env_model = os.environ.get("AGENTEVALS_MODEL_NAME", "").strip()
    if env_model:
        return env_model
    return fallback


def build_agent_config(
    *,
    agent_id: str,
    version_id: str,
    baseline_version_id: str,
    components: dict[str, Any] | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Build RunCreate.agent_config for mock and live AgentEvals."""
    cfg: dict[str, Any] = {
        "agent_id": agent_id,
        "version_id": version_id,
        "baseline_version_id": baseline_version_id,
    }
    resolved = model_name or resolve_model_name(components=components)
    if resolved:
        cfg["model"] = {"name": resolved}
    return cfg
