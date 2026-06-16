#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Mock AERL trainer — production-shaped TrainingClient + RestClient shims.

Implements self-tuning-trainer-api-plan.md §8 (sliced M4.1):
  Slice 1 — job lifecycle, validation, phased runs, metrics
  Slice 2 — checkpoints with mock:// URIs; empty processes list

CLI:
  python mock_aerl.py serve --data-dir ./demo-stack --port 8004
  python mock_aerl.py run --data-dir ./demo-stack --pipeline sft --base-model mock-base
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import http.server
import json
import math
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

try:
    from mock_agent_registry import AgentRegistry
except ImportError:  # pragma: no cover
    from .mock_agent_registry import AgentRegistry

VERSION = "0.2.0"
UTC = _dt.timezone.utc
PIPELINES = frozenset({"sft", "grpo"})
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "canceled"})
PHASE_SLEEP_S = 0.012

PIPELINE_META: dict[str, dict[str, Any]] = {
    "sft": {
        "title": "Supervised fine-tuning",
        "requires_rollout": False,
        "supported_reward_types": ["sft"],
        "loss_type": "cross_entropy",
        "phases": ["queued", "data_prep", "train", "checkpoint", "done"],
    },
    "grpo": {
        "title": "GRPO",
        "requires_rollout": True,
        "supported_reward_types": ["preference", "trajectory_reward"],
        "loss_type": "grpo",
        "phases": ["queued", "data_prep", "rollout", "train", "checkpoint", "done"],
    },
}

REWARD_SCHEMA = {
    "current_version": "reward.ic.v1",
    "supported_versions": ["reward.ic.v1"],
    "record_types": ["sft", "preference", "trajectory_reward"],
    "component_functions": ["length_penalty_v1", "tool_error_penalty_v1"],
}


def _now() -> str:
    return _dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_now() -> str:
    return _dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return f"{prefix}-{hashlib.sha1(raw).hexdigest()[:10]}"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_seed(run_id: str) -> int:
    return int(hashlib.sha1(run_id.encode()).hexdigest()[:8], 16)


