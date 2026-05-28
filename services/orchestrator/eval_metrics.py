# SPDX-License-Identifier: MIT
"""EvalMetrics — shared JSON contract for auto-eval, drop detection, and promotion."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class EvalMetrics:
    run_id: str
    agent_id: str
    skill_bundle_version: str
    model_checkpoint_id: str
    score: float
    baseline_score: float
    cost_per_task: float
    latency_p95_ms: float
    safety_pass_rate: float
    task_scores: dict[str, float] = field(default_factory=dict)
    recorded_at: str = ""
    split: str = "canary"
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.recorded_at:
            self.recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalMetrics:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)


def normalize_from_mock_eval(
    *,
    agent_id: str,
    eval_summary: dict[str, Any],
    report: dict[str, Any],
    baseline_score: float | None = None,
    skill_bundle_version: str = "unknown",
    model_checkpoint_id: str | None = None,
    split: str = "canary",
) -> EvalMetrics:
    """Map mock (or compatible) eval summary + report into EvalMetrics."""
    scores = report.get("scores") or {}
    overall = float(scores.get("overall", 0.0))
    task_scores = {k: float(v) for k, v in scores.items() if k != "overall" and isinstance(v, (int, float))}
    cost = report.get("cost") or {}
    latency = report.get("latency") or {}
    candidate = report.get("candidate") or eval_summary.get("candidate", "mock-candidate-v1")
    baseline = report.get("baseline") or "mock-baseline-v0"
    if baseline_score is None:
        baseline_score = overall if candidate == baseline else overall + 0.05

    p95_s = float(latency.get("p95_s", 0.02))
    return EvalMetrics(
        run_id=str(eval_summary.get("run_id", report.get("run_id", "eval-unknown"))),
        agent_id=agent_id,
        skill_bundle_version=skill_bundle_version,
        model_checkpoint_id=model_checkpoint_id or str(candidate),
        score=overall,
        baseline_score=float(baseline_score),
        cost_per_task=float(cost.get("usd", 0.0)),
        latency_p95_ms=p95_s * 1000.0,
        safety_pass_rate=float(scores.get("safety", 1.0)),
        task_scores=task_scores,
        split=split,
        raw={"summary": eval_summary, "report": report},
    )


def metrics_store_path(coaching_root: Path) -> Path:
    return coaching_root / ".self-coaching" / "metrics" / "eval_metrics.jsonl"


def append_metrics(path: Path, metrics: EvalMetrics) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(metrics.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def load_metrics_lines(path: Path) -> list[EvalMetrics]:
    if not path.is_file():
        return []
    out: list[EvalMetrics] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(EvalMetrics.from_dict(json.loads(line)))
    return out


def latest_metrics(path: Path, agent_id: str | None = None) -> EvalMetrics | None:
    rows = load_metrics_lines(path)
    if agent_id:
        rows = [r for r in rows if r.agent_id == agent_id]
    return rows[-1] if rows else None


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
