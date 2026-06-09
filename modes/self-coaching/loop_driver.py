# SPDX-License-Identifier: MIT
"""Loop driver: task stream, Sigma/B stores, E-path and T-path evolution."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

_SC_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _SC_ROOT.parents[1]
_MOCK_SERVICES = _REPO_ROOT / "mock-services"
for _path in (_SC_ROOT, _SC_ROOT / "self-learning", _MOCK_SERVICES, _REPO_ROOT):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from free_time import FreeTimeSimulator  # noqa: E402
from loop_store import LoopStore, SupportEntry, read_jsonl  # noqa: E402
from state import LoopState, LoopStateStore  # noqa: E402
from trajectory_scorer import RubricResult, score_trajectory  # noqa: E402
from trajectory_simulator import simulate_trajectory  # noqa: E402

DEFAULT_TAU_FAIL = 0.75
DEFAULT_SIGMA_MIN = 3
DEFAULT_SIGMA_PLAY = 3
DEFAULT_BATCH_SIZE = 4
DEFAULT_AGENT_ID = "demo-agent"
DEFAULT_TASK_STREAM = _MOCK_SERVICES / "fixtures" / "task_stream" / "tool_use_v1.jsonl"
THRESHOLDS_PATH = _REPO_ROOT / "services" / "orchestrator" / "config" / "thresholds.json"
HOLDOUT_SUITE_ID = "tool-use-holdout"


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


@dataclass(frozen=True)
class TaskScore:
    task_id: str
    score: float
    rubric: RubricResult
    routed_to: str
    trajectory_ref: str


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


def route_score(score: float, *, tau_fail: float | None = None) -> str:
    threshold = DEFAULT_TAU_FAIL if tau_fail is None else tau_fail
    return "support" if score < threshold else "buffer"


def failure_event_text(task_id: str, score: float, rubric: RubricResult) -> str:
    breakdown = rubric["breakdown"]
    if not breakdown["tools_ok"]:
        missing = ", ".join(breakdown["missing_tools"]) or "expected tools"
        return f"Task {task_id} missing tools: {missing} (score={score:.2f})"
    return f"Task {task_id} answer incomplete after tool use (score={score:.2f})"


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
    self_play_engine: Any | None = None,
) -> dict[str, Any] | None:
    """C06: sparse failure-conditioned self-play augments Sigma before E.learn."""
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

    sp_url = _self_play_base_url()
    if sp_url:
        from mock_self_play import generate_suite_via_http

        result = generate_suite_via_http(sp_url, body)
    else:
        from mock_self_play import MockSelfPlayEngine

        engine = self_play_engine or MockSelfPlayEngine(coaching_root)
        result = engine.generate_suite(**body)

    staging = coaching_root / ".self-coaching" / "curated" / "staging.jsonl"
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
    self_play_engine: Any | None = None,
) -> dict[str, Any] | None:
    """E-path: optional sparse self-play, learn, activate draft, bump g, flush stale B."""
    if not sigma:
        return None

    bootstrap_version = str(registry.get_agent(agent_id)["active_version_id"])
    play_limit = sigma_play_threshold() if sigma_play is None else sigma_play
    suite_result = augment_sigma_sparse(
        sigma,
        coaching_root=coaching_root,
        loop_store=loop_store,
        agent_id=agent_id,
        version_id=bootstrap_version,
        generation=state.generation,
        sigma_play=play_limit,
        self_play_engine=self_play_engine,
    )

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
        "sparse_self_play": suite_result,
        "sigma_size_before_learn": sigma_size_before_learn,
    }
    return result


def fill_buffer_batch(
    *,
    coaching_root: Path,
    loop_store: LoopStore,
    registry: Any,
    agent_id: str,
    generation: int,
    n: int,
    capability: str = "tool_use",
    self_play_engine: Any | None = None,
) -> dict[str, Any]:
    """C07: top up tuning buffer B via batch self-play."""
    if n <= 0:
        return {"status": "skipped", "count": 0}

    version_id = str(registry.get_agent(agent_id)["active_version_id"])
    sp_url = _self_play_base_url()
    if sp_url:
        from mock_self_play import self_play_via_http

        result = self_play_via_http(sp_url, coaching_root=coaching_root, capability=capability, n=n)
    else:
        from mock_self_play import MockSelfPlayEngine

        engine = self_play_engine or MockSelfPlayEngine(coaching_root)
        result = engine.generate_batch(coaching_root=coaching_root, capability=capability, n=n)

    staging = coaching_root / ".self-coaching" / "curated" / "staging.jsonl"
    for traj in read_jsonl(staging):
        loop_store.append_buffer_from_trajectory(
            traj,
            generation=generation,
            version_id=version_id,
        )
    return result


def _holdout_metrics(
    agentevals_engine: Any,
    *,
    agent_id: str,
    version_id: str,
    coaching_root: Path,
) -> Any:
    import time

    from services.orchestrator.eval_metrics import EvalMetrics

    version = agentevals_engine.registry.get_version(agent_id, version_id)
    model_id = str((version.get("components") or {}).get("model_id", version_id))
    skill_bundle = str((version.get("components") or {}).get("skill_bundle_version", "unknown"))
    created = agentevals_engine.create_run(
        {
            "suite_id": holdout_suite_id(),
            "num_trials": 1,
            "agent_config": {
                "agent_id": agent_id,
                "version_id": version_id,
                "baseline_version_id": version_id,
            },
        }
    )
    run_id = str(created["id"])
    deadline = time.time() + 5.0
    detail: dict[str, Any] = created
    while time.time() < deadline:
        detail = agentevals_engine.get_run(run_id)
        if str(detail.get("status")) == "succeeded":
            break
        time.sleep(0.02)
    if str(detail.get("status")) != "succeeded":
        raise RuntimeError(f"mock holdout eval run {run_id} did not succeed")

    metrics = detail.get("metrics") or {}
    num_trials = max(int(detail.get("num_trials") or 1), 1)
    overall = float(metrics.get("overall", 0.0))
    return EvalMetrics(
        run_id=run_id,
        agent_id=agent_id,
        skill_bundle_version=skill_bundle,
        model_checkpoint_id=model_id,
        score=overall,
        baseline_score=overall,
        cost_per_task=float(metrics.get("cost_usd", 0.0)) / num_trials,
        latency_p95_ms=float(metrics.get("latency_p95_ms", 800.0)),
        safety_pass_rate=float(metrics.get("safety", 1.0)),
        task_scores={
            key: float(value)
            for key, value in metrics.items()
            if key not in {"overall", "pass_rate", "cost_usd", "latency_p95_ms", "safety"} and isinstance(value, (int, float))
        },
        split="holdout",
        raw={"run_detail": detail},
    )


def run_t_path(
    *,
    client: LoopClient,
    registry: Any,
    loop_store: LoopStore,
    state: LoopState,
    coaching_root: Path,
    agent_id: str,
    beta: int | None = None,
    pipeline: str = "sft",
    candidate_model_id: str | None = None,
    self_play_engine: Any | None = None,
    agentevals_engine: Any | None = None,
) -> dict[str, Any] | None:
    """T-path: fill B, train, holdout gate, optional hot-swap, consume B."""
    from mock_agentevals import MockAgentEvalsEngine
    from services.orchestrator.drop_detector import check_promotion, load_thresholds

    batch_size = batch_size_threshold() if beta is None else beta
    active_rows = loop_store.active_buffer_rows()
    if len(active_rows) < batch_size:
        fill_buffer_batch(
            coaching_root=coaching_root,
            loop_store=loop_store,
            registry=registry,
            agent_id=agent_id,
            generation=state.generation,
            n=batch_size - len(active_rows),
            self_play_engine=self_play_engine,
        )
        active_rows = loop_store.active_buffer_rows()

    if len(active_rows) < batch_size:
        return None

    production_version = str(registry.get_agent(agent_id)["active_version_id"])
    production_version_doc = registry.get_version(agent_id, production_version)
    base_model = str((production_version_doc.get("components") or {}).get("model_id", "mock-base"))

    dataset_path = loop_store.export_train_dataset(active_rows)
    train_result = client.train(pipeline=pipeline, dataset=str(dataset_path), base_model=base_model)
    trained_model = candidate_model_id or str(train_result.get("candidate") or "mock-sft-candidate")

    draft = registry.create_version(
        agent_id,
        parent_version_id=production_version,
        components={"model_id": trained_model},
        artifacts={"training_run_id": train_result.get("run_id")},
        source="mock_aerl",
    )
    candidate_version_id = str(draft["version_id"])

    eval_engine = agentevals_engine or MockAgentEvalsEngine(coaching_root)
    current_metrics = _holdout_metrics(
        eval_engine,
        agent_id=agent_id,
        version_id=production_version,
        coaching_root=coaching_root,
    )
    candidate_metrics = _holdout_metrics(
        eval_engine,
        agent_id=agent_id,
        version_id=candidate_version_id,
        coaching_root=coaching_root,
    )

    thresholds = load_thresholds(THRESHOLDS_PATH)
    ok, gate_reasons = check_promotion(current_metrics, candidate_metrics, thresholds)

    consumed = 0
    if ok:
        registry.activate(agent_id, candidate_version_id)
        consumed = loop_store.mark_buffer_consumed(
            task_ids={str(row.get("task_id")) for row in active_rows},
        )

    return {
        "promoted": ok,
        "gate_reasons": gate_reasons,
        "train_result": train_result,
        "candidate_version_id": candidate_version_id,
        "production_version_id": production_version,
        "current_eval": current_metrics.to_dict(),
        "candidate_eval": candidate_metrics.to_dict(),
        "buffer_consumed": consumed,
        "buffer_preserved": not ok,
    }


def process_task(
    tau: dict[str, Any],
    *,
    loop_store: LoopStore,
    generation: int,
    version_id: str,
    tau_fail: float | None = None,
) -> tuple[TaskScore, dict[str, Any], SupportEntry | None]:
    xi = simulate_trajectory(tau)
    rubric = score_trajectory(xi, tau)
    task_id = str(tau.get("task_id") or "")
    trajectory_id, trajectory_ref = loop_store.save_trajectory(task_id, xi, rubric_result=rubric)
    routed_to = route_score(rubric["score"], tau_fail=tau_fail)

    support_entry: SupportEntry | None = None
    if routed_to == "support":
        event_text = failure_event_text(task_id, rubric["score"], rubric)
        support_entry = SupportEntry(
            task_id=task_id,
            trajectory_id=trajectory_id,
            trajectory_ref=trajectory_ref,
            score=rubric["score"],
            event_text=event_text,
        )
        loop_store.append_support(
            task_id=task_id,
            generation=generation,
            version_id=version_id,
            trajectory_id=trajectory_id,
            trajectory_ref=trajectory_ref,
            score=rubric["score"],
            event_text=event_text,
        )
    else:
        loop_store.append_buffer(
            task_id=task_id,
            generation=generation,
            version_id=version_id,
            score=rubric["score"],
            trajectory_ref=trajectory_ref,
        )

    result = TaskScore(
        task_id=task_id,
        score=rubric["score"],
        rubric=rubric,
        routed_to=routed_to,
        trajectory_ref=trajectory_ref,
    )
    return result, xi, support_entry


def default_client(coaching_root: str | Path) -> LoopClient:
    from client import ModuleClient

    return ModuleClient(coaching_root)


def run_tasks(
    coaching_root: str | Path,
    *,
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
    self_play_engine: Any | None = None,
    agentevals_engine: Any | None = None,
) -> tuple[list[TaskScore], LoopState]:
    """Process fixture tasks; route Sigma/B; run E-path and optional T-path."""
    from mock_agent_registry import AgentRegistry

    stream_path = Path(task_stream_path or DEFAULT_TASK_STREAM)
    root = Path(coaching_root).resolve()
    store = LoopStateStore(root)
    loop_store = LoopStore(root)
    state = store.load()
    state = store.sync_generation_from_registry(state, agent_id=agent_id or loop_agent_id())

    agent = agent_id or loop_agent_id()
    registry = AgentRegistry(root)
    registry.ensure_agent(agent)
    if store.registry_generation(agent_id=agent) == 0 and state.generation == 0:
        store.write_registry_generation(0, agent_id=agent)

    loop_client = client if client is not None else default_client(root)
    threshold = tau_fail_threshold() if tau_fail is None else tau_fail
    sigma_threshold = sigma_min_threshold() if sigma_min is None else sigma_min
    free_time = FreeTimeSimulator(idle_after=idle_after)

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
                sigma_play=sigma_play,
                self_play_engine=self_play_engine,
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
                beta=beta,
                candidate_model_id=candidate_model_id,
                self_play_engine=self_play_engine,
                agentevals_engine=agentevals_engine,
            )
            state.buffer_count = len(loop_store.active_buffer_rows())

    store.save(state)
    return results, state


def count_store_rows(coaching_root: str | Path) -> tuple[int, int]:
    loop_store = LoopStore(coaching_root)
    return len(read_jsonl(loop_store.support_path)), len(read_jsonl(loop_store.buffer_path))
