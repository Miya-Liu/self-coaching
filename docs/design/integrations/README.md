# Integrations (design)

How external systems connect to the shared **evolution engine** via adapters. One `SelfCoachingClient`, many backends — see [architecture.md](../architecture.md).

| Doc | System | Role in loop |
|-----|--------|----------------|
| [agentevals.md](agentevals.md) | **AgentEvals** | Scored benchmark eval → `EvalMetrics` |
| [production_agent.md](production_agent.md) | **Production agent API** | Trajectories, versions, skills, deploy/rollback |
| [coaching_api.md](coaching_api.md) | **Coaching API (T2)** | HTTP spine for learn / self-play / eval / train |
| [aerl.md](aerl.md) | **AERL** | SFT / GRPO training pipelines |
| [db_bridge_remote_shell.md](db_bridge_remote_shell.md) | **db_bridge remote shell** | CLI command dispatch to AReaL GPU host via Supabase |
| [areal_cli_training_request.md](areal_cli_training_request.md) | **AReaL training script** | `TRAINING_COMPLETE` stdout marker (external request) |

## Adapter layout

```text
services/orchestrator/
       |
       v
SelfCoachingClient  <-- mock-services/client.py
       |
       +-- evaluate / eval_report  -> AgentEvals adapter (live: migration M1 PASS)
       +-- learn / self_play       -> Coaching API mock; learn evolve API migration M2 (spec only)
       +-- train                   -> mock_aerl | aerl HTTP | cli (db_bridge); see [cli-training-implementation.md](../../project/cli-training-implementation.md)
       +-- (trajectory / deploy)    -> Production agent adapter (planned)
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
