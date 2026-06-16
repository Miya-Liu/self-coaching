# SPDX-License-Identifier: MIT
"""Map TrainingClient + RestClient responses to loop train() contract."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _truthy_env(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() not in {"0", "false", "no", "off"}


def load_json_env(name: str) -> dict[str, Any] | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    path = Path(raw)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(raw)


def agent_snapshot_from_env() -> dict[str, Any] | None:
    if not _truthy_env("LOOP_TRAIN_AGENT_SNAPSHOT", "true"):
        return None
    snapshot: dict[str, Any] = {}
    for field, env_key in (
        ("registry_version_id", "LOOP_TRAIN_REGISTRY_VERSION_ID"),
        ("memory_version", "LOOP_TRAIN_MEMORY_VERSION"),
        ("skill_bundle_version", "LOOP_TRAIN_SKILL_BUNDLE_VERSION"),
        ("prompt_bundle_version", "LOOP_TRAIN_PROMPT_BUNDLE_VERSION"),
        ("eval_run_id", "LOOP_TRAIN_EVAL_RUN_ID"),
        ("learning_job_id", "LOOP_TRAIN_LEARNING_JOB_ID"),
    ):
        value = os.environ.get(env_key)
        if value:
            snapshot[field] = value
    return snapshot or None


def rollout_from_env() -> dict[str, Any] | None:
    return load_json_env("LOOP_TRAIN_ROLLOUT_CONFIG")


def reward_spec_from_env() -> dict[str, Any] | None:
    return load_json_env("LOOP_TRAIN_REWARD_SPEC")


def build_create_run_body(
    *,
    pipeline: str,
    base_model: str,
    dataset: str | None,
    agent_id: str | None,
    coaching_root: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "pipeline_id": pipeline,
        "base_model": base_model,
        "wait": _truthy_env("LOOP_TRAIN_WAIT", "true"),
    }
    if dataset:
        body["dataset_refs"] = [dataset]
    if agent_id:
        body["agent_id"] = agent_id
    if coaching_root:
        body["coaching_root"] = coaching_root
    snapshot = agent_snapshot_from_env()
    if snapshot:
        body["agent_snapshot"] = snapshot
    if pipeline == "grpo":
        rollout = rollout_from_env()
        if rollout:
            body["rollout"] = rollout
    reward_spec = reward_spec_from_env()
    if reward_spec:
        body["reward_spec"] = reward_spec
    labels: dict[str, Any] = {}
    if os.environ.get("LOOP_TRAIN_SOURCE"):
        labels["source"] = os.environ["LOOP_TRAIN_SOURCE"]
    if os.environ.get("LOOP_CAPABILITY"):
        labels["capability"] = os.environ["LOOP_CAPABILITY"]
    if labels:
        body["labels"] = labels
    return body


def manifest_path(coaching_root: str | Path | None) -> str | None:
    if coaching_root is None:
        return None
    path = Path(coaching_root) / ".self-coaching" / "manifests" / "training_run_manifest.json"
    return str(path) if path.is_file() else None


def resolve_checkpoint(
    rest_client: Any,
    *,
    run: dict[str, Any],
) -> dict[str, Any] | None:
    ckpt_id = run.get("primary_checkpoint_id")
    if ckpt_id:
        try:
            return rest_client.get_checkpoint(str(ckpt_id))
        except Exception:
            pass
    run_id = str(run.get("id") or run.get("training_run_id") or "")
    if not run_id:
        return None
    try:
        listed = rest_client.list_checkpoints(training_run_id=run_id)
    except Exception:
        return None
    checkpoints = listed.get("checkpoints") or []
    if not checkpoints:
        return None
    ckpt_id = str(checkpoints[0].get("id") or "")
    if not ckpt_id:
        return None
    try:
        return rest_client.get_checkpoint(ckpt_id)
    except Exception:
        return None


def map_train_result(
    *,
    run: dict[str, Any],
    checkpoint: dict[str, Any] | None,
    coaching_root: str | Path | None,
    pipeline: str,
) -> dict[str, Any]:
    run_id = str(run.get("id") or run.get("training_run_id") or "")
    candidate = str(
        run.get("candidate_model_id")
        or run.get("candidate")
        or (checkpoint or {}).get("id")
        or run.get("primary_checkpoint_id")
        or f"mock-{pipeline}-candidate-{run_id[-6:]}"
    )
    result: dict[str, Any] = {
        "status": "trained",
        "run_id": run_id,
        "candidate": candidate,
        "candidate_model_id": candidate,
        "manifest": manifest_path(coaching_root),
        "log_file": run.get("log_file"),
        "registry_version_id": run.get("registry_version_id"),
        "metrics": run.get("metrics"),
        "_train_backend": "aerl",
    }
    if run.get("primary_checkpoint_id"):
        result["primary_checkpoint_id"] = run["primary_checkpoint_id"]
    if run.get("trainer"):
        result["trainer"] = run["trainer"]
    if run.get("training_data"):
        result["training_data"] = run["training_data"]
    if run.get("pipeline_config"):
        result["pipeline_config"] = run["pipeline_config"]
    if run.get("agent_snapshot"):
        result["agent_snapshot"] = run["agent_snapshot"]
    if run.get("rollout_summary"):
        result["rollout_summary"] = run["rollout_summary"]
    if checkpoint:
        result["checkpoint"] = checkpoint
        weights = checkpoint.get("weights") or {}
        if weights.get("uri"):
            result["weights_uri"] = weights["uri"]
        if checkpoint.get("id"):
            result["primary_checkpoint_id"] = checkpoint["id"]
    return result
