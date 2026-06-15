# SPDX-License-Identifier: MIT
"""Bridge to the supervised external agent — setup coach clock and format responses."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from post import CoachPost, ClockAction

try:
    from registry import SupervisedAgent
except ImportError:
    from modes.coach.registry import SupervisedAgent  # type: ignore[no-redef]


@dataclass(frozen=True)
class ClockPlan:
    """Agent decision after reviewing an inbound post."""

    action: ClockAction
    reason: str
    scenario_overrides: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "scenario_overrides": self.scenario_overrides,
        }


_SETUP_PROMPT = """\
You are the coach for supervised agent {agent_id}.

An inbound post arrived on the coach clock service. Review it and decide how to \
run the self-evolution loop (same gates as self-coaching: hold, self-learning, \
self-play, self-tuning, or a full autonomous tick).

Post:
{post_json}

Reply with JSON only:
{{"action": "hold"|"learn"|"play"|"tune"|"full_tick", "reason": "...", "scenario_overrides": {{}}}}
"""


class CoachAgentBridge(Protocol):
    def setup_clock(self, agent: SupervisedAgent, post: CoachPost) -> ClockPlan: ...

    def format_response(
        self,
        agent: SupervisedAgent,
        post: CoachPost,
        plan: ClockPlan,
        tick_result: dict[str, Any] | None,
    ) -> dict[str, Any]: ...


_VALID_ACTIONS: frozenset[ClockAction] = frozenset({"hold", "learn", "play", "tune", "full_tick"})


def _normalize_action(raw: Any) -> ClockAction:
    if isinstance(raw, str) and raw in _VALID_ACTIONS:
        return raw  # type: ignore[return-value]
    return "full_tick"


class MockCoachAgentBridge:
    """Deterministic bridge for CI — reads optional payload.action / payload.route."""

    def __init__(self, *, audit_dir: Path | None = None):
        self.audit_dir = audit_dir

    def setup_clock(self, agent: SupervisedAgent, post: CoachPost) -> ClockPlan:
        prompt = _SETUP_PROMPT.format(agent_id=agent.id, post_json=json.dumps(post.to_dict(), indent=2))
        if self.audit_dir is not None:
            audit = self.audit_dir / agent.id
            audit.mkdir(parents=True, exist_ok=True)
            (audit / "last_setup_prompt.txt").write_text(prompt, encoding="utf-8")

        payload = post.payload
        action = _normalize_action(payload.get("action") or payload.get("route"))
        reason = str(payload.get("reason") or f"mock bridge: {post.event} → {action}")
        overrides = payload.get("scenario_overrides")
        if not isinstance(overrides, dict):
            overrides = {}
        return ClockPlan(action=action, reason=reason, scenario_overrides=overrides)

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
                f"Coach clock for {agent.id}: {plan.action} — {plan.reason}"
                + (f"; promoted={tick_result.get('t_path_promoted')}" if tick_result else "")
            ),
        }
