# SPDX-License-Identifier: MIT
"""AERL train adapter: mock-compatible train() for the orchestrator."""

from __future__ import annotations

import os
from typing import Any

from .aerl_client import AERLClient, AERLError


class AERLTrainAdapter:
    """train() backed by AERL async training runs."""

    def __init__(self, client: AERLClient | None = None):
        self._client = client or AERLClient()

    def train(
        self,
        *,
        pipeline: str = "sft",
        dataset: str | None = None,
        base_model: str = "mock-base",
        coaching_root: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_agent_id = agent_id or os.environ.get("AGENT_ID")
        dataset_refs = [dataset] if dataset else None
        created = self._client.create_training_run(
            pipeline_id=pipeline,
            base_model=base_model,
            dataset_refs=dataset_refs,
            agent_id=resolved_agent_id,
            coaching_root=coaching_root,
        )
        run_id = str(created.get("id") or created.get("run_id") or "")
        if not run_id:
            raise AERLError("create_training_run response missing id", body=created)
        detail = self._client.wait_for_training_run(run_id)
        candidate = str(
            detail.get("candidate_model_id")
            or detail.get("candidate")
            or f"mock-{pipeline}-candidate-{run_id[-6:]}"
        )
        return {
            "status": "trained",
            "run_id": run_id,
            "candidate": candidate,
            "candidate_model_id": candidate,
            "manifest": None,
            "log_file": detail.get("log_file"),
            "registry_version_id": detail.get("registry_version_id"),
            "metrics": detail.get("metrics"),
            "_train_backend": "aerl",
        }
