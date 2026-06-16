# SPDX-License-Identifier: MIT
"""Self-play backend via the Self-Questioning Pipeline Service (success signal only)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .pipeline_http import PipelineHTTPError
from .pipeline_mapping import (
    build_batch_request,
    build_suite_request,
    map_batch_result,
    map_pipeline_error,
    map_suite_result,
    pipeline_job_succeeded,
)
from .pipeline_service_client import PipelineServiceClient


class SelfPlayPipelineEngine:
    """Submit pipeline jobs and return proceed / hold signals for the coaching loop.

    Data produced by the pipeline stays in the remote store (Supabase). This adapter
    does **not** export rows into ``staging.jsonl``. Callers use ``proceed`` (or
    ``pipeline_job_succeeded()``) to decide whether to advance the loop.
    """

    def __init__(
        self,
        client: PipelineServiceClient | None = None,
        *,
        use_sync: bool | None = None,
    ):
        self._client = client or PipelineServiceClient()
        if use_sync is None:
            use_sync = os.environ.get("PIPELINE_USE_SYNC", "").strip().lower() in {
                "1",
                "true",
                "yes",
            }
        self._use_sync = use_sync

    def _run(self, body: dict[str, Any]) -> dict[str, Any]:
        if self._use_sync:
            sync_timeout = float(os.environ.get("PIPELINE_SYNC_TIMEOUT_S", "3600"))
            return self._client.run_sync(body, timeout_s=sync_timeout)
        submitted = self._client.submit(body)
        job_id = str(submitted.get("job_id", ""))
        if not job_id:
            raise PipelineHTTPError("pipeline submit returned no job_id", body=submitted)
        return self._client.wait_for_job(job_id)

    def generate_batch(
        self,
        *,
        coaching_root: Path | None = None,  # noqa: ARG002 — mock parity
        capability: str = "tool_use",
        n: int = 3,
    ) -> dict[str, Any]:
        """C07: trigger batch self-play pipeline; return success / failure only."""
        body = build_batch_request(n=n, capability=capability)
        job_id: str | None = None
        try:
            if self._use_sync:
                finished = self._run(body)
            else:
                submitted = self._client.submit(body)
                job_id = str(submitted.get("job_id") or "") or None
                if not job_id:
                    raise PipelineHTTPError("pipeline submit returned no job_id", body=submitted)
                finished = self._client.wait_for_job(job_id)
            return map_batch_result(finished, requested_n=n)
        except PipelineHTTPError as exc:
            return map_pipeline_error(exc, job_id=job_id, mode="batch")

    def generate_suite(
        self,
        *,
        coaching_root: Path | None = None,  # noqa: ARG002
        user_query: str = "",  # noqa: ARG002 — pipeline reads remote messages
        trajectory: dict[str, Any] | None = None,  # noqa: ARG002
        eval_score: float = 0.5,  # noqa: ARG002
        eval_run_id: str | None = None,  # noqa: ARG002
        agent_id: str = "example-agent",  # noqa: ARG002
        version_id: str | None = None,  # noqa: ARG002
        capability: list[str] | str | None = None,  # noqa: ARG002
        mode: str = "adversarial",  # noqa: ARG002
        n_variants: int = 2,
    ) -> dict[str, Any]:
        """C06: trigger sparse self-play pipeline; return success / failure only."""
        body = build_suite_request(n_variants=n_variants)
        job_id: str | None = None
        try:
            if self._use_sync:
                finished = self._run(body)
            else:
                submitted = self._client.submit(body)
                job_id = str(submitted.get("job_id") or "") or None
                if not job_id:
                    raise PipelineHTTPError("pipeline submit returned no job_id", body=submitted)
                finished = self._client.wait_for_job(job_id)
            return map_suite_result(finished, requested_n=n_variants)
        except PipelineHTTPError as exc:
            return map_pipeline_error(exc, job_id=job_id, mode="suite")


def build_self_play_pipeline_engine(
    base_url: str | None = None,
    *,
    client: PipelineServiceClient | None = None,
) -> SelfPlayPipelineEngine:
    """Factory used by loop_env (Sprint 2) and tests."""
    if client is not None:
        return SelfPlayPipelineEngine(client)
    if base_url:
        return SelfPlayPipelineEngine(PipelineServiceClient(base_url))
    return SelfPlayPipelineEngine()


__all__ = [
    "SelfPlayPipelineEngine",
    "build_self_play_pipeline_engine",
    "pipeline_job_succeeded",
]
