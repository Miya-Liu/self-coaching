# Integration artifacts

**Phase 0** of the [integration plan](../project/integration-plan.md).

| Path | Purpose | Status |
|------|---------|--------|
| `api-snapshots/agent-openapi.json` | Production agent API (`GET /openapi.json`) | **Captured** 2026-05-29 from `http://10.110.158.146:8000` |
| `api-snapshots/agentevals-openapi.json` | AgentEvals API (`GET /openapi.json`) | **Pending** — export when `AGENTEVALS_BASE_URL` (default `:8080`) is up |
| `mapping.md` (planned) | Field-level `RunDetail.metrics` → `EvalMetrics` | Not started |

## Refresh snapshots

```bash
bash scripts/export-integration-snapshots.sh
```

Environment overrides: `AGENT_API_BASE_URL`, `AGENTEVALS_BASE_URL`.

Commit snapshots here for adapter fixtures and optional CI OpenAPI diff.
