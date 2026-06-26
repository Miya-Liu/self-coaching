# SPDX-License-Identifier: MIT
"""Trace-eval coach bridge — observe player activity, evaluate via AgentEvals, decide action.

This bridge extends the coach's decision-making with two evaluation modes:

  **Mode 1: Trace Evaluation (reactive)**
  When user sessions complete, the Coach calls POST /api/trace-evals to grade
  those specific sessions. The score determines if the session is good (→ buffer B)
  or bad (→ support set Σ).

  **Mode 2: Suite/Benchmark Evaluation (proactive)**
  During the player's idle time (no active sessions), the Coach runs an existing
  benchmark suite (POST /api/runs) against the player agent to assess overall
  capability. If the suite score drops below threshold, evolution is triggered.

Decision flow:
  - Trace eval score >= tau_fail → buffer (good session)
  - Trace eval score < tau_fail → sigma (bad session, learn from it)
  - Suite eval overall >= threshold → hold (agent performing well)
  - Suite eval overall < threshold → trigger e-path or full_tick

Thresholds (env-configurable):
  - TRACE_EVAL_SCORE_HIGH (default 0.85): above → hold (agent is performing well)
  - TRACE_EVAL_SCORE_LOW (default 0.60): below → full_tick (needs aggressive evolution)
  - Between high/low: route to e-path (learn) or t-path (tune) depending on trend.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from coach.agent_bridge import ClockPlan, _VALID_ACTIONS
from coach.post import CoachPost
from coach.registry import SupervisedAgent

LOG = logging.getLogger("coach.trace_eval_bridge")

# Score thresholds
_SCORE_HIGH = float(os.environ.get("TRACE_EVAL_SCORE_HIGH", "0.85"))
_SCORE_LOW = float(os.environ.get("TRACE_EVAL_SCORE_LOW", "0.60"))
# Time window for sampling traces (hours lookback)
_WINDOW_HOURS = int(os.environ.get("TRACE_EVAL_WINDOW_HOURS", "24"))
# Number of sessions to sample
_SAMPLE_COUNT = int(os.environ.get("TRACE_EVAL_SAMPLE_COUNT", "10"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class TraceEvalCoachBridge:
    """CoachAgentBridge that uses AgentEvals trace evaluation to drive decisions.

    Flow:
      1. On player activity post → trigger POST /api/trace-evals with recent window.
      2. Poll until succeeded.
      3. Read average_score from metrics.
      4. Decide action based on score thresholds and dimensions.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        audit_dir: Path | None = None,
        score_high: float | None = None,
        score_low: float | None = None,
        window_hours: int | None = None,
        sample_count: int | None = None,
        poll_timeout_s: float | None = None,
    ):
        from services.adapters.agentevals_client import AgentEvalsClient

        self._client = AgentEvalsClient(
            base_url=base_url,
            poll_timeout_s=poll_timeout_s or 300.0,
        )
        self._audit_dir = audit_dir
        self._score_high = score_high if score_high is not None else _SCORE_HIGH
        self._score_low = score_low if score_low is not None else _SCORE_LOW
        self._window_hours = window_hours if window_hours is not None else _WINDOW_HOURS
        self._sample_count = sample_count if sample_count is not None else _SAMPLE_COUNT

    def setup_clock(self, agent: SupervisedAgent, post: CoachPost) -> ClockPlan:
        """Trigger trace eval on player activity, collect scores, decide action."""
        now = _utc_now()
        end_time = _iso(now)
        start_time = _iso(now - timedelta(hours=self._window_hours))

        trace_detail: dict[str, Any] | None = None
        error: str | None = None

        try:
            summary = self._client.create_trace_eval(
                agent_id=agent.id,
                start_time=start_time,
                end_time=end_time,
                sample_count=self._sample_count,
                agent_config={"agent_id": agent.id},
            )
            run_id = str(summary.get("id", ""))
            trace_detail = self._client.wait_for_trace_eval(run_id)
        except Exception as exc:
            error = str(exc)
            LOG.error("trace eval failed for %s: %s", agent.id, exc)

        plan = self._decide(agent, post, trace_detail, error)
        self._write_audit(agent, post, plan, trace_detail, error)
        return plan

    def _decide(
        self,
        agent: SupervisedAgent,
        post: CoachPost,
        trace_detail: dict[str, Any] | None,
        error: str | None,
    ) -> ClockPlan:
        """Map trace eval scores + loop state to a ClockPlan action.

        Decision matrix (aligned with spec's threshold-based evolution checker):
          - Trace eval error/no data → hold (fail-safe)
          - No sessions sampled → hold
          - score >= high threshold → play (self-questioning for continuous improvement)
          - score <= low threshold → full_tick (aggressive evolution)
          - Mid-range + Σ >= sigma_min → learn (e-path, enough failures accumulated)
          - Mid-range + B >= batch_size → tune (t-path, buffer ready for training)
          - Mid-range + many failing sessions → learn (e-path from trace evidence)
          - Mid-range otherwise → tune (t-path)
        """
        # On error or no data → hold (fail-safe)
        if error is not None or trace_detail is None:
            return ClockPlan(
                action="hold",
                reason=f"trace eval unavailable: {error or 'no detail'}",
            )

        metrics = trace_detail.get("metrics")
        if not metrics:
            return ClockPlan(action="hold", reason="trace eval returned no metrics")

        score = float(metrics.get("average_score", 0.0))
        sampled = int(metrics.get("sampled_count", 0))

        if sampled == 0:
            return ClockPlan(action="hold", reason="no sessions sampled in window")

        # Consult loop state via integration facade (best-effort)
        loop_status = self._get_loop_status(agent)

        # Decision logic based on score thresholds
        if score >= self._score_high:
            return ClockPlan(
                action="play",
                reason=f"score={score:.3f} >= {self._score_high} — self-questioning for continuous improvement",
            )

        if score <= self._score_low:
            return ClockPlan(
                action="full_tick",
                reason=f"score={score:.3f} <= {self._score_low} — full evolution needed",
            )

        # Mid-range: use loop state to pick best route
        if loop_status:
            sigma = loop_status.get("sigma_size", 0)
            buffer = loop_status.get("buffer_size", 0)
            # If sigma already has enough failures, learn from them
            if sigma >= 2:
                return ClockPlan(
                    action="learn",
                    reason=f"score={score:.3f} mid-range, Σ={sigma} >= threshold — e-path self-learning",
                )
            # If buffer is ready, tune
            if buffer >= 3:
                return ClockPlan(
                    action="tune",
                    reason=f"score={score:.3f} mid-range, B={buffer} >= batch — t-path self-tuning",
                )

        # Fallback: use per-session breakdown
        sessions = metrics.get("sessions") or []
        failing_sessions = [s for s in sessions if (s.get("score") or 0) < self._score_low]
        failing_ratio = len(failing_sessions) / max(1, len(sessions))

        if failing_ratio > 0.5:
            return ClockPlan(
                action="learn",
                reason=(
                    f"score={score:.3f}, {len(failing_sessions)}/{len(sessions)} sessions below threshold"
                    " — e-path self-learning"
                ),
            )

        return ClockPlan(
            action="tune",
            reason=f"score={score:.3f} in mid-range — t-path self-tuning",
        )

    def _get_loop_status(self, agent: SupervisedAgent) -> dict[str, Any] | None:
        """Best-effort read of loop state via integration facade."""
        try:
            from self_coaching.integration import get_loop_status
            return get_loop_status(agent.coaching_root)
        except Exception:
            LOG.debug("loop status unavailable for %s", agent.id, exc_info=True)
            return None

    def format_response(
        self,
        agent: SupervisedAgent,
        post: CoachPost,
        plan: ClockPlan,
        tick_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "agent_id": agent.id,
            "post_id": post.post_id,
            "plan": plan.to_dict(),
            "tick": tick_result,
            "message": (
                f"TraceEval coach for {agent.id}: {plan.action} — {plan.reason}"
                + (f"; promoted={tick_result.get('t_path_promoted')}" if tick_result else "")
            ),
        }

    def _write_audit(
        self,
        agent: SupervisedAgent,
        post: CoachPost,
        plan: ClockPlan,
        trace_detail: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        try:
            base = self._audit_dir or Path(agent.coaching_root) / ".self-coaching" / "coach" / "audit"
            audit = base / agent.id
            audit.mkdir(parents=True, exist_ok=True)
            record = {
                "post_id": post.post_id,
                "agent_id": agent.id,
                "plan": plan.to_dict(),
                "trace_eval": trace_detail,
                "error": error,
                "timestamp": _iso(_utc_now()),
            }
            (audit / "last_trace_eval_decision.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            LOG.debug("could not write trace eval audit for %s", agent.id, exc_info=True)


__all__ = ["TraceEvalCoachBridge"]