class MockAERLEngine:
    """Deterministic mock AERL trainer with phased async runs and checkpoint store."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.registry = AgentRegistry(self.data_dir)
        self._runs_dir = self.data_dir / "aerl" / "runs"
        self._logs_dir = self.data_dir / "aerl" / "logs"
        self._checkpoints_dir = self.data_dir / "aerl" / "checkpoints"
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._active_runs = 0

    def _run_path(self, run_id: str) -> Path:
        return self._runs_dir / f"{run_id}.json"

    def _checkpoint_path(self, checkpoint_id: str) -> Path:
        return self._checkpoints_dir / f"{checkpoint_id}.json"

    def _save_run(self, run: dict[str, Any]) -> None:
        with self._lock:
            self._save_run_unlocked(run)

    def _load_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return self._load_run_unlocked(run_id)

    def _save_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        self._checkpoint_path(str(checkpoint["id"])).write_text(
            json.dumps(checkpoint, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _load_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        path = self._checkpoint_path(checkpoint_id)
        if not path.is_file():
            raise KeyError(f"checkpoint not found: {checkpoint_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _metric_from_records(self, n_records: int) -> float:
        return max(0.01, 1.0 - min(n_records, 10) * 0.05)

    def _resolve_dataset(
        self, dataset_refs: list[str] | None, coaching_root: Path | None
    ) -> tuple[Path | None, int, dict[str, int]]:
        refs = dataset_refs or []
        if not refs and coaching_root is not None:
            candidate = coaching_root / ".self-coaching" / "curated" / "train.jsonl"
            if candidate.is_file():
                refs = [str(candidate)]
        dataset_path: Path | None = None
        n_records = 0
        record_counts: dict[str, int] = {"sft": 0, "preference": 0, "trajectory_reward": 0}
        for ref in refs:
            path = Path(ref)
            if path.is_file():
                dataset_path = path
                rows = read_jsonl(path)
                n_records = len(rows)
                for row in rows:
                    if row.get("_type") == "dataset_header":
                        continue
                    rtype = str(row.get("type") or "sft")
                    record_counts[rtype] = record_counts.get(rtype, 0) + 1
                if sum(record_counts.values()) == 0 and n_records:
                    record_counts["sft"] = n_records
                break
        return dataset_path, n_records, record_counts

    def _trainer_block(self, run: dict[str, Any]) -> dict[str, Any]:
        pipeline_id = str(run.get("pipeline_id") or "sft")
        meta = PIPELINE_META.get(pipeline_id, PIPELINE_META["sft"])
        hparams = run.get("hyperparameters") or {}
        return {
            "algorithm": pipeline_id,
            "pipeline_id": pipeline_id,
            "method": str(hparams.get("method") or "lora"),
            "implementation": f"mock-aerl-{pipeline_id}-v1",
            "loss_type": meta["loss_type"],
        }

    def _training_data_block(self, run: dict[str, Any]) -> dict[str, Any]:
        record_counts = dict(run.get("record_counts") or {})
        if not record_counts:
            record_counts = {"sft": run.get("n_records") or 0}
        reward_version = (run.get("reward_spec") or {}).get("schema_version") or "reward.ic.v1"
        return {
            "dataset_refs": run.get("dataset_refs") or [],
            "record_counts": record_counts,
            "reward_schema_version": reward_version,
        }

    def _pipeline_config_block(self, run: dict[str, Any]) -> dict[str, Any]:
        return {
            "hyperparameters": run.get("hyperparameters") or {},
            "rollout": run.get("rollout"),
            "reward_spec": run.get("reward_spec"),
        }

    def _synthetic_metrics(self, run: dict[str, Any], *, terminal: bool = False) -> dict[str, float]:
        pipeline_id = str(run.get("pipeline_id") or "sft")
        seed = _run_seed(str(run["id"]))
        n_records = int(run.get("n_records") or 0)
        floor = self._metric_from_records(n_records)
        progress = float(run.get("progress_step") or 0)
        total = float(run.get("progress_total") or 100)
        frac = min(1.0, progress / max(total, 1))
        train_loss = max(floor, 1.2 * math.exp(-3.5 * frac) + floor * 0.5)
        val_loss = max(floor, train_loss * (0.92 + (seed % 7) * 0.01))
        metrics: dict[str, float] = {
            "train_loss": round(train_loss, 4),
            "val_loss": round(val_loss, 4),
        }
        if pipeline_id == "grpo":
            reward_mean = round(min(0.95, 0.35 + frac * 0.55 + (seed % 5) * 0.02), 4)
            metrics["reward_mean"] = reward_mean
            if terminal:
                metrics["kl_to_reference"] = round(0.02 + (seed % 3) * 0.01, 4)
        return metrics

    def _metrics_series(self, run: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        total = int(run.get("progress_total") or 100)
        step_stride = max(1, total // 5)
        series: dict[str, list[dict[str, Any]]] = {
            "train_loss": [],
            "val_loss": [],
        }
        pipeline_id = str(run.get("pipeline_id") or "sft")
        if pipeline_id == "grpo":
            series["reward_mean"] = []
        for step in range(0, total + 1, step_stride):
            snapshot = dict(run)
            snapshot["progress_step"] = step
            metrics = self._synthetic_metrics(snapshot)
            epoch = step // max(step_stride, 1)
            series["train_loss"].append({"step": step, "epoch": epoch, "value": metrics["train_loss"]})
            series["val_loss"].append({"step": step, "epoch": epoch, "value": metrics["val_loss"]})
            if "reward_mean" in metrics and "reward_mean" in series:
                series["reward_mean"].append({"step": step, "value": metrics["reward_mean"]})
        return series

    def _build_public_run(self, run: dict[str, Any]) -> dict[str, Any]:
        """TrainingRunRecord (§4.2.1) plus legacy flat fields for backward compat."""
        status = str(run.get("status") or "queued")
        phase = run.get("phase") or "queued"
        pipeline_id = str(run.get("pipeline_id") or "sft")
        record: dict[str, Any] = {
            "id": run["id"],
            "training_run_id": run["id"],
            "pipeline_id": pipeline_id,
            "status": status,
            "phase": phase,
            "trainer": self._trainer_block(run),
            "base_model": run.get("base_model"),
            "agent_id": run.get("agent_id"),
            "training_data": self._training_data_block(run),
            "pipeline_config": self._pipeline_config_block(run),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "agent_snapshot": run.get("agent_snapshot"),
            "labels": run.get("labels") or {},
            "hyperparameters": run.get("hyperparameters") or {},
            "dataset_refs": run.get("dataset_refs") or [],
            "coaching_root": run.get("coaching_root"),
        }
        if run.get("started_at"):
            record["started_at"] = run["started_at"]
        if run.get("finished_at"):
            record["finished_at"] = run["finished_at"]
        if run.get("duration_ms") is not None:
            record["duration_ms"] = run["duration_ms"]
        if status == "running" or (status not in TERMINAL_STATUSES and phase not in {"queued", "done"}):
            record["progress"] = {
                "epoch": run.get("progress_epoch") or 0,
                "step": run.get("progress_step") or 0,
                "total_steps": run.get("progress_total") or 100,
            }
            if pipeline_id == "grpo":
                record["progress"]["rollouts_completed"] = run.get("rollouts_completed") or 0
                record["progress"]["rollouts_total"] = run.get("rollouts_total") or 0
            partial = run.get("metrics_partial") or self._synthetic_metrics(run)
            record["metrics_partial"] = partial
        if status == "succeeded":
            record["metrics"] = run.get("metrics") or self._synthetic_metrics(run, terminal=True)
            record["primary_checkpoint_id"] = run.get("primary_checkpoint_id")
            record["candidate_model_id"] = run.get("candidate_model_id")
            if run.get("rollout_summary"):
                record["rollout_summary"] = run["rollout_summary"]
            record["log_file"] = run.get("log_file")
            record["registry_version_id"] = run.get("registry_version_id")
        elif status in {"failed", "cancelled", "canceled"}:
            if run.get("error"):
                record["error"] = run["error"]
            record["log_file"] = run.get("log_file")
        return record

    def create_training_run(self, body: dict[str, Any]) -> dict[str, Any]:
        pipeline_id = str(body.get("pipeline_id") or body.get("pipeline") or "sft")
        if pipeline_id not in PIPELINES:
            raise ValueError(f"unsupported pipeline: {pipeline_id}")
        meta = PIPELINE_META[pipeline_id]
        if meta["requires_rollout"] and not body.get("rollout"):
            raise RolloutRequiredError("rollout required for grpo pipeline")

        base_model = str(body.get("base_model") or "mock-base")
        agent_id = str(body.get("agent_id") or "example-agent")
        coaching_root = body.get("coaching_root")
        root = Path(coaching_root) if coaching_root else None
        dataset_refs = body.get("dataset_refs")
        if dataset_refs is None and body.get("dataset"):
            dataset_refs = [str(body["dataset"])]
        if isinstance(dataset_refs, str):
            dataset_refs = [dataset_refs]
        dataset_path, n_records, record_counts = self._resolve_dataset(
            list(dataset_refs) if dataset_refs else None,
            root,
        )

        run_id = f"train-{uuid.uuid4().hex[:12]}"
        created_at = _iso_now()
        total_steps = max(20, min(400, n_records * 10 or 100))
        run: dict[str, Any] = {
            "id": run_id,
            "pipeline_id": pipeline_id,
            "status": "queued",
            "phase": "queued",
            "created_at": created_at,
            "updated_at": created_at,
            "base_model": base_model,
            "agent_id": agent_id,
            "dataset_refs": [str(dataset_path)] if dataset_path else list(dataset_refs or []),
            "coaching_root": str(root) if root else None,
            "agent_snapshot": body.get("agent_snapshot"),
            "labels": body.get("labels") or {},
            "hyperparameters": body.get("hyperparameters") or {},
            "rollout": body.get("rollout"),
            "reward_spec": body.get("reward_spec"),
            "n_records": n_records,
            "record_counts": record_counts,
            "progress_step": 0,
            "progress_epoch": 0,
            "progress_total": total_steps,
            "rollouts_total": total_steps if pipeline_id == "grpo" else 0,
            "rollouts_completed": 0,
            "metrics": None,
            "metrics_partial": None,
            "candidate_model_id": None,
            "primary_checkpoint_id": None,
            "log_file": None,
            "registry_version_id": None,
            "cancel_requested": False,
            "metrics_series": None,
        }
        self._save_run(run)

        with self._lock:
            self._active_runs += 1

        threading.Thread(target=self._run_worker, args=(run_id,), daemon=True).start()
        return {
            "id": run_id,
            "pipeline_id": pipeline_id,
            "status": "queued",
            "created_at": created_at,
            "updated_at": created_at,
            "poll_url": f"/v1/training/runs/{run_id}",
        }

    def _run_worker(self, run_id: str) -> None:
        try:
            run = self._load_run(run_id)
            if run.get("cancel_requested") or str(run.get("status") or "").lower() == "cancelled":
                return
            pipeline_id = str(run["pipeline_id"])
            meta = PIPELINE_META[pipeline_id]
            phases = [p for p in meta["phases"] if p != "queued"]
            started_at = _iso_now()
            run["status"] = "running"
            run["started_at"] = started_at
            run["updated_at"] = started_at
            self._save_run(run)

            for phase in phases:
                run = self._load_run(run_id)
                if run.get("cancel_requested"):
                    run["status"] = "cancelled"
                    run["phase"] = phase
                    run["updated_at"] = _iso_now()
                    run["finished_at"] = run["updated_at"]
                    self._save_run(run)
                    return

                run["phase"] = phase
                run["updated_at"] = _iso_now()
                if phase == "rollout" and pipeline_id == "grpo":
                    total = int(run.get("rollouts_total") or 100)
                    run["rollouts_completed"] = total
                    run["progress_step"] = total // 2
                elif phase == "train":
                    run["progress_step"] = int(run.get("progress_total") or 100) - 1
                    run["metrics_partial"] = self._synthetic_metrics(run)
                elif phase == "checkpoint":
                    run["progress_step"] = int(run.get("progress_total") or 100)
                self._save_run(run)
                time.sleep(PHASE_SLEEP_S)

            with self._lock:
                run = self._load_run_unlocked(run_id)
                if run.get("cancel_requested") or str(run.get("status") or "").lower() == "cancelled":
                    return

                n_records = int(run.get("n_records") or 0)
                metric = self._metric_from_records(n_records)
                suffix = run_id[-6:]
                candidate = f"mock-{pipeline_id}-candidate-{suffix}"
                checkpoint_id = f"ckpt-{pipeline_id}-{suffix}"
                log_file = self._logs_dir / f"{run_id}.log"
                log_file.write_text(
                    "mock AERL training started\n"
                    f"pipeline={pipeline_id}\nbase_model={run.get('base_model')}\n"
                    f"records={n_records}\nmetric.val_loss={metric:.4f}\n"
                    "mock AERL training complete\n",
                    encoding="utf-8",
                )

                registry_version_id: str | None = None
                agent_id = str(run.get("agent_id") or "example-agent")
                try:
                    self.registry.ensure_agent(agent_id)
                    version = self.registry.create_version(
                        agent_id,
                        components={"model_id": candidate},
                        artifacts={"training_run_id": run_id, "checkpoint_id": checkpoint_id},
                        source="mock_aerl",
                    )
                    registry_version_id = str(version["version_id"])
                except Exception:
                    registry_version_id = None

                root = Path(run["coaching_root"]) if run.get("coaching_root") else None
                if root is not None:
                    manifests = root / ".self-coaching" / "manifests"
                    manifests.mkdir(parents=True, exist_ok=True)
                    terminal_metrics = self._synthetic_metrics(
                        {**run, "progress_step": run.get("progress_total")}, terminal=True
                    )
                    manifest = {
                        "run_id": run_id,
                        "timestamp": _now(),
                        "pipeline_id": pipeline_id,
                        "dataset_refs": run["dataset_refs"],
                        "base_model": run.get("base_model"),
                        "candidate": candidate,
                        "candidate_model_id": candidate,
                        "primary_checkpoint_id": checkpoint_id,
                        "method": pipeline_id,
                        "hyperparameters": run.get("hyperparameters") or {"epochs": 1, "learning_rate": 1e-5},
                        "agent_snapshot": run.get("agent_snapshot"),
                        "labels": run.get("labels") or {},
                        "log_file": str(log_file),
                        "metrics": terminal_metrics,
                        "rollback_target": run.get("base_model"),
                        "eval_run_id": (run.get("agent_snapshot") or {}).get("eval_run_id"),
                        "registry_version_id": registry_version_id,
                    }
                    if pipeline_id == "grpo" and run.get("rollout"):
                        manifest["rollout_summary"] = run.get("rollout_summary")
                    write_json(manifests / "training_run_manifest.json", manifest)

                weights_uri = f"mock://{run_id}/weights/{checkpoint_id}"
                checkpoint = {
                    "id": checkpoint_id,
                    "training_run_id": run_id,
                    "base_model": run.get("base_model"),
                    "trainer": self._trainer_block(run),
                    "step": int(run.get("progress_total") or 100),
                    "epoch": 1,
                    "metrics": self._synthetic_metrics(
                        {**run, "progress_step": run.get("progress_total")}, terminal=True
                    ),
                    "format": "safetensors",
                    "size_bytes": 142000000,
                    "status": "available",
                    "created_at": _iso_now(),
                    "agent_snapshot": run.get("agent_snapshot"),
                    "weights": {
                        "format": "safetensors",
                        "uri": weights_uri,
                        "shard_uris": [
                            f"{weights_uri}-00001-of-00002",
                            f"{weights_uri}-00002-of-00002",
                        ],
                        "shard_count": 2,
                        "size_bytes": 142000000,
                        "adapter_only": True,
                        "merged": False,
                    },
                }
                self._save_checkpoint(checkpoint)

                rollout_summary = None
                if pipeline_id == "grpo":
                    seed = _run_seed(run_id)
                    rollout_summary = {
                        "proxy_base_url": (run.get("rollout") or {}).get("llm_proxy", {}).get("base_url"),
                        "total_rollout_calls": 128 + seed % 64,
                        "total_tokens": {"input": 240000 + seed % 10000, "output": 89000 + seed % 5000},
                    }

                finished_at = _iso_now()
                started = run.get("started_at") or finished_at
                try:
                    start_dt = _dt.datetime.fromisoformat(started.replace("Z", "+00:00"))
                    end_dt = _dt.datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                    duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
                except ValueError:
                    duration_ms = 0

                run = self._load_run_unlocked(run_id)
                if run.get("cancel_requested") or str(run.get("status") or "").lower() == "cancelled":
                    return

                run["status"] = "succeeded"
                run["phase"] = "done"
                run["updated_at"] = finished_at
                run["finished_at"] = finished_at
                run["duration_ms"] = duration_ms
                run["metrics"] = checkpoint["metrics"]
                run["metrics_partial"] = checkpoint["metrics"]
                run["candidate_model_id"] = candidate
                run["primary_checkpoint_id"] = checkpoint_id
                run["log_file"] = str(log_file)
                run["registry_version_id"] = registry_version_id
                run["rollout_summary"] = rollout_summary
                run["metrics_series"] = self._metrics_series(run)
                self._save_run_unlocked(run)
        finally:
            with self._lock:
                self._active_runs = max(0, self._active_runs - 1)

    def get_training_run(self, run_id: str) -> dict[str, Any]:
        return self._build_public_run(self._load_run(run_id))

    def get_training_metrics(self, run_id: str) -> dict[str, Any]:
        run = self._load_run(run_id)
        if str(run.get("status") or "queued") == "queued" and run.get("phase") == "queued":
            raise MetricsNotReadyError("metrics not ready for queued run")
        series = run.get("metrics_series") or self._metrics_series(run)
        complete = str(run.get("status") or "") in TERMINAL_STATUSES
        return {
            "training_run_id": run_id,
            "series": series,
            "last_step": int(run.get("progress_step") or 0),
            "complete": complete,
        }

    def cancel_training_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._load_run_unlocked(run_id)
            status = str(run.get("status") or "").lower()
            if status in TERMINAL_STATUSES:
                raise NotCancellableError("run already terminal")
            cancelled_at = _iso_now()
            run["cancel_requested"] = True
            run["status"] = "cancelled"
            run["updated_at"] = cancelled_at
            run["finished_at"] = cancelled_at
            self._save_run_unlocked(run)
        return {
            "id": run_id,
            "status": "cancelled",
            "cancelled_at": cancelled_at,
        }

    def _load_run_unlocked(self, run_id: str) -> dict[str, Any]:
        path = self._run_path(run_id)
        if not path.is_file():
            raise KeyError(f"training run not found: {run_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_run_unlocked(self, run: dict[str, Any]) -> None:
        path = self._run_path(str(run["id"]))
        payload = json.dumps(run, indent=2, sort_keys=True) + "\n"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)

    def list_training_runs(
        self,
        *,
        agent_id: str | None = None,
        pipeline_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        runs: list[dict[str, Any]] = []
        for path in sorted(self._runs_dir.glob("*.json"), reverse=True):
            run = json.loads(path.read_text(encoding="utf-8"))
            if agent_id and str(run.get("agent_id")) != agent_id:
                continue
            if pipeline_id and str(run.get("pipeline_id")) != pipeline_id:
                continue
            if status and str(run.get("status")) != status:
                continue
            runs.append(
                {
                    "id": run["id"],
                    "pipeline_id": run.get("pipeline_id"),
                    "status": run.get("status"),
                    "created_at": run.get("created_at"),
                    "candidate_model_id": run.get("candidate_model_id"),
                }
            )
            if len(runs) >= limit:
                break
        return {"runs": runs, "next_cursor": None}

    def list_pipelines(self) -> dict[str, Any]:
        pipelines = []
        for pid, meta in PIPELINE_META.items():
            pipelines.append(
                {
                    "id": pid,
                    "title": meta["title"],
                    "requires_rollout": meta["requires_rollout"],
                    "supported_reward_types": meta["supported_reward_types"],
                }
            )
        return {"pipelines": pipelines}

    def validate_rollout(self, body: dict[str, Any]) -> dict[str, Any]:
        llm_proxy = body.get("llm_proxy") or (body.get("rollout") or {}).get("llm_proxy") or body
        base_url = str(llm_proxy.get("base_url") or "")
        checks: list[dict[str, Any]] = []
        ok = bool(base_url) and "invalid" not in base_url.lower()
        checks.append({"name": "proxy_health", "ok": ok, "latency_ms": 42 if ok else None})
        checks.append({"name": "policy_model_route", "ok": ok})
        checks.append({"name": "reference_model_route", "ok": ok})
        return {"valid": ok, "checks": checks}

    def validate_rewards(self, body: dict[str, Any]) -> dict[str, Any]:
        refs = body.get("dataset_refs") or []
        if isinstance(refs, str):
            refs = [refs]
        reward_spec = body.get("reward_spec") or {}
        schema_version = str(reward_spec.get("schema_version") or "reward.ic.v1")
        record_counts: dict[str, int] = {"sft": 0, "preference": 0, "trajectory_reward": 0}
        warnings: list[dict[str, Any]] = []
        for ref in refs:
            path = Path(str(ref))
            if not path.is_file():
                return {
                    "valid": False,
                    "error": f"dataset not found: {ref}",
                    "record_counts": record_counts,
                }
            for line_no, row in enumerate(read_jsonl(path), start=1):
                if row.get("_type") == "dataset_header":
                    header_version = str(row.get("reward_schema_version") or schema_version)
                    if header_version != schema_version:
                        return {
                            "valid": False,
                            "error": "reward_schema_mismatch",
                            "record_counts": record_counts,
                        }
                    continue
                rtype = str(row.get("type") or "sft")
                record_counts[rtype] = record_counts.get(rtype, 0) + 1
                if rtype == "preference" and not row.get("rewards", {}).get("human"):
                    warnings.append(
                        {
                            "line": line_no,
                            "code": "missing_human_review",
                            "message": "human_reviewed=false",
                        }
                    )
        return {"valid": True, "record_counts": record_counts, "warnings": warnings}

    def get_rewards_schema(self) -> dict[str, Any]:
        return dict(REWARD_SCHEMA)

    def health(self) -> dict[str, Any]:
        queued = 0
        for path in self._runs_dir.glob("*.json"):
            run = json.loads(path.read_text(encoding="utf-8"))
            if str(run.get("status")) == "queued":
                queued += 1
        return {
            "status": "ok",
            "version": VERSION,
            "data_dir": str(self.data_dir),
            "gpu_available": True,
            "queue_depth": queued,
            "active_runs": self._active_runs,
            "supported_pipelines": sorted(PIPELINES),
        }

    def list_checkpoints(
        self,
        *,
        training_run_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        checkpoints: list[dict[str, Any]] = []
        for path in sorted(self._checkpoints_dir.glob("*.json"), reverse=True):
            ckpt = json.loads(path.read_text(encoding="utf-8"))
            if training_run_id and str(ckpt.get("training_run_id")) != training_run_id:
                continue
            checkpoints.append(
                {
                    "id": ckpt["id"],
                    "training_run_id": ckpt.get("training_run_id"),
                    "base_model": ckpt.get("base_model"),
                    "trainer": ckpt.get("trainer"),
                    "step": ckpt.get("step"),
                    "epoch": ckpt.get("epoch"),
                    "metrics": ckpt.get("metrics"),
                    "format": ckpt.get("format"),
                    "size_bytes": ckpt.get("size_bytes"),
                    "status": ckpt.get("status"),
                    "created_at": ckpt.get("created_at"),
                }
            )
            if len(checkpoints) >= limit:
                break
        return {"checkpoints": checkpoints, "next_cursor": None}

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        return self._load_checkpoint(checkpoint_id)

    def list_processes(self) -> dict[str, Any]:
        return {"processes": []}

    def run_pipeline_argv(self, pipeline_id: str, argv: list[str]) -> tuple[str, str | None]:
        if pipeline_id not in PIPELINES:
            raise ValueError(f"unsupported pipeline: {pipeline_id}")
        digest = hashlib.sha1(json.dumps(argv, sort_keys=True).encode()).hexdigest()[:8]
        metric = 0.42 + (len(argv) % 5) * 0.02
        run_id = f"train-argv-{digest}"
        log = (
            f"mock AERL pipeline={pipeline_id}\n"
            f"argv={json.dumps(argv)}\n"
            f"run_token={digest}\n"
            f"run_id={run_id}\n"
            f"metric.val_loss={metric:.4f}\n"
            "mock AERL pipeline complete\n"
        )
        return log, run_id


class RolloutRequiredError(ValueError):
    def __init__(self, message: str = "rollout required"):
        super().__init__(message)
        self.code = "rollout_required"


class MetricsNotReadyError(ValueError):
    def __init__(self, message: str = "metrics not ready"):
        super().__init__(message)
        self.code = "metrics_not_ready"


class NotCancellableError(ValueError):
    def __init__(self, message: str = "not cancellable"):
        super().__init__(message)
        self.code = "not_cancellable"


def train_via_http(
    base_url: str,
    *,
    coaching_root: Path,
    pipeline: str = "sft",
    dataset: str | None = None,
    base_model: str = "mock-base",
    agent_id: str | None = None,
    poll_timeout_s: float = 60.0,
    poll_interval_s: float = 0.1,
) -> dict[str, Any]:
    """Call mock AERL /v1/training/runs and return coaching-compatible train result."""
    body: dict[str, Any] = {
        "pipeline_id": pipeline,
        "base_model": base_model,
        "coaching_root": str(coaching_root),
        "agent_id": agent_id or "example-agent",
    }
    if dataset:
        body["dataset_refs"] = [dataset]
    created = _http_json("POST", f"{base_url.rstrip('/')}/v1/training/runs", body)
    run_id = str(created.get("id") or "")
    if not run_id:
        raise RuntimeError(f"AERL create run missing id: {created}")

    deadline = time.time() + poll_timeout_s
    detail: dict[str, Any] = created
    while time.time() < deadline:
        detail = _http_json("GET", f"{base_url.rstrip('/')}/v1/training/runs/{run_id}")
        status = str(detail.get("status", "")).lower()
        if status in TERMINAL_STATUSES:
            break
        time.sleep(poll_interval_s)
    else:
        raise TimeoutError(f"AERL run {run_id} did not complete within {poll_timeout_s}s")

    if str(detail.get("status", "")).lower() != "succeeded":
        raise RuntimeError(f"AERL run {run_id} ended with status={detail.get('status')!r}")

    candidate = str(detail.get("candidate_model_id") or "")
    manifest_path = coaching_root / ".self-coaching" / "manifests" / "training_run_manifest.json"
    return {
        "status": "trained",
        "run_id": run_id,
        "candidate": candidate,
        "candidate_model_id": candidate,
        "manifest": str(manifest_path) if manifest_path.is_file() else None,
        "log_file": detail.get("log_file"),
        "registry_version_id": detail.get("registry_version_id"),
        "_train_backend": "aerl",
    }


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    from proxyutil import urlopen as _urlopen
    try:
        with _urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            err_body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_body = exc.reason
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {err_body}") from exc


class _AERLHandler(http.server.BaseHTTPRequestHandler):
    server_version = "MockAERL/" + VERSION

    @property
    def engine(self) -> MockAERLEngine:
        return self.server.engine  # type: ignore[attr-defined]

    def _json(self, code: int, obj: object) -> None:
        body = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, code: int, text: str, *, extra_headers: dict[str, str] | None = None) -> None:
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length", "0") or "0")
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _query(self) -> dict[str, str]:
        parsed = urllib.parse.urlparse(self.path)
        return {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = self._query()

        if path == "/health":
            self._json(200, self.engine.health())
            return
        if path == "/v1/pipelines":
            self._json(200, self.engine.list_pipelines())
            return
        if path == "/v1/rewards/schema":
            self._json(200, self.engine.get_rewards_schema())
            return
        if path == "/v1/training/runs":
            self._json(
                200,
                self.engine.list_training_runs(
                    agent_id=q.get("agent_id"),
                    pipeline_id=q.get("pipeline_id"),
                    status=q.get("status"),
                    limit=int(q.get("limit", "50")),
                ),
            )
            return
        if path == "/v1/checkpoints":
            self._json(
                200,
                self.engine.list_checkpoints(training_run_id=q.get("training_run_id")),
            )
            return
        if path == "/v1/processes":
            self._json(200, self.engine.list_processes())
            return

        m = re.fullmatch(r"/v1/training/runs/([^/]+)/metrics", path)
        if m:
            try:
                result = self.engine.get_training_metrics(m.group(1))
            except KeyError as exc:
                self._json(404, {"error": str(exc), "code": "run_not_found"})
                return
            except MetricsNotReadyError as exc:
                self._json(409, {"error": str(exc), "code": exc.code})
                return
            self._json(200, result)
            return

        m = re.fullmatch(r"/v1/training/runs/([^/]+)", path)
        if m:
            try:
                result = self.engine.get_training_run(m.group(1))
            except KeyError as exc:
                self._json(404, {"error": str(exc), "code": "run_not_found"})
                return
            self._json(200, result)
            return

        m = re.fullmatch(r"/v1/checkpoints/([^/]+)", path)
        if m:
            try:
                result = self.engine.get_checkpoint(m.group(1))
            except KeyError as exc:
                self._json(404, {"error": str(exc), "code": "checkpoint_not_found"})
                return
            self._json(200, result)
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path

        if path == "/v1/training/runs":
            try:
                result = self.engine.create_training_run(self._body())
            except RolloutRequiredError as exc:
                self._json(400, {"error": str(exc), "code": exc.code})
                return
            except ValueError as exc:
                self._json(400, {"error": str(exc), "code": "invalid_request"})
                return
            self._json(202, result)
            return

        m = re.fullmatch(r"/v1/training/runs/([^/]+)/cancel", path)
        if m:
            try:
                result = self.engine.cancel_training_run(m.group(1))
            except KeyError as exc:
                self._json(404, {"error": str(exc), "code": "run_not_found"})
                return
            except NotCancellableError as exc:
                self._json(409, {"error": str(exc), "code": exc.code})
                return
            self._json(200, result)
            return

        if path == "/v1/rollout/configs/validate":
            self._json(200, self.engine.validate_rollout(self._body()))
            return
        if path == "/v1/rewards/validate":
            self._json(200, self.engine.validate_rewards(self._body()))
            return

        m = re.fullmatch(r"/v1/pipelines/([^/]+)/run", path)
        if m:
            data = self._body()
            argv = data.get("argv") or []
            if not isinstance(argv, list):
                self._json(400, {"error": "argv must be a list"})
                return
            try:
                log, run_id = self.engine.run_pipeline_argv(m.group(1), [str(a) for a in argv])
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            headers = {"X-Training-Run-Id": run_id} if run_id else None
            self._text(200, log, extra_headers=headers)
            return

        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[mock-aerl] " + fmt % args + "\n")


def serve(data_dir: Path, port: int, host: str = "127.0.0.1") -> None:
    engine = MockAERLEngine(data_dir)
    server = http.server.ThreadingHTTPServer((host, port), _AERLHandler)
    server.engine = engine  # type: ignore[attr-defined]
    print(json.dumps({"status": "serving", "url": f"http://{host}:{port}", "data_dir": str(data_dir)}, indent=2))
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock AERL trainer service")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_data(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data-dir", default="./mock-aerl-data")

    p_run = sub.add_parser("run")
    add_data(p_run)
    p_run.add_argument("--pipeline", default="sft")
    p_run.add_argument("--base-model", default="mock-base")
    p_run.add_argument("--agent-id", default="example-agent")
    p_run.add_argument("--coaching-root")

    p_serve = sub.add_parser("serve")
    add_data(p_serve)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8004)

    args = parser.parse_args(argv)
    engine = MockAERLEngine(args.data_dir)
    if args.cmd == "run":
        body: dict[str, Any] = {
            "pipeline_id": args.pipeline,
            "base_model": args.base_model,
            "agent_id": args.agent_id,
        }
        if args.coaching_root:
            body["coaching_root"] = args.coaching_root
        created = engine.create_training_run(body)
        run_id = str(created["id"])
        deadline = time.time() + 30
        while time.time() < deadline:
            detail = engine.get_training_run(run_id)
            if str(detail.get("status", "")).lower() == "succeeded":
                print(json.dumps(detail, indent=2, sort_keys=True))
                return 0
            time.sleep(0.05)
        raise SystemExit(f"run {run_id} did not finish")
    if args.cmd == "serve":
        serve(Path(args.data_dir), args.port, args.host)
        return 0
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
