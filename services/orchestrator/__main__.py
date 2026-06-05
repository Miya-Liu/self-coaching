# SPDX-License-Identifier: MIT
"""CLI: python -m services.orchestrator <command>"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .drop_detector import check_drop, load_thresholds
from .eval_metrics import latest_metrics, metrics_store_path
from .runner import record_eval, run_improvement


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cmd_record_eval(args: argparse.Namespace) -> int:
    metrics = record_eval(
        Path(args.coaching_root),
        agent_id=args.agent_id,
        candidate=args.candidate,
        baseline=args.baseline,
        skill_bundle_version=args.skill_bundle_version,
        split=args.split,
        baseline_score=args.baseline_score,
    )
    print(json.dumps(metrics.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_check_drop(args: argparse.Namespace) -> int:
    metrics_dir = Path(args.metrics_dir)
    store = metrics_dir / "eval_metrics.jsonl" if metrics_dir.is_dir() else metrics_dir
    latest = latest_metrics(store, args.agent_id)
    if latest is None:
        print(json.dumps({"triggered": False, "reasons": ["no_metrics"]}, indent=2))
        return 0
    thresholds_path = Path(args.thresholds) if args.thresholds else (
        Path(__file__).resolve().parent / "config" / "thresholds.json"
    )
    result = check_drop(latest, load_thresholds(thresholds_path))
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 1 if result.triggered else 0


def cmd_run(args: argparse.Namespace) -> int:
    result = run_improvement(
        Path(args.coaching_root),
        Path(args.run_dir),
        agent_id=args.agent_id,
        force_trigger=args.force_trigger,
        thresholds_path=Path(args.thresholds) if args.thresholds else None,
        production_candidate=args.production_candidate,
        production_baseline=args.production_baseline,
        train_pipeline=args.pipeline,
        capability=args.capability,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("status") == "skipped":
        return 0
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evolution engine (T3): record-eval, check-drop, run (M1)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("record-eval", help="Run eval and append EvalMetrics to the metrics store")
    p.add_argument("--coaching-root", required=True, help="Root with .self-coaching/ layout")
    p.add_argument("--agent-id", default="default-agent")
    p.add_argument("--candidate", default="mock-candidate-v1")
    p.add_argument("--baseline", default="mock-baseline-v0")
    p.add_argument("--skill-bundle-version", default="unknown")
    p.add_argument("--split", default="canary", choices=["canary", "holdout"])
    p.add_argument("--baseline-score", type=float, default=None,
                   help="Override baseline_score in metrics (for testing drops)")
    p.set_defaults(func=cmd_record_eval)

    p = sub.add_parser("check-drop", help="Check latest metrics against thresholds (exit 1 if drop)")
    p.add_argument("--metrics-dir", required=True,
                   help="Metrics directory or path to eval_metrics.jsonl")
    p.add_argument("--agent-id", default=None)
    p.add_argument("--thresholds", default=None)
    p.set_defaults(func=cmd_check_drop)

    p = sub.add_parser("run", help="Run improvement loop into --run-dir (dry deploy)")
    p.add_argument("--coaching-root", required=True)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--agent-id", default="default-agent")
    p.add_argument("--force-trigger", action="store_true",
                   help="Skip drop check and run improvement anyway")
    p.add_argument("--thresholds", default=None)
    p.add_argument("--production-candidate", default="mock-baseline-v0")
    p.add_argument("--production-baseline", default="mock-baseline-v0")
    p.add_argument("--pipeline", default="sft", choices=["sft", "grpo"])
    p.add_argument("--capability", default="tool_use")
    p.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    # Allow `python -m services.orchestrator` from repo root.
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    raise SystemExit(main())
