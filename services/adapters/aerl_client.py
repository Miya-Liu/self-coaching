# SPDX-License-Identifier: MIT
"""Low-level HTTP client for AERL — deprecated alias of TrainingClient (M4.2)."""

from __future__ import annotations

from typing import Any

from .training_client import TrainingClient, TrainerHTTPError

# Backward-compatible error alias
AERLError = TrainerHTTPError


class AERLClient(TrainingClient):
    """Deprecated alias for :class:`TrainingClient`. Prefer ``TrainingClient`` in new code."""

    def create_training_run(  # type: ignore[override]
        self,
        *,
        pipeline_id: str,
        base_model: str,
        dataset_refs: list[str] | None = None,
        agent_id: str | None = None,
        coaching_root: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        return self.create_run_from_fields(
            pipeline_id=pipeline_id,
            base_model=base_model,
            dataset_refs=dataset_refs,
            agent_id=agent_id,
            coaching_root=coaching_root,
            **{k: v for k, v in extra.items() if k in {
                "hyperparameters", "rollout", "reward_spec", "agent_snapshot", "labels", "wait",
            }},
        )
