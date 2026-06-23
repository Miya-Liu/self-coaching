# SPDX-License-Identifier: MIT
"""Map loop self-questioning semantics to Pipeline Service requests and responses."""

from __future__ import annotations

import os
from typing import Any


def _explore_n(requested: int) -> int:
    cap = int(os.environ.get("PIPELINE_EXPLORE_N_CAP", "8"))
    return max(1, min(requested, cap))


def build_batch_request(
    *,
    n: int,
    capability: str = "tool_use",  # noqa: ARG001 — reserved for future pipeline filters
    train_eval_flag: str | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """C07 batch self-questioning → full pipeline run."""
    flag = train_eval_flag or os.environ.get("PIPELINE_BATCH_TRAIN_EVAL_FLAG", "train")
    explore = _explore_n(n)
    body: dict[str, Any] = {
        "start_stage": 1,
        "generate_tasks_limit": max(1, n),
        "train_eval_flag": flag,
        "n": explore,
        "num_explore_threads": explore,
        "fail_fast": True,
    }
    if dry_run is not None:
        body["dry_run"] = dry_run
    elif os.environ.get("PIPELINE_DRY_RUN", "").strip().lower() in {"1", "true", "yes"}:
        body["dry_run"] = True
    return body


def build_suite_request(
    *,
    n_variants: int,
    train_eval_flag: str | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """C06 sparse self-questioning → pipeline run sized to sigma / variant count."""
    flag = train_eval_flag or os.environ.get("PIPELINE_TRAIN_EVAL_FLAG", "eval")
    limit = max(1, n_variants)
    explore = _explore_n(limit)
    body: dict[str, Any] = {
        "start_stage": 1,
        "generate_tasks_limit": limit,
        "train_eval_flag": flag,
        "n": explore,
        "num_explore_threads": explore,
        "fail_fast": True,
    }
    if dry_run is not None:
        body["dry_run"] = dry_run
    elif os.environ.get("PIPELINE_DRY_RUN", "").strip().lower() in {"1", "true", "yes"}:
        body["dry_run"] = True
    return body


def pipeline_job_succeeded(result: dict[str, Any]) -> bool:
    """Whether the loop should treat self-questioning as complete and move on."""
    if not result.get("pipeline_service"):
        return str(result.get("status", "")).lower() in {"generated", "registered"}
    return bool(result.get("proceed"))


def map_batch_result(
    finished: dict[str, Any],
    *,
    requested_n: int,
) -> dict[str, Any]:
    """Mock-compatible batch result — success signal only (no local data writeback)."""
    stage_results = finished.get("stage_results") or {}
    ok = str(finished.get("status", "")).lower() == "success" and all(
        stage_results.get(str(i)) for i in (1, 2, 3)
    )
    if not ok:
        return {
            "status": "error",
            "error": finished.get("error") or "pipeline stages incomplete",
            "count": 0,
            "job_id": finished.get("job_id"),
            "stage_results": stage_results,
            "pipeline_service": True,
            "proceed": False,
        }
    return {
        "status": "generated",
        "count": requested_n,
        "job_id": finished.get("job_id"),
        "stage_results": stage_results,
        "pipeline_service": True,
        "proceed": True,
    }


def map_suite_result(
    finished: dict[str, Any],
    *,
    requested_n: int,
) -> dict[str, Any]:
    """Mock-compatible sparse suite result — success signal only."""
    stage_results = finished.get("stage_results") or {}
    ok = str(finished.get("status", "")).lower() == "success" and all(
        stage_results.get(str(i)) for i in (1, 2, 3)
    )
    if not ok:
        return {
            "status": "error",
            "error": finished.get("error") or "pipeline stages incomplete",
            "count": 0,
            "job_id": finished.get("job_id"),
            "stage_results": stage_results,
            "pipeline_service": True,
            "proceed": False,
        }
    return {
        "status": "registered",
        "count": requested_n,
        "job_id": finished.get("job_id"),
        "stage_results": stage_results,
        "pipeline_service": True,
        "proceed": True,
    }


def map_pipeline_error(
    exc: Exception,
    *,
    job_id: str | None = None,
    mode: str = "batch",
) -> dict[str, Any]:
    body = getattr(exc, "body", None)
    stage_results: dict[str, Any] = {}
    error_msg = str(exc)
    if isinstance(body, dict):
        job_id = job_id or body.get("job_id")
        stage_results = body.get("stage_results") or {}
        if body.get("error"):
            error_msg = str(body["error"])
    status = "error"
    return {
        "status": status,
        "error": error_msg,
        "count": 0,
        "job_id": job_id,
        "stage_results": stage_results,
        "pipeline_service": True,
        "proceed": False,
        "mode": mode,
    }
