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
from .pipeline_http import PipelineHTTPError
from .pipeline_service_client import PipelineServiceClient
from .self_questioning_pipeline_adapter import (
    SelfQuestioningPipelineEngine,
    build_self_questioning_pipeline_engine,
    pipeline_job_succeeded,
)
from .self_learning_client import SelfLearningClient, SelfLearningError
from .cli_train_adapter import CLITrainAdapter
from .cli_train_errors import (
    CLITrainError,
    TrainerCLIError,
    TrainerTimeoutError,
    TransportError,
)
from .trainer_rest_client import RestClient
from .trainer_client import TrainerClient, TrainerHTTPError

__all__ = [
    "AERLClient",
    "AERLError",
    "AERLTrainAdapter",
    "CLITrainAdapter",
    "CLITrainError",
    "AgentEvalsClient",
    "AgentEvalsError",
    "AgentEvalsEvalAdapter",
    "AgentEvalsHoldoutEngine",
    "CompositeClient",
    "PipelineHTTPError",
    "PipelineServiceClient",
    "SelfQuestioningPipelineEngine",
    "build_self_questioning_pipeline_engine",
    "pipeline_job_succeeded",
    "RestClient",
    "SelfLearningAdapter",
    "SelfLearningClient",
    "SelfLearningError",
    "TrainerHTTPError",
    "TrainerCLIError",
    "TrainerTimeoutError",
    "TransportError",
    "TrainerClient",
    "build_composite_client",
    "build_holdout_engine",
    "collect_holdout_metrics",
    "holdout_timeout_s",
    "wait_for_holdout_run",
    "with_agentevals_eval",
]
