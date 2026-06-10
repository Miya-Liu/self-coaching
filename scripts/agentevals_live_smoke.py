#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Opt-in smoke test against a live AgentEvals service (default http://localhost:8080).

Usage:
  python scripts/agentevals_live_smoke.py
  AGENTEVALS_BASE_URL=http://localhost:8080 AGENTEVALS_MODEL_NAME=gpt-4o python scripts/agentevals_live_smoke.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.adapters.agentevals_client import AgentEvalsClient, AgentEvalsError
from services.adapters.agentevals_mapping import build_agent_config
from services.orchestrator.eval_metrics import normalize_from_agentevals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live AgentEvals connectivity + mapping smoke")
    parser.add_argument("--base-url", default=os.environ.get("AGENTEVALS_BASE_URL", "http://localhost:8080"))
    parser.add_argument("--suite-id", default=os.environ.get("AGENTEVALS_SUITE_ID", "MemoryArena_Preview"))
    parser.add_argument("--model-name", default=os.environ.get("AGENTEVALS_MODEL_NAME", "gpt-4o"))
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("LOOP_AGENT_ID") or os.environ.get("AGENT_ID") or "6ed953f5-ca52-45ff-a137-9d2d1b2e1d8d",
    )
    parser.add_argument("--timeout-s", type=float, default=float(os.environ.get("AGENTEVALS_TIMEOUT_S", "600")))
    args = parser.parse_args(argv)

    client = AgentEvalsClient(base_url=args.base_url, poll_timeout_s=args.timeout_s)
    print(f"==> health {args.base_url}")
    health = client.health()
    if str(health.get("status", "")).lower() != "ok":
        raise SystemExit(f"unexpected health response: {health!r}")
    print(json.dumps(health))

    print("==> list suites")
    suites = client.list_suites()
    suite_ids = [str(s.get("id")) for s in suites]
    print(f"suites ({len(suite_ids)}): {', '.join(suite_ids)}")
    if args.suite_id not in suite_ids:
        raise SystemExit(f"suite {args.suite_id!r} not found; available: {suite_ids}")

    agent_config = build_agent_config(
        agent_id=args.agent_id,
        version_id="ver-smoke-candidate",
        baseline_version_id="ver-smoke-baseline",
        model_name=args.model_name,
    )
    print("==> create run")
    print(json.dumps({"suite_id": args.suite_id, "agent_config": agent_config}, indent=2))
    created = client.create_run(
        suite_id=args.suite_id,
        agent_config=agent_config,
        num_trials=1,
    )
    run_id = str(created.get("id") or "")
    if not run_id:
        raise AgentEvalsError("create_run missing id", body=created)
    print(f"run_id={run_id}")

    print("==> wait for run")
    detail = client.wait_for_run(run_id)
    metrics = normalize_from_agentevals(
        agent_id=args.agent_id,
        run_detail=detail,
        skill_bundle_version="smoke",
        model_checkpoint_id="ver-smoke-candidate",
        split="holdout",
    )
    print(json.dumps(metrics.to_dict(), indent=2))
    print(f"agentevals-live-smoke: OK score={metrics.score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
