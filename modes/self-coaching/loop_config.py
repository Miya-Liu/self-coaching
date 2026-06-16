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


def cli_train_env_configured() -> bool:
    """True when Supabase credentials exist for db_bridge CLI training."""
    return bool(
        os.environ.get("SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        and os.environ.get("BRIDGE_USER_ID")
    )


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
    """Single source of truth for loop runtime configuration.

    Construct via:
      - LoopConfig.from_env()       — read from os.environ (legacy path)
      - LoopConfig.from_env_file()  — load .env file then read environ
      - Direct construction          — tests, programmatic use
    """

    # ── Loop thresholds ──
    tau_fail: float = DEFAULT_TAU_FAIL
    sigma_min: int = DEFAULT_SIGMA_MIN
    sigma_play: int = DEFAULT_SIGMA_PLAY
    batch_size: int = DEFAULT_BATCH_SIZE
    agent_id: str = DEFAULT_AGENT_ID
    task_stream: Path = DEFAULT_TASK_STREAM
    thresholds_path: Path = THRESHOLDS_PATH
    holdout_suite_id: str = HOLDOUT_SUITE_ID

    # ── Service mode ──
    service_mode: str = "mock-module"  # mock-module | mock-http | live

    # ── Backends ──
    eval_backend: str = "mock"       # mock | agentevals
    train_backend: str = "mock"      # mock | aerl | cli
    learn_backend: str = "mock"      # mock | self-learning
    selfplay_backend: str = "mock"   # mock | pipeline
    transport: str = "module"        # module | http

    # ── Service URLs (None = in-process mock) ──
    orchestrator_base_url: str | None = None
    agentevals_url: str | None = None
    self_learning_url: str | None = None
    self_play_url: str | None = None
    pipeline_service_url: str | None = None
    aerl_url: str | None = None

    # ── AgentEvals suite IDs ──
    agentevals_suite_id: str = "tool-use-canary"

    # ── Auth ──
    api_token: str | None = None

    # ── Timeouts ──
    holdout_timeout_s: float = 5.0
    idle_after: int = 0

    # ── Mock stack ──
    auto_start_mock_stack: bool = True

    # ── Factories (injectable for production) ──
    # Callable[[Path], AgentRegistry-like] — default uses mock_agent_registry
    registry_factory: Any = None
    # Callable[[Path], SelfPlayEngine-like] — default uses MockSelfPlayEngine
    self_play_factory: Any = None

    @classmethod
    def from_env(cls) -> "LoopConfig":
        """Build config from environment variables."""
        mode = os.environ.get("LOOP_SERVICE_MODE", "mock-module").strip().lower()

        # Resolve URLs
        ae_url = os.environ.get("AGENTEVALS_BASE_URL") or os.environ.get("MOCK_AGENTEVALS_URL")
        sl_url = os.environ.get("SELF_LEARNING_BASE_URL") or os.environ.get("MOCK_SELF_LEARNING_URL")
        sp_url = os.environ.get("SELF_PLAY_BASE_URL") or os.environ.get("MOCK_SELF_PLAY_URL")
        pipeline_url = os.environ.get("PIPELINE_SERVICE_URL") or os.environ.get("SELF_QUESTIONING_URL")
        aerl_url = os.environ.get("TRAINER_BASE_URL") or os.environ.get("MOCK_AERL_URL") or os.environ.get("AERL_BASE_URL")

        # Resolve backends (explicit env takes priority, else infer from URLs in live mode)
        eval_be = os.environ.get("ORCHESTRATOR_EVAL_BACKEND", "mock").lower()
        train_be = os.environ.get("ORCHESTRATOR_TRAIN_BACKEND", "mock").lower()
        learn_be = os.environ.get("ORCHESTRATOR_LEARN_BACKEND", "mock").lower()
        selfplay_be = os.environ.get("ORCHESTRATOR_SELFPLAY_BACKEND", "mock").lower()
        if mode == "live":
            if eval_be == "mock" and ae_url:
                eval_be = "agentevals"
            if train_be == "mock":
                if aerl_url:
                    train_be = "aerl"
                elif cli_train_env_configured():
                    train_be = "cli"
            if learn_be == "mock" and sl_url:
                learn_be = "self-learning"
            if selfplay_be == "mock" and pipeline_url:
                selfplay_be = "pipeline"

        return cls(
            tau_fail=float(os.environ.get("LOOP_TAU_FAIL", str(DEFAULT_TAU_FAIL))),
            sigma_min=int(os.environ.get("LOOP_SIGMA_MIN", str(DEFAULT_SIGMA_MIN))),
            sigma_play=int(os.environ.get("LOOP_SIGMA_PLAY", str(DEFAULT_SIGMA_PLAY))),
            batch_size=int(os.environ.get("LOOP_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))),
            agent_id=os.environ.get("LOOP_AGENT_ID", os.environ.get("AGENT_ID", DEFAULT_AGENT_ID)),
            task_stream=Path(os.environ.get("LOOP_TASK_STREAM", str(DEFAULT_TASK_STREAM))),
            thresholds_path=Path(os.environ.get("LOOP_THRESHOLDS_PATH", str(THRESHOLDS_PATH))),
            holdout_suite_id=os.environ.get("AGENTEVALS_SUITE_ID_HOLDOUT", HOLDOUT_SUITE_ID),
            service_mode=mode,
            eval_backend=eval_be,
            train_backend=train_be,
            learn_backend=learn_be,
            selfplay_backend=selfplay_be,
            transport=os.environ.get("ORCHESTRATOR_TRANSPORT", "module").lower(),
            orchestrator_base_url=os.environ.get("ORCHESTRATOR_BASE_URL"),
            agentevals_url=ae_url or None,
            self_learning_url=sl_url or None,
            self_play_url=sp_url or None,
            pipeline_service_url=pipeline_url or None,
            aerl_url=aerl_url or None,
            agentevals_suite_id=os.environ.get("AGENTEVALS_SUITE_ID", "tool-use-canary"),
            api_token=os.environ.get("AGENT_API_TOKEN") or os.environ.get("MOCK_SERVICE_TOKEN"),
            holdout_timeout_s=float(os.environ.get("LOOP_HOLDOUT_TIMEOUT_S", "5")),
            idle_after=int(os.environ.get("LOOP_IDLE_AFTER", "0")),
            auto_start_mock_stack=os.environ.get("LOOP_AUTO_START_MOCK_STACK", "1").strip() not in ("0", "false", "no"),
        )

    @classmethod
    def from_env_file(cls, path: str | Path) -> "LoopConfig":
        """Load a .env file into os.environ, then build from env.

        File values override existing env vars (file-wins semantics,
        matching loop_env.load_env_file default behavior).
        """
        env_path = Path(path).resolve()
        if not env_path.is_file():
            raise FileNotFoundError(f"env file not found: {env_path}")
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key:
                continue
            value = value.split("#", 1)[0].strip().strip("'\"")
            os.environ[key] = value  # file wins (overwrite)
        return cls.from_env()


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
