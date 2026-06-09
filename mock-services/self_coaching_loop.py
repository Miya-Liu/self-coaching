#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Self-coaching loop demo driver — task stream, E-path, T-path, scenario manifests.

Usage:
  python mock-services/self_coaching_loop.py run \\
    --root mock-services/demo-loop \\
    --scenario scenarios/full_loop.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
_SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
for _entry in (str(_SC_ROOT), str(_SC_ROOT / "self-learning"), str(REPO_ROOT / "mock-services"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from client import ModuleClient  # noqa: E402
from loop_driver import run_tasks, run_t_path  # noqa: E402
from loop_store import LoopStore  # noqa: E402
from mock_agent_registry import AgentRegistry  # noqa: E402
from state import LoopStateStore  # noqa: E402


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


def run_scenario(
    coaching_root: str | Path,
    scenario: dict[str, Any],
    *,
    client: ModuleClient | None = None,
) -> dict[str, Any]:
    """Run a scenario manifest (full_loop: E-path → buffer fill → T-path promote)."""
    root = Path(coaching_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    agent_id = _scenario_agent_id(scenario)
    loop_cfg = scenario.get("loop") or {}
    streams = scenario.get("task_streams") or {}

    e_path_stream = _resolve_path(
        streams.get("e_path") or "mock-services/fixtures/task_stream/e_path_v1.jsonl"
    )
    t_path_stream = _resolve_path(
        streams.get("t_path") or "mock-services/fixtures/task_stream/t_path_v1.jsonl"
    )

    os.environ.setdefault("LOOP_AGENT_ID", agent_id)
    os.environ.setdefault("AGENT_ID", agent_id)

    loop_client = client or ModuleClient(root)
    registry = AgentRegistry(root)
    registry.ensure_agent(agent_id)

    generation_before = LoopStateStore(root).load().generation

    _, state_after_e = run_tasks(
        root,
        task_stream_path=e_path_stream,
        limit=int(loop_cfg.get("e_path_limit", 10)),
        sigma_min=int(loop_cfg.get("sigma_min", os.environ.get("LOOP_SIGMA_MIN", 3))),
        sigma_play=int(loop_cfg.get("sigma_play", os.environ.get("LOOP_SIGMA_PLAY", 0))),
        enable_e_path=True,
        enable_t_path=False,
        client=loop_client,
        agent_id=agent_id,
        tau_fail=float(loop_cfg.get("tau_fail", os.environ.get("LOOP_TAU_FAIL", 0.75))),
    )

    run_tasks(
        root,
        task_stream_path=t_path_stream,
        limit=int(loop_cfg.get("t_path_limit", 4)),
        enable_e_path=False,
        enable_t_path=False,
        client=loop_client,
        agent_id=agent_id,
    )

    bad = registry.create_version(
        agent_id,
        components={"model_id": "bad-regress-v1"},
        source="full-loop-t-path-setup",
    )
    registry.activate(agent_id, bad["version_id"])

    loop_store = LoopStore(root)
    state = LoopStateStore(root).load()
    beta = int(loop_cfg.get("beta", os.environ.get("LOOP_BATCH_SIZE", 4)))
    t_result = run_t_path(
        client=loop_client,
        registry=registry,
        loop_store=loop_store,
        state=state,
        coaching_root=root,
        agent_id=agent_id,
        beta=beta,
    )
    if t_result is None:
        raise RuntimeError("T-path did not run (buffer batch not filled)")

    LoopStateStore(root).save(state)
    versions = registry.list_versions(agent_id)
    active = registry.get_agent(agent_id)

    summary = {
        "scenario": scenario.get("name", "unknown"),
        "agent_id": agent_id,
        "generation_before": generation_before,
        "generation_after": state.generation,
        "tasks_processed": state.tasks_processed,
        "version_count": len(versions),
        "active_version_id": active["active_version_id"],
        "t_path_promoted": bool(t_result.get("promoted")),
        "coaching_root": str(root),
    }
    write_demo_summary(root, summary, t_result)
    return summary


def write_demo_summary(root: Path, summary: dict[str, Any], t_result: dict[str, Any]) -> Path:
    out = root / ".self-coaching" / "loop" / "demo_summary.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Self-coaching loop demo summary",
        "",
        f"- **Generated:** {ts}",
        f"- **Scenario:** {summary.get('scenario')}",
        f"- **Agent:** {summary.get('agent_id')}",
        f"- **Generation:** {summary.get('generation_before')} → {summary.get('generation_after')}",
        f"- **Tasks processed:** {summary.get('tasks_processed')}",
        f"- **Registry versions:** {summary.get('version_count')}",
        f"- **Active version:** {summary.get('active_version_id')}",
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
    summary = run_scenario(args.root, scenario)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"self-coaching-loop: scenario={summary['scenario']} "
            f"generation={summary['generation_before']}→{summary['generation_after']} "
            f"versions={summary['version_count']} promoted={summary['t_path_promoted']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Self-coaching loop demo driver")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a scenario manifest end-to-end")
    run_p.add_argument("--root", type=Path, required=True, help="Coaching root directory")
    run_p.add_argument(
        "--scenario",
        type=Path,
        default=REPO_ROOT / "scenarios" / "full_loop.json",
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
