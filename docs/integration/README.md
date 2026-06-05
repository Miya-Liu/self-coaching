# Integration artifacts

Operational artifacts for adapter development. **Design docs:** [design/integrations/](../design/integrations/). **Execution plan:** [integration-plan.md](../project/integration-plan.md).

| Path | Purpose | Status |
|------|---------|--------|
| `api-snapshots/agent-openapi.json` | Production agent OpenAPI | **Captured** 2026-05-29 |
| `api-snapshots/agentevals-openapi.json` | AgentEvals OpenAPI | **Pending** |
| `mapping.md` | `RunDetail` → `EvalMetrics` field table | **Draft** — design in [agentevals.md](../design/integrations/agentevals.md) |
| `services/adapters/` | AgentEvals eval client + orchestrator wiring | Phase 1 |

## Refresh snapshots

```bash
bash scripts/export-integration-snapshots.sh
```

Environment: `AGENT_API_BASE_URL`, `AGENTEVALS_BASE_URL`.
