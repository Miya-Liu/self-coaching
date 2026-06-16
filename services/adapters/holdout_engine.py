# SPDX-License-Identifier: MIT
"""Holdout eval engine factory for the self-coaching T-path gate."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from services._paths import ensure_mock_services_importable
from services.adapters.agentevals_mapping import build_agent_config, resolve_model_name
from services.orchestrator.eval_metrics import EvalMetrics, normalize_from_agentevals

_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "canceled"})


def holdout_suite_id() -> str:
    return os.environ.get("AGENTEVALS_SUITE_ID_HOLDOUT", "tool-use-holdout")


def holdout_timeout_s() -> float:
    return float(os.environ.get("LOOP_HOLDOUT_TIMEOUT_S", "5"))


def holdout_poll_interval_s() -> float:
    if _uses_http_holdout():
        return float(os.environ.get("AGENTEVALS_POLL_INTERVAL_S", "5"))
    return 0.02


def _uses_http_holdout() -> bool:
    if os.environ.get("ORCHESTRATOR_EVAL_BACKEND", "mock").lower() == "agentevals":
        return True
    url = os.environ.get("AGENTEVALS_BASE_URL") or os.environ.get("MOCK_AGENTEVALS_URL")
    return bool(url and url.strip())


@runtime_checkable
class HoldoutEngine(Protocol):
    registry: Any

    def create_run(self, body: dict[str, Any]) -> dict[str, Any]: ...

    def get_run(self, run_id: str) -> dict[str, Any]: ...


class AgentEvalsHoldoutEngine:
    """AgentEvals HTTP holdout with local registry for version metadata."""

    def __init__(self, coaching_root: str | Path, client: Any):
        ensure_mock_services_importable()
        from mock_agent_registry import AgentRegistry  # noqa: E402

        self.registry = AgentRegistry(coaching_root)
        self._client = client

    def create_run(self, body: dict[str, Any]) -> dict[str, Any]:
        agent_config = body.get("agent_config") or {}
        return self._client.create_run(
            suite_id=str(body["suite_id"]),
            agent_config=agent_config,
            num_trials=body.get("num_trials"),
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._client.get_run(run_id)


def _agentevals_base_url() -> str | None:
    for key in ("AGENTEVALS_BASE_URL", "MOCK_AGENTEVALS_URL"):
        value = os.environ.get(key, "").strip()
        if value:
            return value.rstrip("/")
    return None


def build_holdout_engine(coaching_root: str | Path) -> HoldoutEngine:
    """Return mock in-process or HTTP AgentEvals engine per env profile."""
    eval_backend = os.environ.get("ORCHESTRATOR_EVAL_BACKEND", "mock").lower()
    ae_url = _agentevals_base_url()

    if eval_backend == "agentevals" or ae_url:
        from .agentevals_client import AgentEvalsClient

        client = AgentEvalsClient(base_url=ae_url)
        return AgentEvalsHoldoutEngine(coaching_root, client)

    ensure_mock_services_importable()
    from mock_agentevals import MockAgentEvalsEngine  # noqa: E402

    return MockAgentEvalsEngine(coaching_root)


def wait_for_holdout_run(
    engine: HoldoutEngine,
    run_id: str,
    *,
    timeout_s: float | None = None,
    poll_interval_s: float | None = None,
) -> dict[str, Any]:
    """Poll until the run reaches a terminal status or timeout."""
    budget = holdout_timeout_s() if timeout_s is None else timeout_s
    deadline = time.time() + budget
    interval = holdout_poll_interval_s() if poll_interval_s is None else poll_interval_s
    while time.time() < deadline:
        detail = engine.get_run(run_id)
        status = str(detail.get("status", "")).lower()
        if status in _TERMINAL:
            if status != "succeeded":
                raise RuntimeError(f"holdout eval run {run_id} ended with status={status!r}")
            return detail
        time.sleep(interval)
    raise RuntimeError(f"holdout eval run {run_id} did not succeed within {budget}s")


def collect_holdout_metrics(
    engine: HoldoutEngine,
    *,
    agent_id: str,
    version_id: str,
    coaching_root: Path,
    timeout_s: float | None = None,
) -> EvalMetrics:
    """Run holdout suite eval and map RunDetail → EvalMetrics (C18 gate)."""
    version = engine.registry.get_version(agent_id, version_id)
    components = version.get("components") or {}
    model_id = str(components.get("model_id", version_id))
    skill_bundle = str(components.get("skill_bundle_version", "unknown"))
    model_name = resolve_model_name(components=components if isinstance(components, dict) else None)

    created = engine.create_run(
        {
            "suite_id": holdout_suite_id(),
            "num_trials": 1,
            "agent_config": build_agent_config(
                agent_id=agent_id,
                version_id=version_id,
                baseline_version_id=version_id,
                components=components if isinstance(components, dict) else None,
                model_name=model_name,
            ),
        }
    )
    run_id = str(created.get("id") or created.get("run_id") or "")
    if not run_id:
        raise RuntimeError("holdout create_run response missing id")

    detail = wait_for_holdout_run(engine, run_id, timeout_s=timeout_s)
    return normalize_from_agentevals(
        agent_id=agent_id,
        run_detail=detail,
        skill_bundle_version=skill_bundle,
        model_checkpoint_id=model_id,
        split="holdout",
    )
