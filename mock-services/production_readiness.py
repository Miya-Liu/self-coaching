#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Production-readiness harness for mock self-coaching services.

Validates pipeline phases, artifact contracts (validation/holdout splits), and
split hygiene. Exit 0 when all required checks pass.

Usage:
  python mock-services/production_readiness.py [--root PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "mock-services") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "mock-services"))

import mock_self_coaching as msc  # noqa: E402
from plugin_mock import register  # noqa: E402


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "required"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _artifact_paths(root: Path) -> list[Path]:
    base = root / ".self-coaching"
    return [
        root / "experience" / "EXPERIMENT_LOG.md",
        root / "experience" / "ERROR.md",
        root / "experience" / "LEARNINGS.md",
        base / "events" / "learning_events.jsonl",
        base / "cases" / "self_questioning_candidates.jsonl",
        base / "cases" / "eval_cases.jsonl",
        base / "curated" / "train.jsonl",
        base / "curated" / "validation.jsonl",
        base / "curated" / "holdout.jsonl",
        base / "manifests" / "training_run_manifest.json",
    ]


def check_artifact_contract(root: Path) -> Check:
    missing = [str(p.relative_to(root)) for p in _artifact_paths(root) if not p.is_file()]
    validation = root / ".self-coaching" / "curated" / "validation.jsonl"
    holdout = root / ".self-coaching" / "curated" / "holdout.jsonl"
    extra: list[str] = []
    if validation.is_file() and validation.stat().st_size == 0:
        extra.append("validation.jsonl is empty (need self_questioning n>=5)")
    if holdout.is_file() and holdout.stat().st_size == 0:
        extra.append("holdout.jsonl is empty")
    problems = missing + extra
    return Check(
        "artifact_contract_required_paths",
        not problems,
        f"missing: {missing}; issues: {extra}" if problems else "ok",
    )


def check_case_records(root: Path) -> Check:
    cases = _read_jsonl(root / ".self-coaching" / "cases" / "eval_cases.jsonl")
    if not cases:
        return Check("case_records_have_rubric_and_privacy", False, "cases=0")
    for case in cases:
        if not isinstance(case.get("rubric"), dict):
            return Check("case_records_have_rubric_and_privacy", False, f"missing rubric: {case.get('id')}")
        labels = case.get("labels") or {}
        if not labels.get("privacy_checked"):
            return Check("case_records_have_rubric_and_privacy", False, f"privacy_checked false: {case.get('id')}")
    return Check("case_records_have_rubric_and_privacy", True, f"cases={len(cases)}")


def _split_ids(path: Path) -> set[str]:
    return {str(r.get("case_id") or r.get("id")) for r in _read_jsonl(path) if r.get("case_id") or r.get("id")}


def check_eval_train_split(root: Path) -> Check:
    """Holdout/validation rows must not leak into train (curated split hygiene)."""
    curated = root / ".self-coaching" / "curated"
    train_ids = _split_ids(curated / "train.jsonl")
    holdout_ids = _split_ids(curated / "holdout.jsonl")
    validation_ids = _split_ids(curated / "validation.jsonl")
    overlap_holdout = sorted(train_ids & holdout_ids)
    overlap_validation = sorted(train_ids & validation_ids)
    problems = []
    if overlap_holdout:
        problems.append(f"train∩holdout={overlap_holdout}")
    if overlap_validation:
        problems.append(f"train∩validation={overlap_validation}")
    eval_case_count = len(_read_jsonl(root / ".self-coaching" / "cases" / "eval_cases.jsonl"))
    return Check(
        "eval_train_split_no_exact_id_overlap",
        not problems,
        "; ".join(problems) if problems else f"eval_cases={eval_case_count} train={len(train_ids)} holdout={len(holdout_ids)}",
    )


