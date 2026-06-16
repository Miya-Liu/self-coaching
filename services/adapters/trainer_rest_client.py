# SPDX-License-Identifier: MIT
"""RestClient — trainer durable artifacts (checkpoints, models, processes)."""

from __future__ import annotations

import urllib.parse
from typing import Any

from .trainer_http import TrainerHTTPBase


class RestClient(TrainerHTTPBase):
    """HTTP client for RestClient routes (self-tuning-trainer-api-plan §4.13–§4.16)."""

    def list_checkpoints(
        self,
        *,
        training_run_id: str | None = None,
        base_model: str | None = None,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"limit": str(limit)}
        if training_run_id:
            params["training_run_id"] = training_run_id
        if base_model:
            params["base_model"] = base_model
        if agent_id:
            params["agent_id"] = agent_id
        query = urllib.parse.urlencode(params)
        return self._request("GET", f"/v1/checkpoints?{query}")

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/checkpoints/{checkpoint_id}")

    def get_weights(self, checkpoint_id: str) -> dict[str, Any]:
        checkpoint = self.get_checkpoint(checkpoint_id)
        weights = checkpoint.get("weights")
        if not isinstance(weights, dict):
            raise KeyError(f"checkpoint {checkpoint_id} has no weights block")
        return weights

    def list_models(
        self,
        *,
        agent_id: str | None = None,
        base_model: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"limit": str(limit)}
        if agent_id:
            params["agent_id"] = agent_id
        if base_model:
            params["base_model"] = base_model
        query = urllib.parse.urlencode(params)
        return self._request("GET", f"/v1/models?{query}")

    def get_model(self, model_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/models/{model_id}")

    def list_processes(
        self,
        *,
        training_run_id: str | None = None,
        checkpoint_id: str | None = None,
        process_type: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if training_run_id:
            params["training_run_id"] = training_run_id
        if checkpoint_id:
            params["checkpoint_id"] = checkpoint_id
        if process_type:
            params["type"] = process_type
        if status:
            params["status"] = status
        suffix = f"?{urllib.parse.urlencode(params)}" if params else ""
        return self._request("GET", f"/v1/processes{suffix}")

    def get_process(self, process_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/processes/{process_id}")
