#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Opt-in M1 exit smoke: full loop with live AgentEvals holdout (mock learn/train).

Usage:
  python scripts/full_loop_live_smoke.py
  python scripts/full_loop_live_smoke.py --env-file scenarios/demo.agentevals.env.example

Requires AgentEvals at AGENTEVALS_BASE_URL (default http://10.110.158.144:8080).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SC = REPO_ROOT / "modes" / "self-coaching"
if str(_SC) not in sys.path:
    sys.path.insert(0, str(_SC))

from demo import run_demo  # noqa: E402

GOLDEN = REPO_ROOT / "tests" / "fixtures" / "golden" / "completeness_report_full_loop_live.json"
DEFAULT_ENV = REPO_ROOT / "scenarios" / "demo.agentevals.env.example"
REPORT = REPO_ROOT / "mock-services" / "demo-loop" / ".self-coaching" / "loop" / "completeness_report.json"


def _check_golden(report: dict, golden: dict) -> list[str]:
    errors: list[str] = []
    if report.get("status") != golden.get("status"):
        errors.append(f"status={report.get('status')!r} expected {golden.get('status')!r}")
    rows = {row["id"]: row for row in report.get("rows", [])}
    for spec in golden.get("rows", []):
        row_id = spec["id"]
        actual = rows.get(row_id)
        if actual is None:
            errors.append(f"missing row {row_id}")
            continue
        for col in ("invocation", "semantic"):
            expected = spec.get(col)
            if expected is not None and actual.get(col) != expected:
                errors.append(f"{row_id}.{col}={actual.get(col)!r} expected {expected!r}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live full_loop_live smoke (M1 exit)")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args(argv)

    if not args.env_file.is_file():
        raise SystemExit(f"env file not found: {args.env_file}")

    code = run_demo(env_file=args.env_file)
    if code != 0:
        return code

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    errors = _check_golden(report, golden)
    if errors:
        for err in errors:
            print(f"GOLDEN FAIL: {err}", file=sys.stderr)
        return 1

    print("full_loop_live_smoke: PASS (C12 invocation + C18 semantic)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