def run_pipeline_checks(root: Path) -> list[Check]:
    checks: list[Check] = []
    init_result = msc.init(root)
    checks.append(Check("phase_learning_init_workspace", init_result.get("status") == "initialized", str(init_result)[:200]))

    learn_result = msc.learn(
        root,
        "Production-readiness: verify side effects before claiming success",
        "production-readiness",
    )
    checks.append(
        Check(
            "phase_learning_event_written",
            bool(learn_result.get("id")),
            str({k: learn_result.get(k) for k in ("id", "classification", "privacy_checked")}),
        )
    )

    play = msc.self_questioning(root, capability="tool_use", n=5)
    checks.append(
        Check(
            "phase_self_questioning_generated_cases",
            int(play.get("count", 0)) >= 5 and bool(play.get("suite_id")),
            str({k: play.get(k) for k in ("status", "count", "suite_id")}),
        )
    )

    baseline = msc.evaluate(root, "mock-baseline-v0", "mock-baseline-v0")
    checks.append(
        Check(
            "phase_evaluation_baseline_passes",
            baseline.get("status") == "passed",
            str({k: baseline.get(k) for k in ("status", "run_id", "recommendation")}),
        )
    )

    bad = msc.evaluate(root, "mock-bad-candidate", "mock-baseline-v0")
    checks.append(
        Check(
            "negative_gate_bad_candidate_blocked",
            bad.get("recommendation") == "do_not_promote",
            str({k: bad.get(k) for k in ("status", "run_id", "recommendation")}),
        )
    )

    train = msc.train(root, pipeline="sft")
    checks.append(
        Check(
            "phase_training_manifest_written",
            train.get("status") == "trained" and bool(train.get("manifest")),
            str({k: train.get(k) for k in ("status", "run_id", "candidate")}),
        )
    )

    candidate_eval = msc.evaluate(root, str(train.get("candidate", "")), "mock-baseline-v0")
    checks.append(
        Check(
            "phase_candidate_eval_passes",
            candidate_eval.get("status") == "passed",
            str({k: candidate_eval.get(k) for k in ("status", "run_id", "recommendation")}),
        )
    )

    run_all_root = root / "run-all-subroot"
    run_all_root.mkdir(parents=True, exist_ok=True)
    summary = msc.run_all(run_all_root, capability="tool_use", pipeline="grpo")
    checks.append(
        Check(
            "phase_run_all_grpo_promotable",
            summary.get("status") == "ok" and summary.get("promotion_allowed") is True,
            str({k: summary.get(k) for k in ("status", "promotion_allowed")})[:200],
        )
    )

    return checks


def run_all_checks(root: Path) -> list[Check]:
    checks: list[Check] = []
    try:
        import plugin_mock  # noqa: F401

        checks.append(Check("import_mock_module", True, ""))
    except ImportError as exc:
        checks.append(Check("import_mock_module", False, str(exc)))

    checks.append(
        Check(
            "plugin_register_capabilities",
            register().get("name") == "mock-self-coaching",
            str(register()),
        )
    )
    checks.extend(run_pipeline_checks(root))
    checks.append(check_artifact_contract(root))
    checks.append(check_case_records(root))
    checks.append(check_eval_train_split(root))
    train_rows = _read_jsonl(root / ".self-coaching" / "curated" / "train.jsonl")
    checks.append(
        Check(
            "training_records_have_observable_traces",
            len(train_rows) >= 1,
            f"train={len(train_rows)}",
        )
    )
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock services production-readiness harness")
    parser.add_argument("--root", type=Path, help="coaching root (default: temp dir)")
    parser.add_argument("--json", action="store_true", help="print JSON report to stdout")
    args = parser.parse_args(argv)

    if args.root:
        root = args.root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        root = Path(tempfile.mkdtemp(prefix="mock-prod-ready-"))
        cleanup = True

    checks = run_all_checks(root)
    required_fail = [c for c in checks if c.severity == "required" and not c.ok]
    report = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "status": "PASS" if not required_fail else "FAIL",
        "checks": [
            {"name": c.name, "ok": c.ok, "detail": c.detail, "severity": c.severity}
            for c in checks
        ],
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Production-readiness: {report['status']} (root={root})")
        for c in checks:
            mark = "PASS" if c.ok else "FAIL"
            print(f"  [{mark}] {c.name}: {c.detail[:120]}")

    if cleanup and required_fail:
        print(f"(temp root preserved for debug: {root})", file=sys.stderr)

    return 0 if not required_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
