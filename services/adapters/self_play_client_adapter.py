# SPDX-License-Identifier: MIT
"""Maps SelfCoachingClient.self_play() to the pipeline self-play engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selfplay_pipeline_adapter import SelfPlayPipelineEngine


class PipelineSelfPlayClientAdapter:
    """Orchestrator-facing adapter: client.self_play() → pipeline job + proceed signal."""

    def __init__(self, engine: SelfPlayPipelineEngine, coaching_root: str | Path):
        self._engine = engine
        self._root = Path(coaching_root).resolve()

    def self_play(self, *, capability: str = "tool_use", n: int = 3) -> dict[str, Any]:
        return self._engine.generate_batch(
            coaching_root=self._root,
            capability=capability,
            n=n,
        )
