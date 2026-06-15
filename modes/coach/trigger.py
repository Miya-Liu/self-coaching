# SPDX-License-Identifier: MIT
"""Handle inbound coach posts — agent plan → evolution tick."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from agent_bridge import ClockPlan, CoachAgentBridge, MockCoachAgentBridge
from post import CoachPost, persist_post

try:
    from clock import load_scenario, run_tick
    from registry import SupervisedAgent, load_registry
except ImportError:
    from modes.coach.clock import load_scenario, run_tick  # type: ignore[no-redef]
    from modes.coach.registry import SupervisedAgent, load_registry  # type: ignore[no-redef]

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_SCENARIO = REPO_ROOT / "scenarios" / "clock_loop.json"


def resolve_coaching_root(agent: SupervisedAgent) -> Path:
    root = Path(agent.coaching_root)
    if not root.is_absolute():
        root = (REPO_ROOT / root).resolve()
    return root


def scenario_path_for_agent(agent: SupervisedAgent) -> Path:
    if agent.coach_clock is not None and agent.coach_clock.scenario:
        candidate = Path(agent.coach_clock.scenario)
        if candidate.is_file():
            return candidate.resolve()
        rooted = REPO_ROOT / candidate
        if rooted.is_file():
            return rooted.resolve()
    return DEFAULT_SCENARIO.resolve()


def merge_scenario(base: dict[str, Any], overrides: dict[str, Any], agent_id: str) -> dict[str, Any]:
    merged = deepcopy(base)
    merged["agent_id"] = agent_id
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def execute_plan(
    agent: SupervisedAgent,
    plan: ClockPlan,
    *,
    client: Any | None = None,
) -> dict[str, Any] | None:
    if plan.action == "hold":
        return None
    if plan.action != "full_tick":
        # Partial routes (learn/play/tune) map to full_tick in mock spine until M5 adapters wire stages.
        pass
    root = resolve_coaching_root(agent)
    scenario = merge_scenario(
        load_scenario(scenario_path_for_agent(agent)),
        plan.scenario_overrides,
        agent.id,
    )
    os.environ["LOOP_AGENT_ID"] = agent.id
    os.environ["AGENT_ID"] = agent.id
    return run_tick(root, scenario, client=client)


def handle_coach_post(
    agent: SupervisedAgent,
    post: CoachPost,
    bridge: CoachAgentBridge | None = None,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    """Full pipeline: persist post → agent sets up clock → execute → agent response."""
    root = resolve_coaching_root(agent)
    root.mkdir(parents=True, exist_ok=True)
    persist_post(root, post)

    coach_bridge = bridge or MockCoachAgentBridge(audit_dir=root / ".self-coaching" / "coach" / "audit")
    plan = coach_bridge.setup_clock(agent, post)
    tick_result = execute_plan(agent, plan, client=client)

    response = coach_bridge.format_response(agent, post, plan, tick_result)
    out_dir = root / ".self-coaching" / "coach"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "last_response.json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return response


def find_agent(agents: list[SupervisedAgent], agent_id: str) -> SupervisedAgent:
    for agent in agents:
        if agent.id == agent_id:
            return agent
    raise KeyError(f"unknown agent_id: {agent_id!r}")


def handle_post_body(
    body: dict[str, Any],
    registry_path: str | Path,
    bridge: CoachAgentBridge | None = None,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    post = CoachPost.from_dict(body)
    agents = load_registry(registry_path)
    agent = find_agent(agents, post.agent_id)
    if agent.coach_clock is not None and not agent.coach_clock.enabled:
        return {
            "agent_id": agent.id,
            "post_id": post.post_id,
            "plan": {"action": "hold", "reason": "coach_clock disabled for agent"},
            "tick": None,
            "message": "coach clock disabled",
        }
    return handle_coach_post(agent, post, bridge, client=client)
