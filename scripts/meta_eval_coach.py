#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Meta-evaluation: compare AgentCoachBridge vs MockCoachAgentBridge.

Runs N ticks with each bridge against the SAME fixture scenario and reports
which approach achieves better generation velocity and tick efficiency.

Usage:
  python scripts/meta_eval_coach.py
  python scripts/meta_eval_coach.py --ticks 10 --json

The candidate bridge uses a "SmartScriptedTransport" — a deterministic heuristic
that checks loop state and chooses an action accordingly, proving that a thinking
coach can outperform the blanket full_tick strategy. When you wire a real LLM
coach, this script serves as the baseline comparator.

Metrics:
  - generations_promoted: number of successful model promotions
  - ticks_total: how many ticks were executed
  - ticks_productive: ticks that produced a non-None result (held ticks are not productive)
  - tick_efficiency: ticks_productive / ticks_total
  - generation_velocity: generations_promoted / ticks_total
  - total_duration_s: wall-clock time for all ticks
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
_COACH = REPO_ROOT / "modes" / "coach"
_SC = REPO_ROOT / "modes" / "self-coaching"
_MOCK = REPO_ROOT / "mock-services"
_MODES = REPO_ROOT / "modes"
for _entry in (str(_MODES), str(_COACH), str(_SC), str(_SC / "self-learning"), str(_MOCK), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from loop_env import configure_demo_env  # noqa: E402
from coach.agent_bridge import MockCoachAgentBridge  # noqa: E402
from coach.agent_bridge_live import AgentCoachBridge  # noqa: E402
from coach.registry import load_registry  # noqa: E402
from coach.trigger import handle_post_body  # noqa: E402
from self_coaching.loop_store import LoopStore, read_jsonl  # noqa: E402
from self_coaching.state import LoopStateStore  # noqa: E402

REGISTRY = _COACH / "agents.clock.yaml"
ROOT = _MOCK / "ci-meta-eval"


# ---------------------------------------------------------------------------
# Smart scripted transport (deterministic heuristic coach)
# ---------------------------------------------------------------------------


class SmartScriptedTransport:
    """Deterministic heuristic that looks at loop state to decide actions.

    Strategy:
      - Σ empty + B empty → hold (nothing to do)
      - Σ has failures → learn (trigger E-path)
      - B needs filling → play (trigger C07)
      - B full → tune (trigger T-path)
      - Otherwise → full_tick

    This demonstrates that targeted decisions save work compared to always
    running the full E→P→T cycle.
    """

    def __init__(self, coaching_root: Path, *, sigma_min: int = 3, beta: int = 4):
        self._root = coaching_root
        self._sigma_min = sigma_min
        self._beta = beta
        self._tick_count = 0

    def complete(self, prompt: str) -> str:
        self._tick_count += 1
        try:
            state = LoopStateStore(self._root).load()
            store = LoopStore(self._root)
            sigma = len(read_jsonl(store.support_path))
            buffer = len(store.active_buffer_rows())
        except Exception:
            # First tick, state may not exist yet → full_tick to bootstrap
            return json.dumps({"action": "full_tick", "reason": "bootstrap (no state yet)"})

        # Heuristic decision
        if sigma == 0 and buffer == 0 and state.tasks_processed == 0:
            return json.dumps({"action": "full_tick", "reason": "cold start"})
        if sigma >= self._sigma_min:
            return json.dumps({"action": "learn", "reason": f"Σ={sigma} ≥ σ_min={self._sigma_min}"})
        if buffer < self._beta:
            return json.dumps({"action": "play", "reason": f"B={buffer} < β={self._beta}"})
        if buffer >= self._beta:
            return json.dumps({"action": "tune", "reason": f"B={buffer} ≥ β={self._beta}, ready to train"})
        return json.dumps({"action": "full_tick", "reason": "fallback"})


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@dataclass
class TickRecord:
    tick_num: int
    action: str
    outcome: str  # "completed" | "held" | "error"
    generation_delta: int
    duration_s: float
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class BridgeResult:
    name: str
    ticks: list[TickRecord] = field(default_factory=list)
    total_duration_s: float = 0.0

    @property
    def ticks_total(self) -> int:
        return len(self.ticks)

    @property
    def ticks_productive(self) -> int:
        return sum(1 for t in self.ticks if t.outcome == "completed")

    @property
    def generations_promoted(self) -> int:
        return sum(t.generation_delta for t in self.ticks)

    @property
    def tick_efficiency(self) -> float:
        return self.ticks_productive / self.ticks_total if self.ticks_total else 0.0

    @property
    def generation_velocity(self) -> float:
        return self.generations_promoted / self.ticks_total if self.ticks_total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ticks_total": self.ticks_total,
            "ticks_productive": self.ticks_productive,
            "generations_promoted": self.generations_promoted,
            "tick_efficiency": round(self.tick_efficiency, 3),
            "generation_velocity": round(self.generation_velocity, 3),
            "total_duration_s": round(self.total_duration_s, 2),
            "ticks": [
                {
                    "tick": t.tick_num,
                    "action": t.action,
                    "outcome": t.outcome,
                    "generation_delta": t.generation_delta,
                    "duration_s": round(t.duration_s, 2),
                }
                for t in self.ticks
            ],
        }


