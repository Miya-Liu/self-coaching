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

Inbound post drives one evolution tick (E → sparse/batch play → T):

```bash
python modes/coach/service.py serve \
  --registry modes/coach/agents.yaml --bind 0.0.0.0:8768
```

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

Smoke: `python scripts/clock_loop_smoke.py` · `pytest tests/test_coach_service.py`

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
