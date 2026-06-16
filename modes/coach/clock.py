#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Coach-mode autonomous clock — one evolution tick (E → P → T).

Models LOOP_EXECUTION_MODE=autonomous for supervised agents: observe failures,
self-evolve with sparse self-play, fill the tuning buffer, then self-tune when idle.

Usage:
  python modes/coach/clock.py run \\
    --root mock-services/ci-clock \\
    --scenario scenarios/clock_loop.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
_COACH_ROOT = HERE.parent
_SC_ROOT = _COACH_ROOT.parent / "self-coaching"
REPO_ROOT = _COACH_ROOT.parents[1]
_MOCK_SERVICES = REPO_ROOT / "mock-services"

for _entry in (
    str(_MOCK_SERVICES),
    str(REPO_ROOT),
    str(_SC_ROOT),
    str(_SC_ROOT / "self-learning"),
    str(_COACH_ROOT),
):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

try:
    from loop_driver import run_tasks, run_t_path  # noqa: E402
    from loop_env import build_loop_client  # noqa: E402
    from loop_store import LoopStore  # noqa: E402
    from state import LoopStateStore  # noqa: E402
except ImportError as exc:
    raise RuntimeError(
        f"Cannot import self-coaching loop driver from {_SC_ROOT}. "
        "Install with: pip install -e ."
    ) from exc
from mock_agent_registry import AgentRegistry  # noqa: E402


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_file():
        return candidate.resolve()
    rooted = REPO_ROOT / candidate
    if rooted.is_file():
        return rooted.resolve()
    return candidate.resolve()


def load_scenario(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve_path(path).read_text(encoding="utf-8"))


def _scenario_agent_id(scenario: dict[str, Any]) -> str:
    return str(scenario.get("agent_id") or os.environ.get("LOOP_AGENT_ID") or "demo-agent")


