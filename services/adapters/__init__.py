# SPDX-License-Identifier: MIT
"""Adapters from external systems (AgentEvals, production agent, AERL) to the evolution engine."""

from .aerl_client import AERLClient, AERLError
from .agentevals_client import AgentEvalsClient, AgentEvalsError
from .composite_client import CompositeClient, build_composite_client, with_agentevals_eval
from .eval_adapter import AgentEvalsEvalAdapter
from .holdout_engine import (
    AgentEvalsHoldoutEngine,
    build_holdout_engine,
    collect_holdout_metrics,
    holdout_timeout_s,
    wait_for_holdout_run,
)
from .learn_adapter import SelfLearningAdapter
from .self_learning_client import SelfLearningClient, SelfLearningError
from .train_adapter import AERLTrainAdapter
from .trainer_rest_client import RestClient
from .training_client import TrainingClient, TrainerHTTPError

__all__ = [
    "AERLClient",
    "AERLError",
    "AERLTrainAdapter",
    "AgentEvalsClient",
    "AgentEvalsError",
    "AgentEvalsEvalAdapter",
    "AgentEvalsHoldoutEngine",
    "CompositeClient",
    "RestClient",
    "SelfLearningAdapter",
    "SelfLearningClient",
    "SelfLearningError",
    "TrainerHTTPError",
    "TrainingClient",
    "build_composite_client",
    "build_holdout_engine",
    "collect_holdout_metrics",
    "holdout_timeout_s",
    "wait_for_holdout_run",
    "with_agentevals_eval",
]
