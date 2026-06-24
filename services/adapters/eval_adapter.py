# SPDX-License-Identifier: MIT
"""AgentEvals eval adapter: mock-compatible evaluate() / eval_report() for the orchestrator."""

from __future__ import annotations

import os
from typing import Any

from .agentevals_client import AgentEvalsClient, AgentEvalsError
from .agentevals_mapping import build_agent_config, score_from_run_metrics, task_scores_from_run_metrics

_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "canceled"})


def run_detail_to_mock_report(detail: dict[str, Any], *, candidate: str, baseline: str) -> dict[str, Any]:
    """Map AgentEvals RunDetail into mock coaching eval report shape."""
    metrics = detail.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    from .agentevals_mapping import trials_from_run_detail

    score = score_from_run_metrics(metrics)
    status = "passed" if score >= 0.8 and str(detail.get("status", "")).lower() == "succeeded" else "failed"
    scores: dict[str, float] = {"overall": score, "safety": float(metrics.get("safety", 1.0))}
    scores.update(task_scores_from_run_metrics(metrics))
    trials = trials_from_run_detail(detail, metrics)
    cost_usd = float(metrics.get("cost_usd", 0.0))
    p95_ms = float(metrics.get("latency_p95_ms", 0.0))
    run_id = str(detail.get("id", detail.get("run_id", "eval-unknown")))
    return {
        "run_id": run_id,
        "candidate": candidate,
        "baseline": baseline,
        "status": status,
        "scores": scores,
        "cost": {"usd": cost_usd, "usd_per_task": cost_usd / trials},
        "latency": {"p95_s": p95_ms / 1000.0},
        "recommendation": "promote" if status == "passed" else "do_not_promote",
        "run_detail": detail,
    }


class AgentEvalsEvalAdapter:
    """evaluate / eval_report backed by AgentEvals; other methods are not provided here."""

    def __init__(self, client: AgentEvalsClient | None = None):
        self._client = client or AgentEvalsClient()
        self._cache: dict[str, dict[str, Any]] = {}

    def _suite_id(self, *, holdout: bool = False) -> str:
        if holdout:
            suite = os.environ.get("AGENTEVALS_SUITE_ID_HOLDOUT") or os.environ.get("AGENTEVALS_SUITE_ID")
        else:
            suite = os.environ.get("AGENTEVALS_SUITE_ID")
        if not suite:
            raise AgentEvalsError(
                "AGENTEVALS_SUITE_ID is required when ORCHESTRATOR_EVAL_BACKEND=agentevals"
            )
        return suite

    def _agent_config(self, *, candidate: str, baseline: str) -> dict[str, Any]:
        agent_id = os.environ.get("AGENT_ID") or os.environ.get("LOOP_AGENT_ID") or "demo-agent"
        return build_agent_config(
            agent_id=agent_id,
            version_id=candidate,
            baseline_version_id=baseline,
        )

    def evaluate(
        self,
        *,
        candidate: str = "mock-candidate-v1",
        baseline: str = "mock-baseline-v0",
        holdout: bool | None = None,
    ) -> dict[str, Any]:
        if holdout is None:
            holdout = os.environ.get("ORCHESTRATOR_EVAL_SPLIT") == "holdout"
        suite_id = self._suite_id(holdout=holdout)
        created = self._client.create_run(
            suite_id=suite_id,
            agent_config=self._agent_config(candidate=candidate, baseline=baseline),
            num_trials=_optional_int(os.environ.get("AGENTEVALS_NUM_TRIALS")),
        )
        run_id = str(created.get("id") or created.get("run_id") or "")
        if not run_id:
            raise AgentEvalsError("create_run response missing id", body=created)
        from .step_log import step_log

        step_log("agentevals", f"holdout eval started run_id={run_id} suite={suite_id}")
        detail = self._client.wait_for_run(run_id)
        report = run_detail_to_mock_report(detail, candidate=candidate, baseline=baseline)
        self._cache[run_id] = report
        return {
            "status": report["status"],
            "run_id": run_id,
            "report": run_id,
            "recommendation": report["recommendation"],
            "_eval_backend": "agentevals",
        }

    def eval_report(self, run_id: str) -> dict[str, Any]:
        if run_id in self._cache:
            return self._cache[run_id]
        detail = self._client.get_run(run_id)
        status = str(detail.get("status", "")).lower()
        if status not in _TERMINAL:
            detail = self._client.wait_for_run(run_id)
        ac = detail.get("agent_config") or {}
        candidate = str(ac.get("version_id", "unknown"))
        baseline = str(ac.get("baseline_version_id", "unknown"))
        report = run_detail_to_mock_report(detail, candidate=candidate, baseline=baseline)
        self._cache[run_id] = report
        return report


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)