def run_tick(
    coaching_root: str | Path,
    scenario: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    """Run one autonomous evolution tick: E-path → buffer → T-path.

    Sets AGENT_ID/LOOP_AGENT_ID in os.environ for the duration of the tick
    (required by mock_self_coaching.learn() which reads it) but restores
    previous values on exit to prevent cross-agent contamination in the
    multi-agent scheduler.
    """
    root = Path(coaching_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    agent_id = _scenario_agent_id(scenario)
    loop_cfg = scenario.get("loop") or {}
    streams = scenario.get("task_streams") or {}

    e_path_stream = _resolve_path(
        streams.get("e_path") or "mock-services/fixtures/task_stream/clock_loop_e_v1.jsonl"
    )
    buffer_stream = _resolve_path(
        streams.get("buffer") or "mock-services/fixtures/task_stream/clock_loop_buffer_v1.jsonl"
    )

    # Build a LoopConfig from scenario values — no permanent env mutation.
    try:
        from loop_config import LoopConfig
    except ImportError:
        from self_coaching.loop_config import LoopConfig  # type: ignore[no-redef]

    sigma_min = int(loop_cfg.get("sigma_min", os.environ.get("LOOP_SIGMA_MIN", 3)))
    sigma_play = int(loop_cfg.get("sigma_play", os.environ.get("LOOP_SIGMA_PLAY", 3)))
    beta = int(loop_cfg.get("beta", os.environ.get("LOOP_BATCH_SIZE", 4)))
    tau_fail = float(loop_cfg.get("tau_fail", os.environ.get("LOOP_TAU_FAIL", 0.75)))

    config = LoopConfig(
        agent_id=agent_id,
        tau_fail=tau_fail,
        sigma_min=sigma_min,
        sigma_play=sigma_play,
        batch_size=beta,
        task_stream=e_path_stream,
    )

    # Scoped env-var set: mock_self_coaching.learn() reads AGENT_ID from env.
    # Restore on exit so concurrent ticks for other agents don't get contaminated.
    _prev_agent = os.environ.get("AGENT_ID")
    _prev_loop_agent = os.environ.get("LOOP_AGENT_ID")
    os.environ["AGENT_ID"] = agent_id
    os.environ["LOOP_AGENT_ID"] = agent_id
    try:
        return _run_tick_inner(root, scenario, config, e_path_stream, buffer_stream, agent_id, client)
    finally:
        if _prev_agent is None:
            os.environ.pop("AGENT_ID", None)
        else:
            os.environ["AGENT_ID"] = _prev_agent
        if _prev_loop_agent is None:
            os.environ.pop("LOOP_AGENT_ID", None)
        else:
            os.environ["LOOP_AGENT_ID"] = _prev_loop_agent


def _run_tick_inner(
    root: Path,
    scenario: dict[str, Any],
    config: Any,
    e_path_stream: Path,
    buffer_stream: Path,
    agent_id: str,
    client: Any | None,
) -> dict[str, Any]:
    """Inner tick logic (separated so run_tick can do env save/restore)."""
    loop_client = client or build_loop_client(root, config=config)
    registry = AgentRegistry(root)
    registry.ensure_agent(agent_id)
    generation_before = LoopStateStore(root).load().generation

    # Phase 1 — observe failures → self-evolution (sparse self-play + learn)
    run_tasks(
        root,
        config=config,
        task_stream_path=e_path_stream,
        enable_e_path=True,
        enable_t_path=False,
        client=loop_client,
        agent_id=agent_id,
    )

    # Phase 2 — partial buffer fill (forces C07 batch self-play on T-path)
    run_tasks(
        root,
        config=config,
        task_stream_path=buffer_stream,
        enable_e_path=False,
        enable_t_path=False,
        client=loop_client,
        agent_id=agent_id,
    )

    # Phase 3 — optionally regress production model so holdout gate can promote candidate.
    # This is demo scaffolding; real deployments skip it (force_regression: false in scenario).
    if scenario.get("force_regression", True):
        bad = registry.create_version(
            agent_id,
            components={"model_id": "bad-regress-v1"},
            source="clock-t-path-setup",
        )
        registry.activate(agent_id, bad["version_id"])

    # Phase 4 — idle window → batch self-play fill + self-tuning
    loop_store = LoopStore(root)
    state = LoopStateStore(root).load()
    t_result = run_t_path(
        client=loop_client,
        registry=registry,
        loop_store=loop_store,
        state=state,
        coaching_root=root,
        agent_id=agent_id,
        beta=config.batch_size,
        self_play_engine=None,
    )
    if t_result is None:
        raise RuntimeError("T-path did not run (buffer batch not filled)")

    LoopStateStore(root).save(state)
    versions = registry.list_versions(agent_id)
    active = registry.get_agent(agent_id)
    final_state = LoopStateStore(root).load()

    e_path_last_path = root / ".self-coaching" / "loop" / "e_path_last.json"
    e_path_last = (
        json.loads(e_path_last_path.read_text(encoding="utf-8"))
        if e_path_last_path.is_file()
        else {}
    )

    summary = {
        "scenario": scenario.get("name", "clock_loop"),
        "execution_mode": scenario.get("execution_mode", "autonomous"),
        "agent_id": agent_id,
        "generation_before": generation_before,
        "generation_after": final_state.generation,
        "tasks_processed": final_state.tasks_processed,
        "version_count": len(versions),
        "active_version_id": active["active_version_id"],
        "sparse_self_play_suite_id": (e_path_last.get("sparse_self_play") or {}).get("suite_id"),
        "batch_self_play_suite_id": (t_result.get("batch_fill") or {}).get("suite_id"),
        "t_path_promoted": bool(t_result.get("promoted")),
        "coaching_root": str(root),
    }
    write_summary(root, summary, t_result)
    return summary


def write_summary(root: Path, summary: dict[str, Any], t_result: dict[str, Any]) -> Path:
    out = root / ".self-coaching" / "loop" / "clock_summary.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Coach clock summary",
        "",
        f"- **Generated:** {ts}",
        f"- **Scenario:** {summary.get('scenario')}",
        f"- **Execution mode:** {summary.get('execution_mode')}",
        f"- **Agent:** {summary.get('agent_id')}",
        f"- **Generation:** {summary.get('generation_before')} → {summary.get('generation_after')}",
        f"- **Sparse self-play suite:** {summary.get('sparse_self_play_suite_id')}",
        f"- **Batch self-play suite:** {summary.get('batch_self_play_suite_id')}",
        f"- **T-path promoted:** {summary.get('t_path_promoted')}",
        "",
        "## Holdout gate",
        "",
        f"- Recommendation: {'promote' if t_result.get('promoted') else 'reject'}",
        f"- Gate reasons: {t_result.get('gate_reasons') or []}",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def cmd_run(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    summary = run_tick(args.root, scenario)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "clock: "
            f"scenario={summary['scenario']} "
            f"generation={summary['generation_before']}→{summary['generation_after']} "
            f"C06={summary['sparse_self_play_suite_id']} "
            f"C07={summary['batch_self_play_suite_id']} "
            f"promoted={summary['t_path_promoted']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coach-mode autonomous clock driver")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run one autonomous evolution tick")
    run_p.add_argument("--root", type=Path, required=True, help="Coaching root directory")
    run_p.add_argument(
        "--scenario",
        type=Path,
        default=REPO_ROOT / "scenarios" / "clock_loop.json",
        help="Scenario manifest JSON",
    )
    run_p.add_argument("--json", action="store_true", help="Emit summary JSON")
    run_p.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
