# SPDX-License-Identifier: MIT
"""Adapters from external systems (AgentEvals, production agent, AERL) to the evolution engine."""

from .aerl_client import AERLClient, AERLError
from .agentevals_client import AgentEvalsClient, AgentEvalsError
from .composite_client import CompositeClient, build_composite_client, with_agentevals_eval
from .eval_adapter import AgentEvalsEvalAdapter
from .train_adapter import AERLTrainAdapter

__all__ = [
    "AERLClient",
    "AERLError",
    "AERLTrainAdapter",
    "AgentEvalsClient",
    "AgentEvalsError",
    "AgentEvalsEvalAdapter",
    "CompositeClient",
    "build_composite_client",
    "with_agentevals_eval",
]
