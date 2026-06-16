# SPDX-License-Identifier: MIT
"""Loop configuration: env-reading, constants, Protocol, and TaskScore dataclass."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

try:
    from ._paths import _MOCK_SERVICES, _REPO_ROOT
except ImportError:
    from _paths import _MOCK_SERVICES, _REPO_ROOT

from trajectory_scorer import RubricResult  # noqa: E402

# ─── Defaults ────────────────────────────────────────────────────────────────

DEFAULT_TAU_FAIL = 0.75
DEFAULT_SIGMA_MIN = 3
DEFAULT_SIGMA_PLAY = 3
DEFAULT_BATCH_SIZE = 4
DEFAULT_AGENT_ID = "demo-agent"
DEFAULT_TASK_STREAM = _MOCK_SERVICES / "fixtures" / "task_stream" / "tool_use_v1.jsonl"
THRESHOLDS_PATH = _REPO_ROOT / "services" / "orchestrator" / "config" / "thresholds.json"
HOLDOUT_SUITE_ID = "tool-use-holdout"


# ─── Protocol ────────────────────────────────────────────────────────────────

@runtime_checkable
class LoopClient(Protocol):
    def learn(
        self,
        *,
        event: str,
        source: str = "client",
        capability: str = "tool_use",
    ) -> dict[str, Any]: ...

    def train(
        self,
        *,
        pipeline: str = "sft",
        dataset: str | None = None,
        base_model: str = "mock-base",
    ) -> dict[str, Any]: ...


# ─── Dataclass ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TaskScore:
    task_id: str
    score: float
    rubric: RubricResult
    routed_to: str
    trajectory_ref: str


# ─── Config ──────────────────────────────────────────────────────────────────

@dataclass
class LoopConfig:
    tau_fail: float = DEFAULT_TAU_FAIL
    sigma_min: int = DEFAULT_SIGMA_MIN
    sigma_play: int = DEFAULT_SIGMA_PLAY
    batch_size: int = DEFAULT_BATCH_SIZE
    agent_id: str = DEFAULT_AGENT_ID
    task_stream: Path = DEFAULT_TASK_STREAM
    thresholds_path: Path = THRESHOLDS_PATH
    holdout_suite_id: str = HOLDOUT_SUITE_ID

    @classmethod
    def from_env(cls) -> "LoopConfig":
        """Build config from environment variables (current behavior)."""
        return cls(
            tau_fail=float(os.environ.get("LOOP_TAU_FAIL", str(DEFAULT_TAU_FAIL))),
            sigma_min=int(os.environ.get("LOOP_SIGMA_MIN", str(DEFAULT_SIGMA_MIN))),
            sigma_play=int(os.environ.get("LOOP_SIGMA_PLAY", str(DEFAULT_SIGMA_PLAY))),
            batch_size=int(os.environ.get("LOOP_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))),
            agent_id=os.environ.get(
                "LOOP_AGENT_ID", os.environ.get("AGENT_ID", DEFAULT_AGENT_ID)
            ),
            task_stream=Path(
                os.environ.get("LOOP_TASK_STREAM", str(DEFAULT_TASK_STREAM))
            ),
            thresholds_path=Path(
                os.environ.get("LOOP_THRESHOLDS_PATH", str(THRESHOLDS_PATH))
            ),
            holdout_suite_id=os.environ.get(
                "AGENTEVALS_SUITE_ID_HOLDOUT", HOLDOUT_SUITE_ID
            ),
        )


# ─── Backward-compatible env-reading helpers ─────────────────────────────────


def tau_fail_threshold() -> float:
    return float(os.environ.get("LOOP_TAU_FAIL", str(DEFAULT_TAU_FAIL)))


def sigma_min_threshold() -> int:
    return int(os.environ.get("LOOP_SIGMA_MIN", str(DEFAULT_SIGMA_MIN)))


def sigma_play_threshold() -> int:
    return int(os.environ.get("LOOP_SIGMA_PLAY", str(DEFAULT_SIGMA_PLAY)))


def batch_size_threshold() -> int:
    return int(os.environ.get("LOOP_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)))


def loop_agent_id() -> str:
    return os.environ.get("LOOP_AGENT_ID", os.environ.get("AGENT_ID", DEFAULT_AGENT_ID))


def holdout_suite_id() -> str:
    return os.environ.get("AGENTEVALS_SUITE_ID_HOLDOUT", HOLDOUT_SUITE_ID)


def _self_play_base_url() -> str | None:
    value = os.environ.get("MOCK_SELF_PLAY_URL", "").strip()
    return value.rstrip("/") if value else None
