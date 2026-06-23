# SPDX-License-Identifier: MIT
"""Maps SelfCoachingClient.self_questioning() to the pipeline self-questioning engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .self_questioning_pipeline_adapter import SelfQuestioningPipelineEngine


class PipelineSelfQuestioningClientAdapter:
    """Orchestrator-facing adapter: client.self_questioning() → pipeline job + proceed signal."""

    def __init__(self, engine: SelfQuestioningPipelineEngine, coaching_root: str | Path):
        self._engine = engine
        self._root = Path(coaching_root).resolve()

    def self_questioning(self, *, capability: str = "tool_use", n: int = 3) -> dict[str, Any]:
        return self._engine.generate_batch(
            coaching_root=self._root,
            capability=capability,
            n=n,
        )
