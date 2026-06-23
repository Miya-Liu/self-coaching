# SPDX-License-Identifier: MIT
"""Loop driver: task stream, Sigma/B stores, E-path and T-path evolution.

This module is now a thin orchestrator. Implementation lives in:
  - loop_config.py  (configuration, constants, Protocol, TaskScore)
  - scoring.py      (task scoring and routing)
  - e_path.py       (E-path evolution)
  - t_path.py       (T-path evolution)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

# ─── Path setup (shared) ─────────────────────────────────────────────────────

try:
    from ._paths import _MOCK_SERVICES, _REPO_ROOT, _SC_ROOT  # noqa: F401
except ImportError:
    from _paths import _MOCK_SERVICES, _REPO_ROOT, _SC_ROOT  # noqa: F401

# ─── Re-exports from loop_config ─────────────────────────────────────────────

try:
    from .loop_config import (  # noqa: F401
        DEFAULT_AGENT_ID,
        DEFAULT_BATCH_SIZE,
        DEFAULT_SIGMA_MIN,
        DEFAULT_SIGMA_PLAY,
        DEFAULT_TAU_FAIL,
        DEFAULT_TASK_STREAM,
        HOLDOUT_SUITE_ID,
        THRESHOLDS_PATH,
        LoopClient,
        LoopConfig,
        TaskScore,
        _self_questioning_base_url,
        batch_size_threshold,
        holdout_suite_id,
        loop_agent_id,
        sigma_min_threshold,
        sigma_play_threshold,
        tau_fail_threshold,
    )
except ImportError:
    from loop_config import (  # noqa: F401
        DEFAULT_AGENT_ID,
        DEFAULT_BATCH_SIZE,
        DEFAULT_SIGMA_MIN,
        DEFAULT_SIGMA_PLAY,
        DEFAULT_TAU_FAIL,
        DEFAULT_TASK_STREAM,
        HOLDOUT_SUITE_ID,
        THRESHOLDS_PATH,
        LoopClient,
        LoopConfig,
        TaskScore,
        _self_questioning_base_url,
        batch_size_threshold,
        holdout_suite_id,
        loop_agent_id,
        sigma_min_threshold,
        sigma_play_threshold,
        tau_fail_threshold,
    )

# ─── Re-exports from scoring ─────────────────────────────────────────────────

try:
    from .scoring import failure_event_text, process_task, route_score  # noqa: F401
except ImportError:
    from scoring import failure_event_text, process_task, route_score  # noqa: F401

# ─── Re-exports from e_path ──────────────────────────────────────────────────

try:
    from .e_path import (  # noqa: F401
        augment_sigma_sparse,
        learn_from_sigma,
        run_e_path,
    )
except ImportError:
    from e_path import (  # noqa: F401
        augment_sigma_sparse,
        learn_from_sigma,
        run_e_path,
    )

# ─── Re-exports from t_path ──────────────────────────────────────────────────

try:
    from .t_path import fill_buffer_batch, run_t_path  # noqa: F401
except ImportError:
    from t_path import fill_buffer_batch, run_t_path  # noqa: F401

# ─── Local imports needed by orchestrator functions ───────────────────────────

try:
    from .free_time import FreeTimeSimulator
    from .loop_store import LoopStore, SupportEntry, read_jsonl
    from .state import LoopState, LoopStateStore
except ImportError:
    from free_time import FreeTimeSimulator
    from loop_store import LoopStore, SupportEntry, read_jsonl
    from state import LoopState, LoopStateStore


# ─── Orchestrator functions (remain in loop_driver) ──────────────────────────


def load_task_stream(path: str | Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            tasks.append(json.loads(line))
    return tasks


def iter_task_stream(path: str | Path) -> Iterator[dict[str, Any]]:
    for task in load_task_stream(path):
        yield task


def default_client(coaching_root: str | Path, config: LoopConfig | None = None) -> LoopClient:
    try:
        from .loop_env import build_loop_client
    except ImportError:
        from loop_env import build_loop_client

    return build_loop_client(coaching_root, config=config)


def run_tasks(
    coaching_root: str | Path,
    *,
    config: LoopConfig | None = None,
    task_stream_path: str | Path | None = None,
    limit: int | None = None,
    tau_fail: float | None = None,
    sigma_min: int | None = None,
    sigma_play: int | None = None,
    beta: int | None = None,
    idle_after: int | None = None,
    client: LoopClient | None = None,
    agent_id: str | None = None,
    enable_e_path: bool = True,
    enable_t_path: bool = False,
    candidate_model_id: str | None = None,
    self_questioning_engine: Any | None = None,
    agentevals_engine: Any | None = None,
    trajectory_fn: Any | None = None,
) -> tuple[list[TaskScore], LoopState]:
    """Process fixture tasks; route Sigma/B; run E-path and optional T-path.

    If config is provided, its values are used as defaults for thresholds.
    Explicit keyword args (tau_fail, sigma_min, etc.) override the config.
    """
    # Registry factory: use config.registry_factory if provided, else default mock
    def _default_registry(root: Path) -> Any:
        from mock_agent_registry import AgentRegistry
        return AgentRegistry(root)

    cfg = config or LoopConfig.from_env()
    registry_factory = getattr(cfg, "registry_factory", None) or _default_registry
    stream_path = Path(task_stream_path or cfg.task_stream)
    root = Path(coaching_root).resolve()
    agent = agent_id or cfg.agent_id

    store = LoopStateStore(root)
    loop_store = LoopStore(root)
    state = store.load()
    state = store.sync_generation_from_registry(state, agent_id=agent)

    registry = registry_factory(root)
    registry.ensure_agent(agent)
    if store.registry_generation(agent_id=agent) == 0 and state.generation == 0:
        store.write_registry_generation(0, agent_id=agent)

    loop_client = client if client is not None else default_client(root, config=cfg)
    threshold = tau_fail if tau_fail is not None else cfg.tau_fail
    sigma_threshold = sigma_min if sigma_min is not None else cfg.sigma_min
    play_limit = sigma_play if sigma_play is not None else cfg.sigma_play
    batch = beta if beta is not None else cfg.batch_size
    free_time = FreeTimeSimulator(idle_after=idle_after if idle_after is not None else cfg.idle_after)

    sigma: list[SupportEntry] = []
    results: list[TaskScore] = []

    for index, tau in enumerate(iter_task_stream(stream_path)):
        if limit is not None and index >= limit:
            break

        version_id = str(registry.get_agent(agent)["active_version_id"])
        result, _xi, support_entry = process_task(
            tau,
            loop_store=loop_store,
            generation=state.generation,
            version_id=version_id,
            tau_fail=threshold,
            trajectory_fn=trajectory_fn,
        )
        results.append(result)
        state.tasks_processed += 1
        free_time.on_task_completed()

        if result.routed_to == "support":
            assert support_entry is not None
            sigma.append(support_entry)
            state.support_count = len(sigma)
        else:
            state.buffer_count = len(loop_store.active_buffer_rows())

        if enable_e_path and len(sigma) >= sigma_threshold:
            run_e_path(
                sigma,
                client=loop_client,
                registry=registry,
                state=state,
                state_store=store,
                loop_store=loop_store,
                coaching_root=root,
                agent_id=agent,
                sigma_play=play_limit,
                self_questioning_engine=self_questioning_engine,
                config=cfg,
            )
            state.buffer_count = len(loop_store.active_buffer_rows())

        if enable_t_path and free_time.idle():
            free_time.mark_busy()
            run_t_path(
                client=loop_client,
                registry=registry,
                loop_store=loop_store,
                state=state,
                coaching_root=root,
                agent_id=agent,
                beta=batch,
                candidate_model_id=candidate_model_id,
                self_questioning_engine=self_questioning_engine,
                agentevals_engine=agentevals_engine,
                config=cfg,
            )
            state.buffer_count = len(loop_store.active_buffer_rows())

    store.save(state)
    return results, state


def count_store_rows(coaching_root: str | Path) -> tuple[int, int]:
    loop_store = LoopStore(coaching_root)
    return len(read_jsonl(loop_store.support_path)), len(read_jsonl(loop_store.buffer_path))
