# coach mode

A **coach service** runs the shared **evolution engine** on **one or more external agents** — periodic evaluation, triggered improvement, and platform deploy. Same **submodules** and adapters as self-coaching mode; different executor and per-agent coaching roots.

Overview: [architecture.md](architecture.md). Shell: `modes/coach/` (planned).

## Purpose in this mode

Operate self-coaching as a **supervisor**: register external agents, schedule **self-evaluation** (via AgentEvals), detect drops, route to **self-learning** or **self-tuning**, gate candidates, and deploy through the production **agent API** — without forking pipeline logic.

## Deploy profile

| Aspect | Typical setup |
|--------|----------------|
| Primary deploy | T2 Coaching API + T3 evolution engine |
| Optional | T1 `modes/self-coaching/` for coach policy in dev |
| Coaching root | **One per subject agent** |
| Observation | AgentEvals (scored), agent API (trajectories), optional LLM proxy |
| Deploy | Agent API skills/versions after deploy gate |
| Config template | `configs/coach.example.yaml` |

## Multi-agent layout

```text
/var/lib/coach/
  agents/<agent_id>/
    experience/
    .self-coaching/
      metrics/eval_metrics.jsonl
      curated/
      reports/eval_runs/
  runs/<improvement_run_id>/
```

## Supervision registry (planned)

`modes/coach/agents.yaml` — per agent: id, model, eval schedule, coaching root, `prefer_skill_first`, optional proxy. See `modes/coach/README.md`. Milestone M5: [roadmap.md](../project/roadmap.md).

## Scheduler (today)

Per agent, cron or interval:

```bash
ROOT=/var/lib/coach/agents/<agent_id>
python -m services.orchestrator record-eval --coaching-root "$ROOT" --agent-id <id> ...
python -m services.orchestrator check-drop --metrics-dir "$ROOT/.self-coaching/metrics" \
  || python -m services.orchestrator run --coaching-root "$ROOT" --run-dir ... --agent-id <id>
```

Typical env: `ORCHESTRATOR_EVAL_BACKEND=agentevals`, `AGENTEVALS_*`, `AGENT_API_*`, `ORCHESTRATOR_TRANSPORT=http`.

## LLM proxy (planned, optional)

**Observation only** — external agents route LLM calls for trajectory capture. **Scored eval stays on AgentEvals.** Does not replace submodules or adapters.

## Improvement and deploy

After [evaluators.md](evaluators.md) gates: skill path → agent API skills; model path → version + activate with rollback pointer. [integrations/production_agent.md](integrations/production_agent.md), [integration-plan.md](../project/integration-plan.md).

## Combined with self-coaching mode

Teams often use **coach** in production and **self-coaching** in dev workspaces — same `modes/self-coaching/` pack, same evolution engine, same AgentEvals/AERL integrations.

## Related

- [self_coaching_mode.md](self_coaching_mode.md)
- [deploy-overview.md#coach-mode](../guides/deploy-overview.md#coach-mode)
- [pipelines.md](pipelines.md)
