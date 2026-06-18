# SPDX-License-Identifier: MIT
"""Handle inbound coach posts — agent plan → evolution tick."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from coach.agent_bridge import ClockPlan, CoachAgentBridge, MockCoachAgentBridge
from coach.post import CoachPost, persist_post
from coach.clock import load_scenario, run_tick
from coach.registry import SupervisedAgent, load_registry

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


def _subject_source_for(agent: SupervisedAgent) -> Any | None:
    """Build a live SubjectTaskSource from coach_clock.subject_chat_url, else None.

    When no subject_chat_url is configured the loop falls back to the fixture
    trajectory simulator (Phase 1 behavior).
    """
    import os

    cc = agent.coach_clock
    subject_url = getattr(cc, "subject_chat_url", None) if cc is not None else None
    if not subject_url:
        return None
    from self_coaching.subject_source import build_subject_source

    return build_subject_source(
        subject_url,
        api_key=os.environ.get("SUBJECT_AGENT_API_KEY"),
        model=os.environ.get("SUBJECT_AGENT_MODEL"),
        path=os.environ.get("SUBJECT_AGENT_PATH", "/chat/completions"),
        timeout_s=float(os.environ.get("SUBJECT_AGENT_TIMEOUT_S", "60")),
    )


def execute_plan(
    agent: SupervisedAgent,
    plan: ClockPlan,
    *,
    client: Any | None = None,
) -> dict[str, Any] | None:
    if plan.action == "hold":
        return None
    root = resolve_coaching_root(agent)
    scenario = merge_scenario(
        load_scenario(scenario_path_for_agent(agent)),
        plan.scenario_overrides,
        agent.id,
    )
    trajectory_fn = _subject_source_for(agent)
    if plan.action == "full_tick":
        return run_tick(root, scenario, client=client, trajectory_fn=trajectory_fn)
    # Partial routes: learn / play / tune target specific loop phases.
    return _execute_partial(root, scenario, plan.action, client=client, trajectory_fn=trajectory_fn)


def _execute_partial(
    root: Path,
    scenario: dict[str, Any],
    action: str,
    *,
    client: Any | None = None,
    trajectory_fn: Any | None = None,
) -> dict[str, Any]:
    """Run a single loop phase (learn / play / tune) instead of the full E→P→T tick.

    Uses the same env-scoped setup as clock.run_tick but only executes the
    targeted phase, returning a result dict with an "action" key.
    """
    import os

    from self_coaching.loop_config import LoopConfig
    from self_coaching.loop_driver import run_tasks
    from self_coaching.loop_env import build_loop_client, build_self_play_engine
    from self_coaching.loop_store import LoopStore
    from self_coaching.state import LoopStateStore
    from self_coaching.t_path import run_t_path
    from mock_agent_registry import AgentRegistry

    agent_id = str(scenario.get("agent_id") or os.environ.get("LOOP_AGENT_ID") or "demo-agent")
    loop_cfg = scenario.get("loop") or {}
    streams = scenario.get("task_streams") or {}

    e_path_stream = Path(
        streams.get("e_path") or "mock-services/fixtures/task_stream/clock_loop_e_v1.jsonl"
    )
    if not e_path_stream.is_absolute():
        e_path_stream = (REPO_ROOT / e_path_stream).resolve()

    config = LoopConfig.from_env()
    config.agent_id = agent_id
    config.sigma_min = int(loop_cfg.get("sigma_min", config.sigma_min))
    config.sigma_play = int(loop_cfg.get("sigma_play", config.sigma_play))
    config.batch_size = int(loop_cfg.get("beta", config.batch_size))
    config.tau_fail = float(loop_cfg.get("tau_fail", config.tau_fail))
    config.task_stream = e_path_stream

    # Scoped env set (same pattern as clock.run_tick)
    _prev_agent = os.environ.get("AGENT_ID")
    _prev_loop = os.environ.get("LOOP_AGENT_ID")
    os.environ["AGENT_ID"] = agent_id
    os.environ["LOOP_AGENT_ID"] = agent_id
    try:
        loop_client = client or build_loop_client(root, config=config)
        self_play_engine = build_self_play_engine(root, config=config)
        registry = AgentRegistry(root)
        registry.ensure_agent(agent_id)

        if action == "learn":
            # E-path only: score tasks → accumulate Σ → sparse self-play → learn
            run_tasks(
                root,
                config=config,
                task_stream_path=e_path_stream,
                enable_e_path=True,
                enable_t_path=False,
                client=loop_client,
                agent_id=agent_id,
                self_play_engine=self_play_engine,
                trajectory_fn=trajectory_fn,
            )
            state = LoopStateStore(root).load()
            return {
                "action": "learn",
                "generation": state.generation,
                "tasks_processed": state.tasks_processed,
            }

        if action == "play":
            # Self-play only: batch fill (C07) without training
            from self_coaching.t_path import fill_buffer_batch

            state = LoopStateStore(root).load()
            loop_store = LoopStore(root)
            current_buffer = len(loop_store.active_buffer_rows())
            n = max(0, config.batch_size - current_buffer)
            if n == 0:
                return {
                    "action": "play",
                    "batch_fill": {"status": "skipped", "count": 0, "reason": "buffer already full"},
                    "buffer_size": current_buffer,
                }
            batch_fill = fill_buffer_batch(
                coaching_root=root,
                loop_store=loop_store,
                registry=registry,
                agent_id=agent_id,
                generation=state.generation,
                n=n,
                self_play_engine=self_play_engine,
                config=config,
            )
            return {
                "action": "play",
                "batch_fill": batch_fill,
                "buffer_size": len(loop_store.active_buffer_rows()),
            }

        if action == "tune":
            # T-path only: fill buffer + train + holdout gate
            state = LoopStateStore(root).load()
            loop_store = LoopStore(root)
            # Honor force_regression from scenario (needed for demo promotion)
            if scenario.get("force_regression", False):
                bad = registry.create_version(
                    agent_id,
                    components={"model_id": "bad-regress-v1"},
                    source="clock-t-path-setup",
                )
                registry.activate(agent_id, bad["version_id"])
            t_result = run_t_path(
                client=loop_client,
                registry=registry,
                loop_store=loop_store,
                state=state,
                coaching_root=root,
                agent_id=agent_id,
                beta=config.batch_size,
                self_play_engine=self_play_engine,
                config=config,
            )
            if t_result is not None:
                LoopStateStore(root).save(state)
            return {
                "action": "tune",
                "t_path": t_result,
                "t_path_promoted": bool((t_result or {}).get("promoted")),
            }

        # Unknown partial action — fall back to full tick (defensive)
        from coach.clock import run_tick as _full_tick

        return _full_tick(root, scenario, client=client, trajectory_fn=trajectory_fn)
    finally:
        if _prev_agent is None:
            os.environ.pop("AGENT_ID", None)
        else:
            os.environ["AGENT_ID"] = _prev_agent
        if _prev_loop is None:
            os.environ.pop("LOOP_AGENT_ID", None)
        else:
            os.environ["LOOP_AGENT_ID"] = _prev_loop


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
