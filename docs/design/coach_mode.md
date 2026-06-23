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

`POST /coach/post` — **inbound trigger** from external systems or the supervised subject pushing events to the coach service. This is URL #1 (inbound):

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
| `learn` | E-path only: score tasks → Σ → sparse self-questioning (C06) → learn |
| `play` | Self-play only: C07 batch buffer fill (no learn, no train) |
| `tune` | T-path only: fill buffer + train + holdout gate |
| `full_tick` | Full `clock.run_tick` (E + P + T) |

Note: `payload.action` on scheduler-generated ticks is a **non-binding hint** (`suggested_action`); the coach brain makes the final decision. On HTTP POST, if `COACH_BRIDGE=mock` the action is respected directly; if `COACH_BRIDGE=agent` the live coach brain may override it.

### Coach brain — `AgentCoachBridge` (`COACH_AGENT_URL`)

URL #2 (**outbound** — coach service → coach brain):

```text
Trigger (scheduler | HTTP POST)
  → handle_post_body()
  → CoachAgentBridge.setup_clock()
      └─ mock:  reads payload.action directly (deterministic, CI-safe)
      └─ agent: sends decision prompt + live state to COACH_AGENT_URL,
                parses ClockPlan from response
  → execute_plan()
      └─ hold:      skip
      └─ full_tick: clock.run_tick() (E→P→T)
      └─ learn:     E-path only (scoring + sparse self-questioning + learn)
      └─ play:      C07 batch self-questioning buffer fill only
      └─ tune:      T-path (buffer fill + train + holdout gate)
```

Env:

| Variable | Default | Purpose |
|----------|---------|---------|
| `COACH_BRIDGE` | `mock` | `mock` (rules) or `agent` (live coach brain) |
| `COACH_AGENT_URL` | — | Required when `agent`; base URL for the coach agent |
| `COACH_AGENT_PATH` | `/chat/completions` | Chat endpoint path appended to base URL |
| `COACH_AGENT_API_KEY` | — | Optional bearer token |
| `COACH_AGENT_MODEL` | `coach` | Model name in chat request |
| `COACH_AGENT_TIMEOUT_S` | `60` | HTTP timeout |

The coach brain receives:
- The `_SETUP_PROMPT` with the inbound post JSON
- Live loop state: generation, support set Σ size, buffer B size, tasks processed
- The scheduler hint (if present)

It returns `ClockPlan` JSON: `{"action": "hold"|"...", "reason": "...", "scenario_overrides": {}}`. On failure or unparseable output, the bridge **fails safe to `hold`** (real coach should not burn a tick on uncertainty).

Audit: prompt + raw response + parsed plan written to `{coaching_root}/.self-coaching/coach/audit/{agent_id}/`.

Implementation: [`agent_bridge_live.py`](../../modes/coach/agent_bridge_live.py).

### Subject chat — `subject_chat_url` (live trajectories)

URL #3 (**outbound** — coach platform → supervised subject for trajectories):

```yaml
agents:
  - id: target-agent
    coaching_root: /var/lib/coach/agents/target-agent
    coach_clock:
      enabled: true
      subject_chat_url: http://target-host:8000/chat   # the agent being improved
```

When set, the loop drives the subject for **real** trajectories instead of the
fixture simulator: for each task it POSTs the `user_request` to the subject's
OpenAI-style `/chat/completions`, then shapes the response (assistant content +
`tool_calls`) into the trajectory `xi` the rubric scorer consumes. The subject's
real behavior — including failing to invoke required tools — is scored faithfully.

Env (optional overrides):

| Variable | Default | Purpose |
|----------|---------|---------|
| `SUBJECT_AGENT_PATH` | `/chat/completions` | Chat endpoint path |
| `SUBJECT_AGENT_API_KEY` | — | Optional bearer token |
| `SUBJECT_AGENT_MODEL` | `subject` | Model name in request |
| `SUBJECT_AGENT_TIMEOUT_S` | `60` | HTTP timeout |

- **Cross-coaching**: `subject_chat_url` points at a separate agent runtime.
- **Self-coaching**: `subject_chat_url` points back at the coach agent itself (`= COACH_AGENT_URL`).

When `subject_chat_url` is unset, the loop falls back to fixture task streams
(deterministic, CI-safe). Implementation: [`subject_source.py`](../../modes/self-coaching/subject_source.py).

### Three-URL summary

| URL / Variable | Direction | Role | Status |
|----------------|-----------|------|--------|
| `POST /coach/post` | external → coach service | Inbound event trigger | ✅ shipped |
| `COACH_AGENT_URL` | coach service → coach brain | Decision (ClockPlan) | ✅ shipped |
| `coach_clock.subject_chat_url` | coach platform → subject | Drive tasks / collect trajectories | ✅ shipped |

### Registry config (per-agent)

```yaml
agents:
  - id: my-agent
    coaching_root: /var/lib/coach/agents/my-agent
    coach_clock:
      enabled: true
      interval_s: 1800       # 30 minutes
      scenario: scenarios/clock_loop.json
      subject_chat_url: http://target-host:8000/chat  # Phase 2: live subject
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

## LLM proxy (optional, observation-only)

If the supervised subject's LLM calls route through a proxy (e.g. db_bridge `chat_completions` gateway), the coach platform can capture trajectories passively — scored eval still stays on AgentEvals. Not required for Phase 1 or 2; purely an observability layer.

## Related

[self_coaching_mode.md](self_coaching_mode.md) · [deploy-overview.md](../guides/deploy-overview.md) · [production_agent.md](integrations/production_agent.md)
