# SPDX-License-Identifier: MIT
"""Composite SelfCoachingClient: delegate eval to AgentEvals, other ops to inner client."""

from __future__ import annotations

from typing import Any

from .agentevals_client import AgentEvalsError
from .eval_adapter import AgentEvalsEvalAdapter


class CompositeClient:
    """Wrap a SelfCoachingClient so evaluate/eval_report use a dedicated eval backend."""

    def __init__(self, inner: Any, eval_adapter: AgentEvalsEvalAdapter):
        self._inner = inner
        self._eval = eval_adapter

    def health(self) -> dict[str, Any]:
        base = self._inner.health()
        try:
            ae = self._eval._client.health()
        except AgentEvalsError as exc:
            ae = {"status": "error", "error": str(exc)}
        return {**base, "eval_backend": "agentevals", "agentevals": ae}

    def learn(self, *, event: str, source: str = "client", capability: str = "tool_use") -> dict[str, Any]:
        return self._inner.learn(event=event, source=source, capability=capability)

    def self_play(self, *, capability: str = "tool_use", n: int = 3) -> dict[str, Any]:
        return self._inner.self_play(capability=capability, n=n)

    def evaluate(
        self,
        *,
        candidate: str = "mock-candidate-v1",
        baseline: str = "mock-baseline-v0",
    ) -> dict[str, Any]:
        return self._eval.evaluate(candidate=candidate, baseline=baseline)

    def eval_report(self, run_id: str) -> dict[str, Any]:
        return self._eval.eval_report(run_id)

    def train(
        self,
        *,
        pipeline: str = "sft",
        dataset: str | None = None,
        base_model: str = "mock-base",
    ) -> dict[str, Any]:
        return self._inner.train(pipeline=pipeline, dataset=dataset, base_model=base_model)

    def run_all(self, *, capability: str = "tool_use", pipeline: str = "sft") -> dict[str, Any]:
        return self._inner.run_all(capability=capability, pipeline=pipeline)


def build_composite_client(
    inner: Any,
    *,
    eval_backend: str = "mock",
    eval_adapter: AgentEvalsEvalAdapter | None = None,
) -> Any:
    """Return inner unchanged for mock eval, or a CompositeClient for agentevals."""
    if eval_backend.lower() == "agentevals":
        return CompositeClient(inner, eval_adapter or AgentEvalsEvalAdapter())
    return inner


def with_agentevals_eval(inner: Any, eval_adapter: AgentEvalsEvalAdapter | None = None) -> CompositeClient:
    """Wrap a SelfCoachingClient so evaluate/eval_report use AgentEvals."""
    return build_composite_client(inner, eval_backend="agentevals", eval_adapter=eval_adapter)
