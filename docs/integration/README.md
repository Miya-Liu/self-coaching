# Integration artifacts

Operational artifacts for adapter development. **Design docs:** [design/integrations/](../design/integrations/). **Execution plan:** [integration-plan.md](../project/integration-plan.md). **Loop migration:** [mock-to-real-migration.md](../project/mock-to-real-migration.md).

| Path | Purpose | Status |
|------|---------|--------|
| `api-snapshots/agent-openapi.json` | Production agent OpenAPI | **Captured** 2026-05-29 |
| `api-snapshots/agentevals-openapi.json` | AgentEvals OpenAPI | **Captured** 2026-06-10 |
| `api-snapshots/self-learning-openapi.json` | Production learner (review API) | **Placeholder** 2026-06-15 (M2.0) |
| `api-snapshots/self-questioning-openapi.json` | Self-play generator | **Pending** — migration M3 |
| `api-snapshots/aerl-openapi.json` | AERL trainer (runs, rollout, rewards) | **Pending** — migration M4.0 · [spec](../project/self-tuning-trainer-api-plan.md) |
| `mapping.md` | Field mapping tables | **Active** (AgentEvals); self-learning § **pending** M2.2 |
| `services/adapters/` | HTTP clients + orchestrator wiring | AgentEvals **shipped**; learn adapter **pending** M2 |

## Refresh snapshots

```bash
bash scripts/export-integration-snapshots.sh
```

Environment: `AGENT_API_BASE_URL`, `AGENTEVALS_BASE_URL`.
