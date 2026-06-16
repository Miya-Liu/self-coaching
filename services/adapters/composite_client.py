# SPDX-License-Identifier: MIT
"""Composite SelfCoachingClient: delegate eval to AgentEvals, train to AERL."""

from __future__ import annotations

from typing import Any

from .agentevals_client import AgentEvalsError
from .aerl_client import AERLError
from .eval_adapter import AgentEvalsEvalAdapter
from .learn_adapter import SelfLearningAdapter
from .self_play_client_adapter import PipelineSelfPlayClientAdapter
from .train_adapter import AERLTrainAdapter


def _default_train_adapter(train_backend: str) -> AERLTrainAdapter | Any:
    if train_backend.lower() == "cli":
        from .cli_train_adapter import CLITrainAdapter

        return CLITrainAdapter()
    return AERLTrainAdapter()


class CompositeClient:
    """Wrap a SelfCoachingClient so evaluate/train/learn can use dedicated backends."""

    def __init__(
        self,
        inner: Any,
        *,
        eval_adapter: AgentEvalsEvalAdapter | None = None,
        train_adapter: AERLTrainAdapter | Any | None = None,
        learn_adapter: SelfLearningAdapter | None = None,
        self_play_adapter: PipelineSelfPlayClientAdapter | None = None,
    ):
        self._inner = inner
        self._eval = eval_adapter
        self._train = train_adapter
        self._learn = learn_adapter
        self._self_play = self_play_adapter

    def health(self) -> dict[str, Any]:
        base = self._inner.health()
        out = dict(base)
        if self._eval is not None:
            try:
                ae = self._eval._client.health()
            except AgentEvalsError as exc:
                ae = {"status": "error", "error": str(exc)}
            out["eval_backend"] = "agentevals"
            out["agentevals"] = ae
        if self._train is not None:
            train_backend = "cli" if type(self._train).__name__ == "CLITrainAdapter" else "aerl"
            try:
                if hasattr(self._train, "health"):
                    tr = self._train.health()
                else:
                    tr = self._train._client.health()
            except (AERLError, Exception) as exc:  # noqa: BLE001
                tr = {"status": "error", "error": str(exc)}
            out["train_backend"] = train_backend
            if train_backend == "cli":
                out["cli_train"] = tr
            else:
                out["aerl"] = tr
        if self._learn is not None:
            from .self_learning_client import SelfLearningError
            try:
                sl = self._learn._client.health()
            except SelfLearningError as exc:
                sl = {"status": "error", "error": str(exc)}
            out["learn_backend"] = "self-learning"
            out["self_learning"] = sl
        if self._self_play is not None:
            from .pipeline_service_client import PipelineServiceClient

            try:
                sp = PipelineServiceClient().health()
            except Exception as exc:  # noqa: BLE001
                sp = {"status": "error", "error": str(exc)}
            out["selfplay_backend"] = "pipeline"
            out["pipeline_service"] = sp
        return out

    def learn(self, *, event: str, source: str = "client", capability: str = "tool_use") -> dict[str, Any]:
        if self._learn is None:
            return self._inner.learn(event=event, source=source, capability=capability)
        return self._learn.learn(event=event, source=source, capability=capability)

    def self_play(self, *, capability: str = "tool_use", n: int = 3) -> dict[str, Any]:
        if self._self_play is None:
            return self._inner.self_play(capability=capability, n=n)
        return self._self_play.self_play(capability=capability, n=n)

    def evaluate(
        self,
        *,
        candidate: str = "mock-candidate-v1",
        baseline: str = "mock-baseline-v0",
    ) -> dict[str, Any]:
        if self._eval is None:
            return self._inner.evaluate(candidate=candidate, baseline=baseline)
        return self._eval.evaluate(candidate=candidate, baseline=baseline)

    def eval_report(self, run_id: str) -> dict[str, Any]:
        if self._eval is None:
            return self._inner.eval_report(run_id)
        return self._eval.eval_report(run_id)

    def train(
        self,
        *,
        pipeline: str = "sft",
        dataset: str | None = None,
        base_model: str = "mock-base",
        coaching_root: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        if self._train is None:
            return self._inner.train(pipeline=pipeline, dataset=dataset, base_model=base_model)
        root = coaching_root or getattr(self._inner, "_root", None)
        return self._train.train(
            pipeline=pipeline,
            dataset=dataset,
            base_model=base_model,
            coaching_root=str(root) if root is not None else None,
            agent_id=agent_id,
        )

    def run_all(self, *, capability: str = "tool_use", pipeline: str = "sft") -> dict[str, Any]:
        return self._inner.run_all(capability=capability, pipeline=pipeline)  # type: ignore[no-any-return]


def build_composite_client(
    inner: Any,
    *,
    eval_backend: str = "mock",
    train_backend: str = "mock",
    learn_backend: str = "mock",
    selfplay_backend: str = "mock",
    eval_adapter: AgentEvalsEvalAdapter | None = None,
    train_adapter: AERLTrainAdapter | Any | None = None,
    learn_adapter: SelfLearningAdapter | None = None,
    self_play_adapter: PipelineSelfPlayClientAdapter | None = None,
) -> Any:  # noqa: ANN401
    """Return inner unchanged when all backends are mock, else CompositeClient."""
    use_eval = eval_backend.lower() == "agentevals"
    use_train = train_backend.lower() in ("aerl", "cli")
    use_learn = learn_backend.lower() in ("self-learning", "http")
    use_selfplay = selfplay_backend.lower() == "pipeline" and self_play_adapter is not None
    if not use_eval and not use_train and not use_learn and not use_selfplay:
        return inner
    return CompositeClient(
        inner,
        eval_adapter=(eval_adapter or AgentEvalsEvalAdapter()) if use_eval else None,
        train_adapter=(_default_train_adapter(train_backend) if train_adapter is None else train_adapter)
        if use_train
        else None,
        learn_adapter=(learn_adapter or SelfLearningAdapter()) if use_learn else None,
        self_play_adapter=self_play_adapter if use_selfplay else None,
    )


def with_agentevals_eval(inner: Any, eval_adapter: AgentEvalsEvalAdapter | None = None) -> CompositeClient:
    """Wrap a SelfCoachingClient so evaluate/eval_report use AgentEvals."""
    return build_composite_client(inner, eval_backend="agentevals", eval_adapter=eval_adapter)  # type: ignore[no-any-return]
