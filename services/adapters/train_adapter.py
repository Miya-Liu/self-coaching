# SPDX-License-Identifier: MIT
"""AERL train adapter: mock-compatible train() for the orchestrator."""

from __future__ import annotations

import os
from typing import Any

from .train_mapping import build_create_run_body, map_train_result, resolve_checkpoint
from .trainer_http import TrainerHTTPError
from .trainer_rest_client import RestClient
from .trainer_client import TrainerClient

AERLError = TrainerHTTPError


class AERLTrainAdapter:
    """train() backed by TrainerClient + RestClient (self-tuning-trainer-api-plan §6)."""

    def __init__(
        self,
        client: TrainerClient | Any | None = None,
        *,
        trainer_client: TrainerClient | None = None,
        rest_client: RestClient | None = None,
    ):
        if trainer_client is not None:
            self._training = trainer_client
        elif client is not None:
            self._training = client  # AERLClient or TrainerClient or mock
        else:
            self._training = TrainerClient()
        base_url = getattr(self._training, "base_url", None)
        api_key = getattr(self._training, "api_key", None)
        timeout_s = getattr(self._training, "timeout_s", 30.0)
        self._rest = rest_client or RestClient(base_url, timeout_s=timeout_s, api_key=api_key)
        self._client = self._training  # composite_client health() compat

    def train(
        self,
        *,
        pipeline: str = "sft",
        dataset: str | None = None,
        base_model: str = "mock-base",
        coaching_root: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_agent_id = agent_id or os.environ.get("AGENT_ID") or os.environ.get("LOOP_AGENT_ID")
        body = build_create_run_body(
            pipeline=pipeline,
            base_model=base_model,
            dataset=dataset,
            agent_id=resolved_agent_id,
            coaching_root=coaching_root,
        )
        create: dict[str, Any]
        if hasattr(self._training, "create_training_run"):
            create = self._training.create_training_run(
                pipeline_id=pipeline,
                base_model=base_model,
                dataset_refs=body.get("dataset_refs"),
                agent_id=resolved_agent_id,
                coaching_root=coaching_root,
                hyperparameters=body.get("hyperparameters"),
                rollout=body.get("rollout"),
                reward_spec=body.get("reward_spec"),
                agent_snapshot=body.get("agent_snapshot"),
                labels=body.get("labels"),
                wait=body.get("wait", False),
            )
        else:
            create = self._training.create_run(body)
        run_id = str(create.get("id") or create.get("run_id") or "")
        if not run_id:
            raise AERLError("create_training_run response missing id", body=create)

        if str(create.get("status", "")).lower() == "succeeded":
            run = create
        elif hasattr(self._training, "wait_for_training_run"):
            run = self._training.wait_for_training_run(run_id)
        else:
            run = self._training.wait_for_run(run_id)

        checkpoint = resolve_checkpoint(self._rest, run=run)
        return map_train_result(
            run=run,
            checkpoint=checkpoint,
            coaching_root=coaching_root,
            pipeline=pipeline,
        )
