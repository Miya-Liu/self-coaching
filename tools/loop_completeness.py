#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Mock-completeness reporter for the self-coaching loop demo pipeline.

Reads loop artifacts, registry lineage, and T-path run_dir eval files; emits
completeness_report.json covering matrix rows C01–C18 (§7 of the demo plan).

Usage:
  python tools/loop_completeness.py --root PATH [--expect-json SCENARIO] [--json | --markdown]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
for _entry in (
    str(REPO_ROOT),
    str(REPO_ROOT / "mock-services"),
    str(REPO_ROOT / "modes" / "self-coaching"),
):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from loop_store import read_jsonl  # noqa: E402
from mock_agent_registry import AgentRegistry  # noqa: E402


@dataclass(frozen=True)
class MatrixRow:
    id: str
    invocation: str | None
    semantic: str | None
    evidence: str


@dataclass
class AuditContext:
    root: Path
    scenario: dict[str, Any]
    agent_id: str
    state: dict[str, Any]
    support_rows: list[dict[str, Any]]
    buffer_rows: list[dict[str, Any]]
    trajectories: list[Path]
    registry: AgentRegistry
    versions: list[dict[str, Any]]
    bootstrap_version: dict[str, Any] | None
    e_path_last: dict[str, Any] | None
    t_path_last: dict[str, Any] | None
    t_path_run_dir: Path | None
    curated: Path


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _split_ids(path: Path) -> set[str]:
    return {str(r.get("case_id") or r.get("id")) for r in read_jsonl(path) if r.get("case_id") or r.get("id")}


