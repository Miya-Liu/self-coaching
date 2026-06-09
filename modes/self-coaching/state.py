# SPDX-License-Identifier: MIT
"""Loop generation state persisted under {coaching_root}/.self-coaching/loop/."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class LoopState:
    """Counters owned by the loop store; generation mirrors registry meta.generation (A6)."""

    generation: int = 0
    support_count: int = 0
    buffer_count: int = 0
    tasks_processed: int = 0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LoopState:
        return cls(
            generation=int(raw.get("generation", 0)),
            support_count=int(raw.get("support_count", 0)),
            buffer_count=int(raw.get("buffer_count", 0)),
            tasks_processed=int(raw.get("tasks_processed", 0)),
        )

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class LoopStateStore:
    """Read/write state.json under the coaching root loop directory."""

    def __init__(self, coaching_root: str | Path):
        self.coaching_root = Path(coaching_root).resolve()
        self.path = self.coaching_root / ".self-coaching" / "loop" / "state.json"

    def load(self) -> LoopState:
        if not self.path.is_file():
            return LoopState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return LoopState.from_dict(raw)

    def save(self, state: LoopState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _meta_path(self, *, data_dir: str | Path | None = None, agent_id: str = "demo-agent") -> Path:
        root = Path(data_dir if data_dir is not None else self.coaching_root)
        try:
            import re

            safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", agent_id).strip("-") or "agent"
        except ImportError:  # pragma: no cover
            safe = agent_id
        return root / "agents" / safe / "meta.json"

    def registry_generation(self, *, data_dir: str | Path | None = None, agent_id: str = "demo-agent") -> int:
        """Read meta.generation from the mock agent registry when present."""
        meta_path = self._meta_path(data_dir=data_dir, agent_id=agent_id)
        if not meta_path.is_file():
            return 0
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return int(meta.get("generation", 0))

    def write_registry_generation(
        self,
        generation: int,
        *,
        data_dir: str | Path | None = None,
        agent_id: str = "demo-agent",
    ) -> None:
        """Persist meta.generation for A6 registry mirror."""
        meta_path = self._meta_path(data_dir=data_dir, agent_id=agent_id)
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = {"agent_id": agent_id}
        meta["generation"] = generation
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def sync_generation_from_registry(
        self,
        state: LoopState,
        *,
        data_dir: str | Path | None = None,
        agent_id: str = "demo-agent",
    ) -> LoopState:
        """Enforce A6: loop state.generation mirrors registry meta.generation."""
        state.generation = self.registry_generation(data_dir=data_dir, agent_id=agent_id)
        return state
