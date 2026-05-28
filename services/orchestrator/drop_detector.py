# SPDX-License-Identifier: MIT
"""Drop detection on EvalMetrics (pipeline.md trigger policy)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .eval_metrics import EvalMetrics


@dataclass
class DropCheckResult:
    triggered: bool
    reasons: list[str]
    metrics: EvalMetrics | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "reasons": self.reasons,
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }


def load_thresholds(path: Path) -> dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: float(v) for k, v in data.items()}


def check_drop(metrics: EvalMetrics, thresholds: dict[str, float]) -> DropCheckResult:
    reasons: list[str] = []
    if metrics.score < thresholds["min_score"]:
        reasons.append(f"score {metrics.score:.4f} < min_score {thresholds['min_score']}")
    drop = metrics.baseline_score - metrics.score
    if drop >= thresholds["max_drop"]:
        reasons.append(f"drop {drop:.4f} >= max_drop {thresholds['max_drop']}")
    if metrics.safety_pass_rate < thresholds["min_safety_pass_rate"]:
        reasons.append(
            f"safety_pass_rate {metrics.safety_pass_rate:.4f} "
            f"< min {thresholds['min_safety_pass_rate']}"
        )
    if metrics.latency_p95_ms > thresholds["max_latency_p95_ms"]:
        reasons.append(
            f"latency_p95_ms {metrics.latency_p95_ms:.1f} > max {thresholds['max_latency_p95_ms']}"
        )
    if metrics.cost_per_task > thresholds["max_cost_per_task"]:
        reasons.append(
            f"cost_per_task {metrics.cost_per_task:.4f} > max {thresholds['max_cost_per_task']}"
        )
    return DropCheckResult(triggered=bool(reasons), reasons=reasons, metrics=metrics)


def check_promotion(
    production: EvalMetrics,
    candidate: EvalMetrics,
    thresholds: dict[str, float],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    min_gain = thresholds["min_candidate_improvement"]
    if candidate.score < production.score + min_gain:
        reasons.append(
            f"candidate score {candidate.score:.4f} < production {production.score:.4f} + {min_gain}"
        )
    if candidate.safety_pass_rate < thresholds["min_safety_pass_rate"]:
        reasons.append("candidate safety below threshold")
    if candidate.latency_p95_ms > thresholds["max_latency_p95_ms"]:
        reasons.append("candidate latency above threshold")
    if candidate.cost_per_task > thresholds["max_cost_per_task"]:
        reasons.append("candidate cost above threshold")
    return (not reasons, reasons)
