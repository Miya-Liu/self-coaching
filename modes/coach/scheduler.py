# SPDX-License-Identifier: MIT
"""Coach clock scheduler — periodic per-agent evolution ticks with locking.

Runs as a background thread alongside the HTTP/WebSocket ingress in service.py.
Each registered agent with coach_clock.enabled=True gets scheduled at its
configured interval. A per-agent lock prevents concurrent ticks.

Usage:
    scheduler = ClockScheduler(registry_path, bridge=bridge)
    scheduler.start()   # non-blocking, spawns timer threads
    scheduler.stop()    # graceful drain, waits for in-flight ticks
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG = logging.getLogger("coach.scheduler")

DEFAULT_INTERVAL_S = 1800.0  # 30 minutes


@dataclass
class TickEvent:
    """Structured record of one clock tick."""

    agent_id: str
    tick_id: str
    started_at: str
    finished_at: str = ""
    duration_s: float = 0.0
    action: str = "unknown"
    outcome: str = "unknown"  # completed | skipped | error
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "tick_id": self.tick_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "action": self.action,
            "outcome": self.outcome,
            "detail": self.detail,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_tick_event(coaching_root: Path, event: TickEvent) -> None:
    """Append a tick event to the per-agent tick log (JSONL)."""
    log_dir = coaching_root / ".self-coaching" / "coach" / "ticks"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "tick_log.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


class AgentTickState:
    """Per-agent lock and metadata for the scheduler."""

    def __init__(self, agent_id: str, interval_s: float):
        self.agent_id = agent_id
        self.interval_s = interval_s
        self.lock = threading.Lock()
        self.last_tick_at: float = 0.0
        self.tick_count: int = 0
        self.running: bool = False

    def time_until_next(self) -> float:
        elapsed = time.time() - self.last_tick_at
        return max(0.0, self.interval_s - elapsed)

    def should_tick(self) -> bool:
        return time.time() - self.last_tick_at >= self.interval_s


class ClockScheduler:
    """Periodic scheduler that ticks each enabled agent at its configured interval.

    Thread-safe: one tick per agent at a time (per-agent lock). The scheduler
    itself runs in a single background thread that wakes up, checks which agents
    are due, and dispatches ticks (each in a short-lived thread to avoid blocking
    the scheduler loop).
    """

    def __init__(
        self,
        registry_path: str | Path,
        *,
        bridge: Any | None = None,
        client: Any | None = None,
        tick_fn: Any | None = None,
    ):
        self._registry_path = Path(registry_path)
        self._bridge = bridge
        self._client = client
        self._tick_fn = tick_fn  # override for testing
        self._agents: dict[str, AgentTickState] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._tick_threads: list[threading.Thread] = []

    def _load_agents(self) -> None:
        """Load/reload agent configs from registry."""
        from coach.registry import load_registry

        agents = load_registry(self._registry_path)
        for agent in agents:
            if agent.coach_clock is None or not agent.coach_clock.enabled:
                continue
            interval = getattr(agent.coach_clock, "interval_s", None) or DEFAULT_INTERVAL_S
            if agent.id not in self._agents:
                self._agents[agent.id] = AgentTickState(agent.id, interval)
                LOG.info("scheduler: registered agent %s (interval=%ss)", agent.id, interval)
            else:
                self._agents[agent.id].interval_s = interval

    def start(self) -> None:
        """Start the scheduler background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._load_agents()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="coach-scheduler", daemon=True)
        self._thread.start()
        LOG.info("scheduler: started (%d agents)", len(self._agents))

    def stop(self, timeout: float = 10.0) -> None:
        """Signal stop and wait for in-flight ticks to drain."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        # Wait for in-flight tick threads
        for t in self._tick_threads:
            t.join(timeout=5.0)
        self._tick_threads.clear()
        LOG.info("scheduler: stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def agent_states(self) -> dict[str, dict[str, Any]]:
        """Return status snapshot for health/debug endpoints."""
        return {
            agent_id: {
                "interval_s": state.interval_s,
                "last_tick_at": state.last_tick_at,
                "tick_count": state.tick_count,
                "running": state.running,
                "time_until_next_s": state.time_until_next(),
            }
            for agent_id, state in self._agents.items()
        }

    def trigger_now(self, agent_id: str) -> dict[str, Any]:
        """Manually trigger a tick for an agent (from HTTP POST). Returns immediately."""
        state = self._agents.get(agent_id)
        if state is None:
            raise KeyError(f"agent {agent_id!r} not registered in scheduler")
        if not state.lock.acquire(blocking=False):
            return {"status": "busy", "agent_id": agent_id, "message": "tick already in progress"}
        try:
            state.running = True
            result = self._execute_tick(agent_id, state, source="manual")
        finally:
            state.running = False
            state.lock.release()
        return result

    def _loop(self) -> None:
        """Main scheduler loop — check due agents every second."""
        while not self._stop_event.is_set():
            for agent_id, state in list(self._agents.items()):
                if self._stop_event.is_set():
                    break
                if state.should_tick() and not state.running:
                    self._dispatch_tick(agent_id, state)
            self._stop_event.wait(timeout=1.0)

    def _dispatch_tick(self, agent_id: str, state: AgentTickState) -> None:
        """Dispatch a tick in a short-lived thread (non-blocking)."""
        if not state.lock.acquire(blocking=False):
            return  # Already running
        state.running = True

        def _worker() -> None:
            try:
                self._execute_tick(agent_id, state, source="scheduled")
            finally:
                state.running = False
                state.lock.release()

        t = threading.Thread(target=_worker, name=f"tick-{agent_id}", daemon=True)
        t.start()
        self._tick_threads.append(t)
        # Clean up finished threads
        self._tick_threads = [t for t in self._tick_threads if t.is_alive()]

    def _execute_tick(self, agent_id: str, state: AgentTickState, *, source: str) -> dict[str, Any]:
        """Run one evolution tick for an agent."""
        import uuid
        tick_id = f"tick-{uuid.uuid4().hex[:8]}"
        started = _utc_now()
        t0 = time.time()

        event = TickEvent(agent_id=agent_id, tick_id=tick_id, started_at=started)

        try:
            if self._tick_fn is not None:
                result = self._tick_fn(agent_id)
            else:
                result = self._run_default_tick(agent_id)

            event.action = result.get("plan", {}).get("action", "full_tick") if isinstance(result, dict) else "full_tick"
            event.outcome = "completed"
            event.detail = {"source": source, "result_keys": list(result.keys()) if isinstance(result, dict) else []}
            state.tick_count += 1
            state.last_tick_at = time.time()
            LOG.info("tick %s agent=%s outcome=completed duration=%.1fs", tick_id, agent_id, time.time() - t0)
        except Exception as exc:
            event.outcome = "error"
            event.detail = {"source": source, "error": str(exc)}
            LOG.error("tick %s agent=%s outcome=error: %s", tick_id, agent_id, exc)
            result = {"status": "error", "error": str(exc)}

        event.finished_at = _utc_now()
        event.duration_s = round(time.time() - t0, 2)

        # Write tick event log
        try:
            from coach.trigger import resolve_coaching_root, find_agent
            from coach.registry import load_registry
            agents = load_registry(self._registry_path)
            agent = find_agent(agents, agent_id)
            coaching_root = resolve_coaching_root(agent)
            _append_tick_event(coaching_root, event)
        except Exception:
            LOG.debug("could not write tick event for %s", agent_id, exc_info=True)

        return result

    def _run_default_tick(self, agent_id: str) -> dict[str, Any]:
        """Run the standard coach tick pipeline via trigger.handle_post_body."""
        from coach.trigger import handle_post_body

        body = {
            "agent_id": agent_id,
            "event": "scheduled_tick",
            # suggested_action is a non-binding hint: MockCoachAgentBridge ignores
            # it (defaults to full_tick for CI determinism); AgentCoachBridge reads
            # it as a hint but the coach brain makes the final decision.
            "payload": {"suggested_action": "full_tick", "reason": "scheduler interval elapsed"},
        }
        return handle_post_body(body, self._registry_path, self._bridge, client=self._client)
