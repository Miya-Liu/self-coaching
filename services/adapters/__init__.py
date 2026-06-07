# SPDX-License-Identifier: MIT
"""Adapters from external systems (AgentEvals, production agent, AERL) to the evolution engine."""

from .agentevals_client import AgentEvalsClient, AgentEvalsError
from .composite_client import CompositeClient, build_composite_client, with_agentevals_eval
from .eval_adapter import AgentEvalsEvalAdapter

__all__ = [
    "AgentEvalsClient",
    "AgentEvalsError",
    "AgentEvalsEvalAdapter",
    "CompositeClient",
    "build_composite_client",
    "with_agentevals_eval",
]
