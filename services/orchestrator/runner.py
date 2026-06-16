# SPDX-License-Identifier: MIT
"""Evolution engine improvement runs (pipelines.md Phase 1, dry deploy)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .drop_detector import check_drop, check_promotion, load_thresholds
from .eval_metrics import (
    EvalMetrics,
    append_metrics,
    metrics_store_path,
    normalize_from_agentevals,
    normalize_from_mock_eval,
    write_json,
)


def _repo_root() -> Path:
    try:
        from self_coaching._paths import repo_root
        return repo_root()
    except ImportError:
        return Path(__file__).resolve().parents[2]


def _default_thresholds_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "thresholds.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _eval_backend() -> str:
    return os.environ.get("ORCHESTRATOR_EVAL_BACKEND", "mock").lower()


def _train_backend() -> str:
    return os.environ.get("ORCHESTRATOR_TRAIN_BACKEND", "mock").lower()


def _self_play_n() -> int:
    return int(os.environ.get("ORCHESTRATOR_SELF_PLAY_N", "4"))


def _min_cases_for_model() -> int:
    return int(os.environ.get("ORCHESTRATOR_MIN_CASES_FOR_MODEL", "100"))


def _learn_backend() -> str:
    return os.environ.get("ORCHESTRATOR_LEARN_BACKEND", "mock").lower()


def _build_client(coaching_root: Path) -> Any:
    mock_services = _repo_root() / "mock-services"
    if str(mock_services) not in sys.path:
        sys.path.insert(0, str(mock_services))
    import client as client_mod  # noqa: E402

    transport = os.environ.get("ORCHESTRATOR_TRANSPORT", "module").lower()
    if transport == "http":
        inner = client_mod.build_client(
            "http",
            base_url=os.environ.get("ORCHESTRATOR_BASE_URL", "http://127.0.0.1:8765"),
            api_key=os.environ.get("MOCK_SERVICE_TOKEN"),
        )
    else:
        inner = client_mod.build_client("module", root=coaching_root)

    from services.adapters import build_composite_client  # noqa: E402

    return build_composite_client(
        inner,
        eval_backend=_eval_backend(),
        train_backend=_train_backend(),
        learn_backend=_learn_backend(),
    )


def _normalize_eval(
    *,
    agent_id: str,
    eval_summary: dict[str, Any],
    report: dict[str, Any],
    baseline_score: float | None,
    skill_bundle_version: str,
    model_checkpoint_id: str,
    split: str,
) -> EvalMetrics:
    if _eval_backend() == "agentevals":
        run_detail = report.get("run_detail")
        if not isinstance(run_detail, dict):
            run_detail = report
        return normalize_from_agentevals(
            agent_id=agent_id,
            run_detail=run_detail,
            baseline_score=baseline_score,
            skill_bundle_version=skill_bundle_version,
            model_checkpoint_id=model_checkpoint_id,
            split=split,
        )
    return normalize_from_mock_eval(
        agent_id=agent_id,
        eval_summary=eval_summary,
        report=report,
        baseline_score=baseline_score,
        skill_bundle_version=skill_bundle_version,
        model_checkpoint_id=model_checkpoint_id,
        split=split,
    )


def record_eval(
    coaching_root: Path,
    *,
    agent_id: str,
    candidate: str,
    baseline: str,
    skill_bundle_version: str = "unknown",
    split: str = "canary",
    baseline_score: float | None = None,
) -> EvalMetrics:
    coaching_root = coaching_root.resolve()
    client = _build_client(coaching_root)
    summary = client.evaluate(candidate=candidate, baseline=baseline)
    report = client.eval_report(summary["run_id"])
    metrics = _normalize_eval(
        agent_id=agent_id,
        eval_summary=summary,
        report=report,
        baseline_score=baseline_score,
        skill_bundle_version=skill_bundle_version,
        model_checkpoint_id=candidate,
        split=split,
    )
    append_metrics(metrics_store_path(coaching_root), metrics)
    return metrics


def run_improvement(
    coaching_root: Path,
    run_dir: Path,
    *,
    agent_id: str,
    force_trigger: bool = False,
    thresholds_path: Path | None = None,
    production_candidate: str = "mock-baseline-v0",
    production_baseline: str = "mock-baseline-v0",
    train_pipeline: str = "sft",
    capability: str = "tool_use",
) -> dict[str, Any]:
    coaching_root = coaching_root.resolve()
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    thresholds = load_thresholds(thresholds_path or _default_thresholds_path())
    store = metrics_store_path(coaching_root)

    latest = None
    if store.is_file():
        from .eval_metrics import latest_metrics

        latest = latest_metrics(store, agent_id)

    if not force_trigger:
        if latest is None:
            raise RuntimeError(
                "no eval metrics recorded; run record-eval first or pass --force-trigger"
            )
        drop = check_drop(latest, thresholds)
        if not drop.triggered:
            return {
                "status": "skipped",
                "reason": "no_drop_detected",
                "drop_check": drop.to_dict(),
            }
        trigger_metrics = latest
    else:
        trigger_metrics = latest

    improvement_run_id = f"imp-{uuid.uuid4().hex[:12]}"
    client = _build_client(coaching_root)

    # Baseline eval at run start (current production).
    current_summary = client.evaluate(candidate=production_candidate, baseline=production_baseline)
    current_report = client.eval_report(current_summary["run_id"])
    current_metrics = _normalize_eval(
        agent_id=agent_id,
        eval_summary=current_summary,
        report=current_report,
        baseline_score=trigger_metrics.baseline_score if trigger_metrics else None,
        skill_bundle_version=trigger_metrics.skill_bundle_version if trigger_metrics else "unknown",
        model_checkpoint_id=production_candidate,
        split="canary",
    )
    write_json(run_dir / "current_eval.json", current_metrics.to_dict())

    # Stub collect + curate (M1): seed learning + self-play, reference curated paths.
    client.learn(
        event=f"Improvement run {improvement_run_id}: performance drop detected",
        source="orchestrator",
        capability=capability,
    )
    play = client.self_play(capability=capability, n=_self_play_n())
    curation = play.get("curation") if isinstance(play.get("curation"), dict) else None
    curate_info: dict[str, Any] = {
        "status": "ok" if curation else "stub",
        "self_play": play,
        "train_split": str(coaching_root / ".self-coaching" / "curated" / "train.jsonl"),
        "validation_split": str(coaching_root / ".self-coaching" / "curated" / "validation.jsonl"),
        "holdout_split": str(coaching_root / ".self-coaching" / "curated" / "holdout.jsonl"),
    }
    if curation:
        curate_info["curation"] = curation
    if play.get("suite_id"):
        curate_info["agentevals_suite_id"] = play["suite_id"]
    else:
        curate_info["note"] = "M1 stub when self-play returns no curation/suite_id"
    write_json(run_dir / "data" / "curation.json", curate_info)

    n_cases = int(play.get("count", 0))
    improvement_path = "skill" if n_cases < _min_cases_for_model() else "model"

    skill_version = hashlib.sha256(improvement_run_id.encode()).hexdigest()[:12]
    candidate_ref = production_candidate

    if improvement_path == "skill":
        write_json(
            run_dir / "skills" / "bundle.json",
            {
                "bundle_version": skill_version,
                "status": "stub",
                "note": "M1 records version only; M3 applies git-tagged skill patches",
            },
        )
    else:
        train_result = client.train(pipeline=train_pipeline, base_model=production_candidate)
        candidate_ref = str(train_result.get("candidate", production_candidate))
        write_json(run_dir / "training.json", train_result)

    prev_split = os.environ.get("ORCHESTRATOR_EVAL_SPLIT")
    if _eval_backend() == "agentevals":
        os.environ["ORCHESTRATOR_EVAL_SPLIT"] = "holdout"
    try:
        candidate_summary = client.evaluate(candidate=candidate_ref, baseline=production_baseline)
        candidate_report = client.eval_report(candidate_summary["run_id"])
    finally:
        if prev_split is None:
            os.environ.pop("ORCHESTRATOR_EVAL_SPLIT", None)
        else:
            os.environ["ORCHESTRATOR_EVAL_SPLIT"] = prev_split
    candidate_metrics = _normalize_eval(
        agent_id=agent_id,
        eval_summary=candidate_summary,
        report=candidate_report,
        baseline_score=current_metrics.score,
        skill_bundle_version=skill_version if improvement_path == "skill" else current_metrics.skill_bundle_version,
        model_checkpoint_id=candidate_ref,
        split="holdout",
    )
    write_json(run_dir / "candidate_eval.json", candidate_metrics.to_dict())

    ok, gate_reasons = check_promotion(current_metrics, candidate_metrics, thresholds)
    recommendation = "promote" if ok else "reject"
    decision = {
        "improvement_run_id": improvement_run_id,
        "recommendation": recommendation,
        "promotion_allowed": ok,
        "gate_reasons": gate_reasons,
        "improvement_path": improvement_path,
        "deploy_mode": "dry_run",
    }
    write_json(run_dir / "decision.json", decision)

    deploy_manifest = {
        "improvement_run_id": improvement_run_id,
        "agent_id": agent_id,
        "candidate_ref": candidate_ref,
        "skill_bundle_version": skill_version if improvement_path == "skill" else current_metrics.skill_bundle_version,
        "model_checkpoint_id": candidate_ref,
        "canary_fraction": 0.0,
        "status": "dry_run_only",
        "created_at": _utc_now(),
        "note": "M4 replaces this with a real deploy script",
    }
    write_json(run_dir / "deploy_manifest.json", deploy_manifest)

    manifest = {
        "improvement_run_id": improvement_run_id,
        "agent_id": agent_id,
        "coaching_root": str(coaching_root),
        "run_dir": str(run_dir),
        "created_at": _utc_now(),
        "improvement_path": improvement_path,
        "trigger": "forced" if force_trigger else "drop_detected",
        "decision": recommendation,
    }
    write_json(run_dir / "improvement_run_manifest.json", manifest)

    return {
        "status": "completed",
        "improvement_run_id": improvement_run_id,
        "decision": recommendation,
        "run_dir": str(run_dir),
    }