def _agent_safe(agent_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", agent_id).strip("-") or "agent"


def load_scenario(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"name": "default"}
    return json.loads(path.read_text(encoding="utf-8"))


def build_context(root: Path, scenario: dict[str, Any]) -> AuditContext:
    agent_id = str(scenario.get("agent_id") or "demo-agent")
    loop_dir = root / ".self-coaching" / "loop"
    trajectories_dir = loop_dir / "trajectories"
    trajectories = sorted(trajectories_dir.glob("*.json")) if trajectories_dir.is_dir() else []

    registry = AgentRegistry(root)
    versions: list[dict[str, Any]] = []
    bootstrap_version: dict[str, Any] | None = None
    try:
        registry.ensure_agent(agent_id)
        versions = registry.list_versions(agent_id)
        for version in versions:
            if version.get("parent_version_id") is None:
                bootstrap_version = version
                break
    except Exception:
        pass

    t_path_run_dir = loop_dir / "runs" / "t_path"
    if not t_path_run_dir.is_dir():
        t_path_run_dir = None

    return AuditContext(
        root=root,
        scenario=scenario,
        agent_id=agent_id,
        state=_read_json(loop_dir / "state.json") or {},
        support_rows=read_jsonl(loop_dir / "support.jsonl"),
        buffer_rows=read_jsonl(loop_dir / "tuning_buffer.jsonl"),
        trajectories=trajectories,
        registry=registry,
        versions=versions,
        bootstrap_version=bootstrap_version,
        e_path_last=_read_json(loop_dir / "e_path_last.json"),
        t_path_last=_read_json(loop_dir / "t_path_last.json"),
        t_path_run_dir=t_path_run_dir,
        curated=root / ".self-coaching" / "curated",
    )


def _row(
    check_id: str,
    *,
    invocation: str | None = None,
    semantic: str | None = None,
    evidence: str = "",
) -> MatrixRow:
    return MatrixRow(id=check_id, invocation=invocation, semantic=semantic, evidence=evidence)


def _t_path_outcome(scenario: dict[str, Any]) -> str:
    t_path = scenario.get("t_path") or {}
    return str(t_path.get("outcome") or "skip")


def _expect_sparse_self_play(scenario: dict[str, Any]) -> bool:
    e_path = scenario.get("e_path") or {}
    if "expect_sparse_self_play" in e_path:
        return bool(e_path["expect_sparse_self_play"])
    return False


def _expect_t_path(scenario: dict[str, Any]) -> bool:
    t_path = scenario.get("t_path") or {}
    outcome = _t_path_outcome(scenario)
    if outcome in {"promote", "reject"}:
        return True
    loop_cfg = scenario.get("loop") or {}
    return bool(loop_cfg.get("enable_t_path"))


def _expect_batch_self_play(ctx: AuditContext) -> bool:
    if not _expect_t_path(ctx.scenario):
        return False
    batch_fill = (ctx.t_path_last or {}).get("batch_fill") or {}
    return bool(
        batch_fill.get("suite_id")
        or batch_fill.get("job_id")
        or int(batch_fill.get("count", 0)) > 0
    )


def _sparse_self_play_ok(sparse: dict[str, Any]) -> tuple[bool, str]:
    """Pass when mock suite_id exists or pipeline sparse job succeeded (proceed + job_id)."""
    suite_id = sparse.get("suite_id")
    if suite_id:
        return True, f"suite_id={suite_id}"
    job_id = sparse.get("job_id")
    if sparse.get("pipeline_service") and sparse.get("proceed") and job_id:
        return True, f"pipeline job_id={job_id} proceed={sparse.get('proceed')}"
    if job_id:
        return True, f"job_id={job_id}"
    return False, "missing sparse self-play suite_id or pipeline job_id"


def check_c01(ctx: AuditContext) -> MatrixRow:
    meta = ctx.root / "agents" / _agent_safe(ctx.agent_id) / "meta.json"
    ok = meta.is_file()
    return _row("C01", invocation="pass" if ok else "fail", evidence=str(meta.relative_to(ctx.root)) if ok else "missing meta.json")


def check_c02(ctx: AuditContext) -> MatrixRow:
    ok = len(ctx.trajectories) > 0
    evidence = str(ctx.trajectories[0].relative_to(ctx.root)) if ok else "no trajectories"
    return _row("C02", invocation="pass" if ok else "fail", evidence=evidence)


def check_c03(ctx: AuditContext) -> MatrixRow:
    with_rubric = 0
    for path in ctx.trajectories:
        traj = json.loads(path.read_text(encoding="utf-8"))
        if traj.get("rubric_result"):
            with_rubric += 1
    ok = with_rubric > 0
    return _row(
        "C03",
        invocation="pass" if ok else "fail",
        evidence=f"rubric_result on {with_rubric}/{len(ctx.trajectories)} trajectories",
    )


def check_c04(ctx: AuditContext) -> MatrixRow:
    ok = len(ctx.support_rows) > 0 or (ctx.e_path_last or {}).get("sigma_size_before_learn", 0) > 0
    return _row(
        "C04",
        invocation="pass" if ok else "fail",
        evidence=f"support.jsonl rows={len(ctx.support_rows)}",
    )


def check_c05(ctx: AuditContext) -> MatrixRow:
    ok = len(ctx.buffer_rows) > 0
    return _row(
        "C05",
        invocation="pass" if ok else "fail",
        evidence=f"tuning_buffer.jsonl rows={len(ctx.buffer_rows)}",
    )


def check_c06(ctx: AuditContext) -> MatrixRow:
    if not _expect_sparse_self_play(ctx.scenario):
        return _row("C06", invocation=None, evidence="not required for scenario")
    sparse = (ctx.e_path_last or {}).get("sparse_self_play") or {}
    ok, evidence = _sparse_self_play_ok(sparse)
    return _row(
        "C06",
        invocation="pass" if ok else "fail",
        evidence=evidence,
    )


def check_c07(ctx: AuditContext) -> MatrixRow:
    if not _expect_batch_self_play(ctx):
        return _row("C07", invocation=None, evidence="batch self-play not required")
    batch_fill = (ctx.t_path_last or {}).get("batch_fill") or {}
    suite_id = batch_fill.get("suite_id")
    job_id = batch_fill.get("job_id")
    count = int(batch_fill.get("count", 0))
    ok = bool(suite_id) or bool(job_id) or count > 0
    if suite_id:
        evidence = f"suite_id={suite_id} count={count}"
    elif job_id:
        evidence = f"job_id={job_id} count={count} proceed={batch_fill.get('proceed')}"
    else:
        evidence = f"count={count}"
    return _row(
        "C07",
        invocation="pass" if ok else "fail",
        evidence=evidence,
    )


def check_c08(ctx: AuditContext) -> MatrixRow:
    if not ctx.versions or ctx.bootstrap_version is None:
        return _row("C08", invocation="fail", evidence="no registry versions")
    changed = False
    evidence_parts: list[str] = []
    for version in ctx.versions:
        if version.get("version_id") == ctx.bootstrap_version.get("version_id"):
            continue
        components = version.get("components") or {}
        skill = str(components.get("skill_bundle_version", ""))
        memory = str(components.get("memory_ref", ""))
        if skill and skill != "skills-bootstrap":
            changed = True
            evidence_parts.append(f"skill_bundle_version={skill}")
        if memory and memory != "mem-bootstrap":
            changed = True
            evidence_parts.append(f"memory_ref={memory}")
    return _row(
        "C08",
        invocation="pass" if changed else "fail",
        evidence="; ".join(evidence_parts) if evidence_parts else "no skill/memory draft",
    )


def check_c09(ctx: AuditContext) -> MatrixRow:
    versions_dir = ctx.root / "agents" / _agent_safe(ctx.agent_id) / "versions"
    files = sorted(versions_dir.glob("*.json")) if versions_dir.is_dir() else []
    ok = len(files) > 1
    return _row(
        "C09",
        invocation="pass" if ok else "fail",
        evidence=f"versions/*.json count={len(files)}",
    )


def check_c10(ctx: AuditContext) -> MatrixRow:
    generation = int(ctx.state.get("generation", 0))
    min_bump = int((ctx.scenario.get("e_path") or {}).get("min_generation_bump", 1))
    ok = generation >= min_bump
    return _row(
        "C10",
        invocation="pass" if ok else "fail",
        evidence=f"state.generation={generation} (min {min_bump})",
    )


def check_c11(ctx: AuditContext) -> MatrixRow:
    generation = int(ctx.state.get("generation", 0))
    stale_active = [
        row for row in ctx.buffer_rows if not row.get("used_for_train") and int(row.get("generation", 0)) < generation
    ]
    ok = not stale_active
    return _row(
        "C11",
        invocation="pass" if ok else "fail",
        evidence=f"stale active buffer rows={len(stale_active)}",
    )


def check_c12(ctx: AuditContext) -> MatrixRow:
    if not _expect_t_path(ctx.scenario):
        return _row("C12", invocation=None, evidence="T-path not expected")
    run_dir = ctx.t_path_run_dir
    current = run_dir / "current_eval.json" if run_dir else None
    candidate = run_dir / "candidate_eval.json" if run_dir else None
    has_run_evals = (
        current is not None
        and candidate is not None
        and current.is_file()
        and candidate.is_file()
    )
    reports_dir = ctx.root / ".self-coaching" / "reports" / "eval_runs"
    has_report = reports_dir.is_dir() and any(reports_dir.glob("*/report.json"))
    ok = has_run_evals or has_report
    if has_run_evals and run_dir is not None:
        evidence = str(run_dir.relative_to(ctx.root))
    elif has_report:
        evidence = str(next(reports_dir.glob("*/report.json")).relative_to(ctx.root))
    else:
        evidence = "missing holdout eval artifacts"
    return _row("C12", invocation="pass" if ok else "fail", evidence=evidence)


def check_c13(ctx: AuditContext) -> MatrixRow:
    if not _expect_t_path(ctx.scenario):
        return _row("C13", invocation=None, evidence="T-path not expected")
    train = (ctx.t_path_last or {}).get("train_result") or {}
    manifest = ctx.root / ".self-coaching" / "manifests" / "training_run_manifest.json"
    ok = bool(train.get("run_id") or train.get("status")) or manifest.is_file()
    return _row(
        "C13",
        invocation="pass" if ok else "fail",
        evidence=f"train run_id={train.get('run_id')} manifest={manifest.is_file()}",
    )


def check_c14(ctx: AuditContext) -> MatrixRow:
    outcome = _t_path_outcome(ctx.scenario)
    if outcome != "promote":
        return _row("C14", invocation=None, evidence=f"t_path.outcome={outcome}")
    promoted = bool((ctx.t_path_last or {}).get("promoted"))
    active_path = ctx.root / "agents" / _agent_safe(ctx.agent_id) / "active.json"
    ok = promoted and active_path.is_file()
    return _row(
        "C14",
        invocation="pass" if ok else "fail",
        evidence=str(active_path.relative_to(ctx.root)) if ok else "hot-swap not recorded",
    )


def check_c15(ctx: AuditContext) -> MatrixRow:
    self_play_ran = _expect_sparse_self_play(ctx.scenario) or _expect_batch_self_play(ctx)
    validation = ctx.curated / "validation.jsonl"
    holdout = ctx.curated / "holdout.jsonl"
    if not self_play_ran:
        return _row("C15", invocation=None, evidence="self-play not required")
    ok = validation.is_file() and holdout.is_file() and validation.stat().st_size > 0 and holdout.stat().st_size > 0
    return _row(
        "C15",
        invocation="pass" if ok else "fail",
        evidence=f"validation={validation.stat().st_size if validation.is_file() else 0}b holdout={holdout.stat().st_size if holdout.is_file() else 0}b",
    )


def _loop_train_ids(ctx: AuditContext) -> set[str]:
    train_path = ctx.curated / "train.jsonl"
    loop_ids = {
        str(row.get("id"))
        for row in read_jsonl(train_path)
        if row.get("source") == "loop_buffer" and row.get("id")
    }
    if loop_ids:
        return loop_ids
    return _split_ids(train_path)


def check_c16(ctx: AuditContext) -> MatrixRow:
    train_ids = _loop_train_ids(ctx)
    holdout_ids = _split_ids(ctx.curated / "holdout.jsonl")
    validation_ids = _split_ids(ctx.curated / "validation.jsonl")
    overlap = sorted((train_ids & holdout_ids) | (train_ids & validation_ids))
    ok = not overlap
    scope = "loop_buffer train" if train_ids else "train"
    return _row(
        "C16",
        semantic="pass" if ok else "fail",
        evidence=f"{scope}∩holdout empty" if ok else f"overlap={overlap}",
    )


def check_c17(ctx: AuditContext) -> MatrixRow:
    generation = int(ctx.state.get("generation", 0))
    stale_consumed = [
        row for row in ctx.buffer_rows if row.get("used_for_train") and int(row.get("generation", 0)) < generation
    ]
    ok = not stale_consumed
    return _row(
        "C17",
        semantic="pass" if ok else "fail",
        evidence=f"consumed stale rows={len(stale_consumed)}",
    )


def check_c18(ctx: AuditContext) -> MatrixRow:
    outcome = _t_path_outcome(ctx.scenario)
    if outcome != "promote":
        return _row("C18", semantic=None, evidence=f"t_path.outcome={outcome}; C18 skipped")

    run_dir = ctx.t_path_run_dir
    if run_dir is None:
        return _row("C18", semantic="fail", evidence="missing t_path run_dir")

    current_path = run_dir / "current_eval.json"
    candidate_path = run_dir / "candidate_eval.json"
    if not current_path.is_file() or not candidate_path.is_file():
        return _row("C18", semantic="fail", evidence="missing current_eval.json or candidate_eval.json")

    current = json.loads(current_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    current_score = float(current.get("score", 0.0))
    candidate_score = float(candidate.get("score", 0.0))
    ok = candidate_score >= current_score
    return _row(
        "C18",
        semantic="pass" if ok else "fail",
        evidence=f"candidate_eval.score={candidate_score:.4f} >= current_eval.score={current_score:.4f}",
    )


CHECKERS: list[Callable[[AuditContext], MatrixRow]] = [
    check_c01,
    check_c02,
    check_c03,
    check_c04,
    check_c05,
    check_c06,
    check_c07,
    check_c08,
    check_c09,
    check_c10,
    check_c11,
    check_c12,
    check_c13,
    check_c14,
    check_c15,
    check_c16,
    check_c17,
    check_c18,
]


def _required_row_ids(scenario: dict[str, Any]) -> frozenset[str] | None:
    completeness = scenario.get("completeness") or {}
    required = completeness.get("require_pass")
    if not required:
        return None
    return frozenset(str(row_id) for row_id in required)


def run_audit(ctx: AuditContext) -> dict[str, Any]:
    rows = [checker(ctx) for checker in CHECKERS]
    failures: list[str] = []
    required_rows = _required_row_ids(ctx.scenario)

    for row in rows:
        if required_rows is not None and row.id not in required_rows:
            continue
        if row.invocation == "fail":
            failures.append(f"{row.id} invocation")
        if row.semantic == "fail":
            failures.append(f"{row.id} semantic")

    generation = int(ctx.state.get("generation", 0))
    min_bump = int((ctx.scenario.get("e_path") or {}).get("min_generation_bump", 1))
    if required_rows is None and generation < min_bump:
        failures.append("generation bump")

    status = "PASS" if not failures else "FAIL"
    return {
        "status": status,
        "scenario": ctx.scenario.get("name", "default"),
        "agent_id": ctx.agent_id,
        "generation": generation,
        "failures": failures,
        "rows": [
            {
                "id": row.id,
                "invocation": row.invocation,
                "semantic": row.semantic,
                "evidence": row.evidence,
            }
            for row in rows
        ],
    }


def write_report(root: Path, report: dict[str, Any]) -> Path:
    out = root / ".self-coaching" / "loop" / "completeness_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Loop completeness — {report.get('scenario', 'default')}",
        "",
        f"**Status:** {report.get('status')}",
        f"**Generation:** {report.get('generation')}",
        "",
        "| ID | Invocation | Semantic | Evidence |",
        "|----|------------|----------|----------|",
    ]
    for row in report.get("rows", []):
        inv = row.get("invocation") if row.get("invocation") is not None else "—"
        sem = row.get("semantic") if row.get("semantic") is not None else "—"
        lines.append(f"| {row['id']} | {inv} | {sem} | {row.get('evidence', '')} |")
    if report.get("failures"):
        lines.extend(["", "**Failures:**", *[f"- {item}" for item in report["failures"]]])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Self-coaching loop completeness audit (C01–C18)")
    parser.add_argument("--root", type=Path, required=True, help="Coaching root directory")
    parser.add_argument("--expect-json", type=Path, default=None, help="Scenario manifest JSON")
    parser.add_argument("--json", action="store_true", help="Print report JSON to stdout")
    parser.add_argument("--markdown", action="store_true", help="Print markdown summary to stdout")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    scenario = load_scenario(args.expect_json)
    ctx = build_context(root, scenario)
    report = run_audit(ctx)
    report_path = write_report(root, report)

    if args.markdown:
        print(format_markdown(report), end="")
    elif args.json or not args.markdown:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    if not args.json and not args.markdown:
        print(f"\nWrote {report_path}", file=sys.stderr)

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
