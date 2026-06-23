#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Smoke test: autonomous self-coaching clock loop (E → sparse P → batch P → T).

Usage:
  python scripts/clock_loop_smoke.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SC = REPO_ROOT / "modes" / "self-coaching"
_COACH = REPO_ROOT / "modes" / "coach"
_MODES = REPO_ROOT / "modes"
_MOCK = REPO_ROOT / "mock-services"
_TOOLS = REPO_ROOT / "tools"
for _entry in (
    str(_MODES),
    str(_COACH),
    str(_SC),
    str(_SC / "self-learning"),
    str(_MOCK),
    str(REPO_ROOT),
    str(_TOOLS),
):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from clock import load_scenario, run_tick  # noqa: E402
from loop_completeness import build_context, run_audit, write_report  # noqa: E402
from loop_env import configure_demo_env  # noqa: E402

GOLDEN = REPO_ROOT / "tests" / "fixtures" / "golden" / "completeness_report_clock_loop.json"
SCENARIO = REPO_ROOT / "scenarios" / "clock_loop.json"
ROOT = _MOCK / "ci-clock-loop"


def _check_golden(report: dict, golden: dict) -> list[str]:
    errors: list[str] = []
    if golden.get("status") is not None and report.get("status") != golden.get("status"):
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


def main() -> int:
    configure_demo_env()
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)

    scenario = load_scenario(SCENARIO)
    summary = run_tick(ROOT, scenario)
    if not summary.get("sparse_self_questioning_suite_id"):
        print("clock_loop_smoke: FAIL missing sparse self-questioning suite (C06)", file=sys.stderr)
        return 1
    if not summary.get("batch_self_questioning_suite_id"):
        print("clock_loop_smoke: FAIL missing batch self-questioning suite (C07)", file=sys.stderr)
        return 1
    if not summary.get("t_path_promoted"):
        print("clock_loop_smoke: FAIL T-path did not promote", file=sys.stderr)
        return 1

    report = run_audit(build_context(ROOT, scenario))
    write_report(ROOT, report)

    if not GOLDEN.is_file():
        raise SystemExit(f"golden fixture missing: {GOLDEN}")

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    errors = _check_golden(report, golden)
    if errors:
        for err in errors:
            print(f"GOLDEN FAIL: {err}", file=sys.stderr)
        report_path = ROOT / ".self-coaching" / "loop" / "completeness_report.json"
        print(f"report: {report_path}", file=sys.stderr)
        return 1

    print(
        "clock_loop_smoke: PASS "
        f"(C06={summary['sparse_self_questioning_suite_id']} "
        f"C07={summary['batch_self_questioning_suite_id']} "
        f"promoted={summary['t_path_promoted']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
