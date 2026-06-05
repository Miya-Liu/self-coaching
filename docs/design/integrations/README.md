# Integrations (design)

How external systems connect to the shared **evolution engine** via adapters. One `SelfCoachingClient`, many backends — see [architecture.md](../architecture.md).

| Doc | System | Role in loop |
|-----|--------|----------------|
| [agentevals.md](agentevals.md) | **AgentEvals** | Scored benchmark eval → `EvalMetrics` |
| [production_agent.md](production_agent.md) | **Production agent API** | Trajectories, versions, skills, deploy/rollback |
| [coaching_api.md](coaching_api.md) | **Coaching API (T2)** | HTTP spine for learn / self-play / eval / train |
| [aerl.md](aerl.md) | **AERL** | SFT / GRPO training pipelines |

## Adapter layout

```text
services/orchestrator/
       │
       ▼
SelfCoachingClient  ←── mock-services/client.py
       │
       ├── evaluate / eval_report  → AgentEvals adapter
       ├── learn / self_play       → Coaching API (mock → future)
       ├── train                   → AERL adapter
       └── (trajectory / deploy)    → Production agent adapter (planned)
```

Code: `services/adapters/`. Execution plan: [integration-plan.md](../../project/integration-plan.md).

## Artifacts (operational)

OpenAPI snapshots, fixtures, smoke commands: [integration/](../../integration/) (sibling folder under `docs/`).

## Environment flags

| Variable | Backend |
|----------|---------|
| `ORCHESTRATOR_EVAL_BACKEND` | `mock` \| `agentevals` |
| `ORCHESTRATOR_TRANSPORT` | `module` \| `http` |
| `ORCHESTRATOR_BASE_URL` | T2 Coaching API |
| `AGENTEVALS_*` | AgentEvals |
| `AGENT_API_*` | Production agent |
| `TRAINER_BASE_URL`, `AERL_ROOT` | AERL |
