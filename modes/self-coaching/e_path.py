# SPDX-License-Identifier: MIT
"""E-path evolution: learn from failures and evolve agent skill patches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from ._paths import _SC_ROOT  # noqa: F401 — triggers sys.path setup
    from .loop_config import LoopClient, LoopConfig, sigma_play_threshold
    from .loop_store import LoopStore, SupportEntry, read_jsonl
    from .self_questioning_factory import run_suite_self_questioning
    from .state import LoopState, LoopStateStore
except ImportError:
    from _paths import _SC_ROOT  # noqa: F401
    from loop_config import LoopClient, LoopConfig, sigma_play_threshold
    from loop_store import LoopStore, SupportEntry, read_jsonl
    from self_questioning_factory import run_suite_self_questioning
    from state import LoopState, LoopStateStore


def learn_from_sigma(client: LoopClient, sigma: list[SupportEntry]) -> dict[str, Any]:
    if not sigma:
        raise ValueError("learn_from_sigma requires a non-empty Sigma")
    first = sigma[0]
    event = f"skill patch needed: {first.event_text}"
    return client.learn(event=event, source="loop-e-path", capability="tool_use")


def _load_trajectory(coaching_root: Path, trajectory_ref: str) -> dict[str, Any]:
    return json.loads((coaching_root / trajectory_ref).read_text(encoding="utf-8"))


def augment_sigma_sparse(
    sigma: list[SupportEntry],
    *,
    coaching_root: Path,
    loop_store: LoopStore,
    agent_id: str,
    version_id: str,
    generation: int,
    sigma_play: int,
    self_questioning_engine: Any | None = None,
    config: LoopConfig | None = None,
) -> dict[str, Any] | None:
    """C06: sparse failure-conditioned self-questioning augments Sigma before E.learn."""
    if not sigma:
        return None
    sigma_size = len(sigma)
    if not (0 < sigma_size <= sigma_play):
        return None

    first = sigma[0]
    trajectory = _load_trajectory(coaching_root, first.trajectory_ref)
    n_variants = min(sigma_size, sigma_play)
    body = {
        "coaching_root": str(coaching_root),
        "user_query": first.event_text,
        "trajectory": trajectory,
        "eval_score": first.score,
        "mode": "adversarial",
        "n_variants": n_variants,
        "agent_id": agent_id,
        "version_id": version_id,
    }

    result = run_suite_self_questioning(
        coaching_root=coaching_root,
        body=body,
        config=config,
        engine=self_questioning_engine,
    )

    staging = coaching_root / ".self-coaching" / "curated" / "staging.jsonl"
    # Pipeline backend: remote data stays in Supabase; only proceed signal matters.
    if not result.get("pipeline_service"):
        for traj in read_jsonl(staging):
            traj_id, trajectory_ref = loop_store.save_trajectory(
                str(traj.get("case_id") or traj.get("id") or "suite-variant"),
                traj,
            )
            traj_score = float((traj.get("critique") or {}).get("score", 0.5))
            traj_task_id = str(traj.get("case_id") or traj.get("id") or "suite-variant")
            event_text = f"Synthetic adversarial failure on {traj_task_id} (score={traj_score:.2f})"
            entry = SupportEntry(
                task_id=str(traj.get("case_id") or traj.get("id") or "suite-variant"),
                trajectory_id=traj_id,
                trajectory_ref=trajectory_ref,
                score=float((traj.get("critique") or {}).get("score", 0.5)),
                event_text=event_text,
            )
            sigma.append(entry)
            loop_store.append_support(
                task_id=entry.task_id,
                generation=generation,
                version_id=version_id,
                trajectory_id=traj_id,
                trajectory_ref=trajectory_ref,
                score=entry.score,
                event_text=entry.event_text,
            )
    return result


def run_e_path(
    sigma: list[SupportEntry],
    *,
    client: LoopClient,
    registry: Any,
    state: LoopState,
    state_store: LoopStateStore,
    loop_store: LoopStore,
    coaching_root: Path,
    agent_id: str,
    sigma_play: int | None = None,
    self_questioning_engine: Any | None = None,
    config: LoopConfig | None = None,
) -> dict[str, Any] | None:
    """E-path: optional sparse self-questioning, learn, activate draft, bump g, flush stale B."""
    if not sigma:
        return None

    bootstrap_version = str(registry.get_agent(agent_id)["active_version_id"])
    play_limit = sigma_play if sigma_play is not None else sigma_play_threshold()
    suite_result = augment_sigma_sparse(
        sigma,
        coaching_root=coaching_root,
        loop_store=loop_store,
        agent_id=agent_id,
        version_id=bootstrap_version,
        generation=state.generation,
        sigma_play=play_limit,
        self_questioning_engine=self_questioning_engine,
        config=config,
    )

    if suite_result and suite_result.get("pipeline_service") and not suite_result.get("proceed"):
        held = {
            "status": "held",
            "reason": "sparse_self_questioning_failed",
            "e_path": {
                "generation": state.generation,
                "parent_version_id": bootstrap_version,
                "sparse_self_questioning": suite_result,
                "sigma_size_before_learn": len(sigma),
            },
        }
        audit_path = coaching_root / ".self-coaching" / "loop" / "e_path_last.json"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(
            json.dumps(held["e_path"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return held

    sigma_size_before_learn = len(sigma)
    result = learn_from_sigma(client, sigma)
    routing = result.get("routing") or {}
    draft_id = result.get("draft_version_id") or routing.get("draft_version_id")
    if draft_id:
        registry.activate(agent_id, draft_id)

    state.generation += 1
    state_store.write_registry_generation(state.generation, agent_id=agent_id)
    loop_store.flush_buffer_stale(state.generation)
    sigma.clear()
    state.support_count = 0
    result["e_path"] = {
        "generation": state.generation,
        "parent_version_id": bootstrap_version,
        "activated_version_id": draft_id,
        "sparse_self_questioning": suite_result,
        "sigma_size_before_learn": sigma_size_before_learn,
    }
    audit_path = coaching_root / ".self-coaching" / "loop" / "e_path_last.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(result["e_path"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
