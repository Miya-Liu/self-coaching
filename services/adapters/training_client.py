# SPDX-License-Identifier: MIT
"""TrainingClient — trainer job lifecycle (runs, pipelines, rollout, rewards)."""

from __future__ import annotations

import os
import time
import urllib.parse
from typing import Any

from .trainer_http import TrainerHTTPBase, TrainerHTTPError


class TrainingClient(TrainerHTTPBase):
    """HTTP client for TrainingClient routes (self-tuning-trainer-api-plan §4.0–§4.12)."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_s: float = 30.0,
        poll_interval_s: float | None = None,
        poll_timeout_s: float | None = None,
        api_key: str | None = None,
    ):
        super().__init__(base_url, timeout_s=timeout_s, api_key=api_key)
        self.poll_interval_s = float(
            poll_interval_s if poll_interval_s is not None
            else os.environ.get("AERL_POLL_INTERVAL_S", "2")
        )
        self.poll_timeout_s = float(
            poll_timeout_s if poll_timeout_s is not None
            else os.environ.get("AERL_TIMEOUT_S", "3600")
        )

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def create_run(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/training/runs", body)

    def create_run_from_fields(
        self,
        *,
        pipeline_id: str,
        base_model: str,
        dataset_refs: list[str] | None = None,
        agent_id: str | None = None,
        coaching_root: str | None = None,
        hyperparameters: dict[str, Any] | None = None,
        rollout: dict[str, Any] | None = None,
        reward_spec: dict[str, Any] | None = None,
        agent_snapshot: dict[str, Any] | None = None,
        labels: dict[str, Any] | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "pipeline_id": pipeline_id,
            "base_model": base_model,
            "wait": wait,
        }
        if dataset_refs:
            body["dataset_refs"] = dataset_refs
        if agent_id:
            body["agent_id"] = agent_id
        if coaching_root:
            body["coaching_root"] = coaching_root
        if hyperparameters:
            body["hyperparameters"] = hyperparameters
        if rollout:
            body["rollout"] = rollout
        if reward_spec:
            body["reward_spec"] = reward_spec
        if agent_snapshot:
            body["agent_snapshot"] = agent_snapshot
        if labels:
            body["labels"] = labels
        return self.create_run(body)

    def get_run(self, training_run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/training/runs/{training_run_id}")

    def wait_for_run(self, training_run_id: str) -> dict[str, Any]:
        deadline = time.time() + self.poll_timeout_s
        terminal = {"succeeded", "failed", "cancelled", "canceled"}
        last: dict[str, Any] | None = None
        while time.time() < deadline:
            last = self.get_run(training_run_id)
            status = str(last.get("status", "")).lower()
            if status in terminal:
                if status != "succeeded":
                    raise TrainerHTTPError(
                        f"training run {training_run_id} ended with status={status!r}",
                        body=last,
                    )
                return last
            time.sleep(self.poll_interval_s)
        raise TrainerHTTPError(
            f"training run {training_run_id} did not complete within {self.poll_timeout_s}s",
            body=last,
        )

    def cancel_run(self, training_run_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/training/runs/{training_run_id}/cancel")

    def list_runs(
        self,
        *,
        agent_id: str | None = None,
        pipeline_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"limit": str(limit)}
        if agent_id:
            params["agent_id"] = agent_id
        if pipeline_id:
            params["pipeline_id"] = pipeline_id
        if status:
            params["status"] = status
        query = urllib.parse.urlencode(params)
        return self._request("GET", f"/v1/training/runs?{query}")

    def get_metrics(
        self,
        training_run_id: str,
        *,
        series: list[str] | None = None,
        downsample: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if series:
            params["series"] = ",".join(series)
        if downsample is not None:
            params["downsample"] = str(downsample)
        suffix = f"?{urllib.parse.urlencode(params)}" if params else ""
        return self._request("GET", f"/v1/training/runs/{training_run_id}/metrics{suffix}")

    def list_pipelines(self) -> dict[str, Any]:
        return self._request("GET", "/v1/pipelines")

    def validate_rollout(self, rollout: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/rollout/configs/validate", rollout)

    def validate_rewards(
        self,
        *,
        dataset_refs: list[str],
        reward_spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"dataset_refs": dataset_refs}
        if reward_spec:
            body["reward_spec"] = reward_spec
        return self._request("POST", "/v1/rewards/validate", body)

    def rewards_schema(self) -> dict[str, Any]:
        return self._request("GET", "/v1/rewards/schema")

    def run_pipeline_argv(self, pipeline_id: str, argv: list[str]) -> str:
        return self._request_text(
            "POST",
            f"/v1/pipelines/{pipeline_id}/run",
            {"argv": argv},
        )

    # Backward-compatible aliases (AERLClient surface)
    def create_training_run(self, **kwargs: Any) -> dict[str, Any]:
        return self.create_run_from_fields(**kwargs)

    def get_training_run(self, run_id: str) -> dict[str, Any]:
        return self.get_run(run_id)

    def wait_for_training_run(self, run_id: str) -> dict[str, Any]:
        return self.wait_for_run(run_id)


__all__ = ["TrainingClient", "TrainerHTTPError"]
