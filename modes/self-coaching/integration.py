# SPDX-License-Identifier: MIT
"""Public integration API for external callers (e.g., leagent coaching service).

This module provides a clean boundary for driving the self-coaching loop
from outside the self-contained demo/clock flow. External callers should
use these functions instead of importing e_path/t_path directly.

Usage:
    from self_coaching.integration import trigger_e_path, trigger_t_path, score_run

    # Score a single run (called per completed agent run)
    result = score_run(coaching_root, tau, trajectory_fn=...)

    # Trigger evolution (called when thresholds met)
    outcome = trigger_e_path(coaching_root, agent_id=..., registry=..., config=...)
    outcome = trigger_t_path(coaching_root, agent_id=..., registry=..., config=...)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

try:
    from .loop_config import LoopConfig
    from .loop_store import LoopStore, read_jsonl
    from .scoring import TaskScore, process_task
    from .state import LoopState, LoopStateStore
except ImportError:
    from loop_config import LoopConfig
    from loop_store import LoopStore, read_jsonl
    from scoring import TaskScore, process_task
    from state import LoopState, LoopStateStore


def score_run(
    coaching_root: str | Path,
    tau: dict[str, Any],
    *,
    trajectory_fn: Callable[[dict], dict] | None = None,
    tau_fail: float | None = None,
) -> tuple[TaskScore, str]:
    """Score a single task and route to Σ or B.

    Args:
        coaching_root: Path to coaching state directory.
        tau: Task fixture dict (from build_tau).
        trajectory_fn: Function that returns ξ given τ.
        tau_fail: Score threshold below which task routes to Σ.

    Returns:
        (TaskScore, routed_to) where routed_to is "support" or "buffer".
    """
    root = Path(coaching_root).resolve()
    store = LoopStore(root)
    state_store = LoopStateStore(root)
    state = state_store.load()

    version_id = "base"  # External caller can override via tau.metadata

    result, _, _ = process_task(
        tau,
        loop_store=store,
        generation=state.generation,
        version_id=version_id,
        tau_fail=tau_fail,
        trajectory_fn=trajectory_fn,
    )

    # Update counters
    state.tasks_processed += 1
    if result.routed_to == "support":
        state.support_count += 1
    else:
        state.buffer_count = len(store.active_buffer_rows())
    state_store.save(state)

    return result, result.routed_to


def trigger_e_path(
    coaching_root: str | Path,
    *,
    agent_id: str,
    registry: Any,
    config: LoopConfig | None = None,
    client: Any | None = None,
    self_questioning_engine: Any | None = None,
) -> dict[str, Any] | None:
    """Trigger E-path evolution.

    Reads sigma from LoopStore, runs learn, activates draft version.

    Args:
        coaching_root: Path to coaching state directory.
        agent_id: Agent being coached.
        registry: Object implementing get_agent(), create_version(), activate().
        config: Loop configuration (thresholds, backends).
        client: LoopClient for backend calls (mock or real).
        self_questioning_engine: Optional engine for C06 sparse questioning.

    Returns:
        E-path result dict or None if sigma is empty.
    """
    try:
        from .e_path import run_e_path
        from .loop_env import build_loop_client as _build_client
    except ImportError:
        from e_path import run_e_path
        from loop_env import build_loop_client as _build_client

    root = Path(coaching_root).resolve()
    cfg = config or LoopConfig()
    store = LoopStore(root)
    state_store = LoopStateStore(root)
    state = state_store.load()

    # Load sigma entries
    sigma_entries = _load_sigma(store)
    if not sigma_entries:
        return None

    loop_client = client or _build_client(root, config=cfg)

    result = run_e_path(
        sigma_entries,
        client=loop_client,
        registry=registry,
        state=state,
        state_store=state_store,
        loop_store=store,
        coaching_root=root,
        agent_id=agent_id,
        sigma_play=cfg.sigma_play,
        self_questioning_engine=self_questioning_engine,
        config=cfg,
    )

    state_store.save(state)
    return result


def trigger_t_path(
    coaching_root: str | Path,
    *,
    agent_id: str,
    registry: Any,
    config: LoopConfig | None = None,
    client: Any | None = None,
    self_questioning_engine: Any | None = None,
    agentevals_engine: Any | None = None,
    candidate_model_id: str | None = None,
) -> dict[str, Any] | None:
    """Trigger T-path evolution.

    Fills buffer if needed, trains, runs holdout gate, promotes if improved.

    Args:
        coaching_root: Path to coaching state directory.
        agent_id: Agent being coached.
        registry: Object implementing get_agent(), create_version(), activate().
        config: Loop configuration (thresholds, backends).
        client: LoopClient for backend calls (mock or real).
        self_questioning_engine: Optional engine for C07 batch questioning.
        agentevals_engine: Optional engine for holdout evaluation.
        candidate_model_id: Override candidate model identifier.

    Returns:
        T-path result dict or None.
    """
    try:
        from .t_path import run_t_path
        from .loop_env import build_loop_client as _build_client
    except ImportError:
        from t_path import run_t_path
        from loop_env import build_loop_client as _build_client

    root = Path(coaching_root).resolve()
    cfg = config or LoopConfig()
    store = LoopStore(root)
    state_store = LoopStateStore(root)
    state = state_store.load()

    loop_client = client or _build_client(root, config=cfg)

    result = run_t_path(
        client=loop_client,
        registry=registry,
        loop_store=store,
        state=state,
        coaching_root=root,
        agent_id=agent_id,
        beta=cfg.batch_size,
        candidate_model_id=candidate_model_id,
        self_questioning_engine=self_questioning_engine,
        agentevals_engine=agentevals_engine,
        config=cfg,
    )

    state_store.save(state)
    return result


def get_loop_status(coaching_root: str | Path) -> dict[str, Any]:
    """Get current loop state for external monitoring.

    Returns:
        Dict with generation, sigma_size, buffer_size, tasks_processed.
    """
    root = Path(coaching_root).resolve()
    store = LoopStore(root)
    state_store = LoopStateStore(root)
    state = state_store.load()

    sigma_size = len(read_jsonl(store.support_path)) if store.support_path.exists() else 0
    buffer_size = len(store.active_buffer_rows())

    return {
        "generation": state.generation,
        "sigma_size": sigma_size,
        "buffer_size": buffer_size,
        "tasks_processed": state.tasks_processed,
    }


def _load_sigma(store: LoopStore) -> list:
    """Load sigma entries from support.jsonl as SupportEntry objects."""
    try:
        from .scoring import SupportEntry
    except ImportError:
        from scoring import SupportEntry

    if not store.support_path.exists():
        return []

    rows = read_jsonl(store.support_path)
    entries = []
    for row in rows:
        entries.append(SupportEntry(
            task_id=row.get("task_id", ""),
            trajectory_id=row.get("trajectory_id", ""),
            trajectory_ref=row.get("trajectory_ref", ""),
            score=row.get("score", 0.0),
            event_text=row.get("event_text", ""),
        ))
    return entries
