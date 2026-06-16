# coach mode

A **coach service** runs the shared evolution engine on **external agents** — periodic eval, triggered improvement, platform deploy. Same submodules and adapters as self-coaching mode.

Overview: [architecture.md](architecture.md). Shell: `modes/coach/` (M5 in progress).

## Deploy profile

| Aspect | Setup |
|--------|-------|
| Primary | T2 Coaching API + T3 evolution engine |
| Coaching root | **One per subject agent** |
| Observation | AgentEvals, agent API, optional LLM proxy |
| Deploy | Agent API skills/versions after deploy gate |

## Multi-agent layout

```text
/var/lib/coach/agents/<agent_id>/
  experience/  .self-coaching/metrics/  .self-coaching/curated/
/var/lib/coach/runs/<improvement_run_id>/
```

## Supervision registry

`modes/coach/agents.example.yaml` + `registry.py` + coach clock (`service.py`, `clock.py`, `trigger.py`). Per agent: id, coaching root, eval suites, `coach_clock`, `prefer_skill_first`. See `modes/coach/README.md`.

## Loop patterns

| Pattern | Driver | Detail |
|---------|--------|--------|
| **Scheduler (cron)** | Fixed interval → orchestrator | § below |
| **Coach clock (24×7)** | HTTP/WebSocket post → `clock.run_tick` | § below |
| **Manual** | On-demand `orchestrator run` | Ops interventions |

Loop execution modes: [self_coaching_mode.md](self_coaching_mode.md#loop-execution-modes).

## Coach clock service

The coach service runs as a 24×7 HTTP ingress with an integrated periodic scheduler:

```bash
python modes/coach/service.py serve \
  --registry modes/coach/agents.clock.yaml --bind 127.0.0.1:8768
```

This starts:
1. **HTTP server** — accepts `POST /coach/post` for on-demand ticks
2. **ClockScheduler** — periodically ticks each enabled agent at its configured `interval_s`

Entry points (after `pip install -e ".[coach]"`):
- `coach-serve serve --registry agents.yaml --bind 0.0.0.0:8768`
- `coach-clock run --root /path/to/coaching --scenario scenarios/clock_loop.json`

### Periodic scheduler

Each agent in the registry with `coach_clock.enabled: true` gets scheduled at `interval_s` (default 1800s / 30 min). Features:
- Per-agent lock — no concurrent ticks on the same agent
- Tick dispatch in worker threads — non-blocking scheduler loop
- Structured tick log — `{coaching_root}/.self-coaching/coach/ticks/tick_log.jsonl`
- Graceful shutdown — drains in-flight ticks on SIGINT

### On-demand POST

`POST /coach/post`:

```json
{
  "agent_id": "support-bot-prod",
  "event": "session_complete",
  "payload": { "action": "full_tick", "reason": "failures in trailing window" }
}
```

| `payload.action` | Behavior |
|------------------|----------|
| `hold` | Record only |
| `learn` / `play` / `tune` | Partial routes |
| `full_tick` | Full `clock.run_tick` |

Mock bridge when `agent_chat_url` unset: `MockCoachAgentBridge`. Production: [agent_bridge.py](../../modes/coach/agent_bridge.py).

### Registry config (per-agent)

```yaml
agents:
  - id: my-agent
    coaching_root: /var/lib/coach/agents/my-agent
    coach_clock:
      enabled: true
      interval_s: 1800       # 30 minutes
      scenario: scenarios/clock_loop.json
```

Smoke: `python scripts/clock_loop_smoke.py` · `pytest tests/test_coach_service.py` · `pytest tests/test_scheduler.py`

## Scheduler (cron)

```bash
ROOT=/var/lib/coach/agents/<agent_id>
python -m services.orchestrator record-eval --coaching-root "$ROOT" --agent-id <id> ...
python -m services.orchestrator check-drop --metrics-dir "$ROOT/.self-coaching/metrics" \
  || python -m services.orchestrator run --coaching-root "$ROOT" --run-dir ... --agent-id <id>
```

Env: `ORCHESTRATOR_EVAL_BACKEND=agentevals`, `AGENTEVALS_*`, `ORCHESTRATOR_TRANSPORT=http`.

## LLM proxy (planned)

Observation only — scored eval stays on AgentEvals.

## Related

[self_coaching_mode.md](self_coaching_mode.md) · [deploy-overview.md](../guides/deploy-overview.md) · [production_agent.md](integrations/production_agent.md)
