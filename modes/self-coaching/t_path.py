# SPDX-License-Identifier: MIT
"""T-path evolution: train from buffer, holdout gate, optional promotion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from ._paths import _SC_ROOT  # noqa: F401 — triggers sys.path setup
    from .loop_config import (
        THRESHOLDS_PATH,
        LoopClient,
        LoopConfig,
        batch_size_threshold,
    )
    from .loop_store import LoopStore, read_jsonl
    from .self_questioning_factory import run_batch_self_questioning
    from .state import LoopState
except ImportError:
    from _paths import _SC_ROOT  # noqa: F401
    from loop_config import (
        THRESHOLDS_PATH,
        LoopClient,
        LoopConfig,
        batch_size_threshold,
    )
    from loop_store import LoopStore, read_jsonl
    from self_questioning_factory import run_batch_self_questioning
    from state import LoopState


def fill_buffer_batch(
    *,
    coaching_root: Path,
    loop_store: LoopStore,
    registry: Any,
    agent_id: str,
    generation: int,
    n: int,
    capability: str = "tool_use",
    self_questioning_engine: Any | None = None,
    config: LoopConfig | None = None,
) -> dict[str, Any]:
    """C07: top up tuning buffer B via batch self-questioning."""
    if n <= 0:
        return {"status": "skipped", "count": 0}

    version_id = str(registry.get_agent(agent_id)["active_version_id"])
    result = run_batch_self_questioning(
        coaching_root=coaching_root,
        capability=capability,
        n=n,
        config=config,
        engine=self_questioning_engine,
    )

    staging = coaching_root / ".self-coaching" / "curated" / "staging.jsonl"
    # Pipeline backend: remote data stays in Supabase; only proceed signal matters.
    if not result.get("pipeline_service"):
        for traj in read_jsonl(staging):
            loop_store.append_buffer_from_trajectory(
                traj,
                generation=generation,
                version_id=version_id,
            )
    return result


def _holdout_metrics(
    holdout_engine: Any,
    *,
    agent_id: str,
    version_id: str,
    coaching_root: Path,
) -> Any:
    from services.adapters.holdout_engine import collect_holdout_metrics

    return collect_holdout_metrics(
        holdout_engine,
        agent_id=agent_id,
        version_id=version_id,
        coaching_root=coaching_root,
    )


def run_t_path(
    *,
    client: LoopClient,
    registry: Any,
    loop_store: LoopStore,
    state: LoopState,
    coaching_root: Path,
    agent_id: str,
    beta: int | None = None,
    pipeline: str = "sft",
    candidate_model_id: str | None = None,
    self_questioning_engine: Any | None = None,
    agentevals_engine: Any | None = None,
    config: LoopConfig | None = None,
) -> dict[str, Any] | None:
    """T-path: fill B, train, holdout gate, optional hot-swap, consume B."""
    from services.adapters.holdout_engine import build_holdout_engine
    from services.orchestrator.drop_detector import check_promotion, load_thresholds

    from services.adapters.step_log import step_log

    batch_size = beta if beta is not None else batch_size_threshold()
    active_rows = loop_store.active_buffer_rows()
    step_log("t-path", f"buffer B: {len(active_rows)} active row(s), beta={batch_size}")
    batch_fill: dict[str, Any] | None = None
    if len(active_rows) < batch_size:
        need = batch_size - len(active_rows)
        step_log("t-path", f"C07 batch self-questioning: requesting n={need} from pipeline")
        batch_fill = fill_buffer_batch(
            coaching_root=coaching_root,
            loop_store=loop_store,
            registry=registry,
            agent_id=agent_id,
            generation=state.generation,
            n=batch_size - len(active_rows),
            self_questioning_engine=self_questioning_engine,
            config=config,
        )
        if batch_fill:
            step_log(
                "t-path",
                "C07 complete:"
                f" proceed={batch_fill.get('proceed')}"
                f" job_id={batch_fill.get('job_id') or batch_fill.get('suite_id') or 'n/a'}",
            )
        if batch_fill.get("pipeline_service") and not batch_fill.get("proceed"):
            run_dir = coaching_root / ".self-coaching" / "loop" / "runs" / "t_path"
            run_dir.mkdir(parents=True, exist_ok=True)
            held = {
                "promoted": False,
                "held": True,
                "gate_reasons": ["batch_self_questioning_failed"],
                "batch_fill": batch_fill,
                "run_dir": str(run_dir),
            }
            from services.orchestrator.eval_metrics import write_json

            write_json(coaching_root / ".self-coaching" / "loop" / "t_path_last.json", held)
            return held
        active_rows = loop_store.active_buffer_rows()

    pipeline_batch_ok = (
        batch_fill is not None
        and batch_fill.get("pipeline_service")
        and batch_fill.get("proceed")
    )
    if len(active_rows) < batch_size and not pipeline_batch_ok:
        return None

    production_version = str(registry.get_agent(agent_id)["active_version_id"])
    production_version_doc = registry.get_version(agent_id, production_version)
    base_model = str((production_version_doc.get("components") or {}).get("model_id", "mock-base"))

    dataset_path = loop_store.export_train_dataset(active_rows)
    step_log(
        "t-path",
        f"CLI train: dispatching remote job (pipeline={pipeline!r}, dataset_rows={len(active_rows)})",
    )
    train_result = client.train(pipeline=pipeline, dataset=str(dataset_path), base_model=base_model)
    step_log(
        "t-path",
        "CLI train complete:"
        f" status={train_result.get('terminal_status') or train_result.get('status')}"
        f" candidate={train_result.get('candidate') or train_result.get('candidate_model_id')}",
    )
    trained_model = candidate_model_id or str(train_result.get("candidate") or "mock-sft-candidate")

    draft = registry.create_version(
        agent_id,
        parent_version_id=production_version,
        components={"model_id": trained_model},
        artifacts={"training_run_id": train_result.get("run_id")},
        source="mock_aerl",
    )
    candidate_version_id = str(draft["version_id"])

    eval_engine = agentevals_engine or build_holdout_engine(coaching_root)
    step_log("t-path", "AgentEvals holdout: evaluating production baseline")
    current_metrics = _holdout_metrics(
        eval_engine,
        agent_id=agent_id,
        version_id=production_version,
        coaching_root=coaching_root,
    )
    step_log("t-path", f"AgentEvals holdout: evaluating candidate version {candidate_version_id}")
    candidate_metrics = _holdout_metrics(
        eval_engine,
        agent_id=agent_id,
        version_id=candidate_version_id,
        coaching_root=coaching_root,
    )

    thresholds = load_thresholds(THRESHOLDS_PATH)
    ok, gate_reasons = check_promotion(current_metrics, candidate_metrics, thresholds)
    step_log(
        "t-path",
        f"holdout gate: {'promote' if ok else 'reject'} — reasons={gate_reasons or []}",
    )

    consumed = 0
    if ok:
        registry.activate(agent_id, candidate_version_id)
        consumed = loop_store.mark_buffer_consumed(
            task_ids={str(row.get("task_id")) for row in active_rows},
        )

    from services.orchestrator.eval_metrics import write_json

    run_dir = coaching_root / ".self-coaching" / "loop" / "runs" / "t_path"
    run_dir.mkdir(parents=True, exist_ok=True)
    current_eval = current_metrics.to_dict()
    candidate_eval = candidate_metrics.to_dict()
    decision = {
        "recommendation": "promote" if ok else "reject",
        "promotion_allowed": ok,
        "gate_reasons": gate_reasons,
        "deploy_mode": "dry_run",
    }
    write_json(run_dir / "current_eval.json", current_eval)
    write_json(run_dir / "candidate_eval.json", candidate_eval)
    write_json(run_dir / "decision.json", decision)
    write_json(run_dir / "training.json", train_result)
    write_json(
        run_dir / "deploy_manifest.json",
        {
            "agent_id": agent_id,
            "candidate_version_id": candidate_version_id,
            "production_version_id": production_version,
            "canary_fraction": 0.0,
            "status": "dry_run_only" if ok else "rejected",
        },
    )

    t_path_summary = {
        "promoted": ok,
        "gate_reasons": gate_reasons,
        "train_result": train_result,
        "candidate_version_id": candidate_version_id,
        "production_version_id": production_version,
        "current_eval": current_eval,
        "candidate_eval": candidate_eval,
        "buffer_consumed": consumed,
        "buffer_preserved": not ok,
        "batch_fill": batch_fill,
        "run_dir": str(run_dir),
    }
    write_json(coaching_root / ".self-coaching" / "loop" / "t_path_last.json", t_path_summary)

    return t_path_summary