def _fresh_root() -> Path:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    return ROOT


def _run_n_ticks(
    bridge: Any,
    *,
    n: int,
    registry_path: Path,
) -> BridgeResult:
    """Run N ticks with the given bridge, collecting metrics."""
    root = _fresh_root()
    configure_demo_env()
    name = type(bridge).__name__
    result = BridgeResult(name=name)
    t0 = time.time()

    for i in range(n):
        gen_before = LoopStateStore(root).load().generation if (root / ".self-coaching" / "loop" / "state.json").exists() else 0
        tick_t0 = time.time()
        body = {
            "agent_id": "clock-demo-agent",
            "event": "scheduled_tick",
            "payload": {"suggested_action": "full_tick"},
        }
        try:
            resp = handle_post_body(body, registry_path, bridge)
            action = resp.get("plan", {}).get("action", "unknown")
            tick_result = resp.get("tick")
            if tick_result is None:
                outcome = "held"
                gen_delta = 0
            else:
                outcome = "completed"
                gen_after = tick_result.get("generation_after", tick_result.get("generation", gen_before))
                gen_delta = gen_after - gen_before if isinstance(gen_after, int) else 0
        except Exception as exc:
            action = "error"
            outcome = "error"
            gen_delta = 0

        result.ticks.append(TickRecord(
            tick_num=i + 1,
            action=action,
            outcome=outcome,
            generation_delta=gen_delta,
            duration_s=time.time() - tick_t0,
        ))

    result.total_duration_s = time.time() - t0
    return result


def run_meta_eval(*, n_ticks: int = 5) -> dict[str, Any]:
    """Run the comparison and return structured results."""
    # Baseline: MockCoachAgentBridge (always full_tick)
    baseline = _run_n_ticks(
        MockCoachAgentBridge(),
        n=n_ticks,
        registry_path=REGISTRY,
    )

    # Candidate: AgentCoachBridge with smart heuristic
    root_for_candidate = _fresh_root()
    candidate_transport = SmartScriptedTransport(root_for_candidate)
    candidate_bridge = AgentCoachBridge(candidate_transport)
    candidate = _run_n_ticks(
        candidate_bridge,
        n=n_ticks,
        registry_path=REGISTRY,
    )

    # Comparison
    comparison = {
        "n_ticks": n_ticks,
        "baseline": baseline.to_dict(),
        "candidate": candidate.to_dict(),
        "winner": (
            "candidate" if candidate.generation_velocity > baseline.generation_velocity
            else "baseline" if baseline.generation_velocity > candidate.generation_velocity
            else "tie"
        ),
        "velocity_delta": round(candidate.generation_velocity - baseline.generation_velocity, 3),
        "efficiency_delta": round(candidate.tick_efficiency - baseline.tick_efficiency, 3),
    }
    return comparison


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Meta-eval: coach-agent vs mock bridge")
    parser.add_argument("--ticks", type=int, default=5, help="Number of ticks per bridge")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON")
    args = parser.parse_args()

    result = run_meta_eval(n_ticks=args.ticks)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        b = result["baseline"]
        c = result["candidate"]
        print(f"Meta-eval: {args.ticks} ticks per bridge")
        print(f"{'':2}{'Metric':<25} {'Mock (baseline)':<18} {'Agent (candidate)'}")
        print(f"{'':2}{'-'*25} {'-'*18} {'-'*18}")
        print(f"{'':2}{'generations_promoted':<25} {b['generations_promoted']:<18} {c['generations_promoted']}")
        print(f"{'':2}{'ticks_productive':<25} {b['ticks_productive']:<18} {c['ticks_productive']}")
        print(f"{'':2}{'tick_efficiency':<25} {b['tick_efficiency']:<18} {c['tick_efficiency']}")
        print(f"{'':2}{'generation_velocity':<25} {b['generation_velocity']:<18} {c['generation_velocity']}")
        print(f"{'':2}{'total_duration_s':<25} {b['total_duration_s']:<18} {c['total_duration_s']}")
        print()
        print(f"  Winner: {result['winner']} (velocity Δ={result['velocity_delta']:+.3f}, efficiency Δ={result['efficiency_delta']:+.3f})")

    # Write report
    report_path = ROOT / "meta_eval_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n  Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
