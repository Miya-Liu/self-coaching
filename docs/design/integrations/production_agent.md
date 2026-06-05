# Production agent API integration

The **production agent platform** provides runtime identity, trajectories, skill bundles, and versioned deploy/rollback for **coach mode**. It does **not** replace AgentEvals for scored benchmarks.

Design context: [coach_mode.md](../coach_mode.md). Implementation plan: [integration-plan.md](../../project/integration-plan.md) Phases 3–4.

## Scoped surface

Integrate only the **self-improvement slice** — not the full agent platform (billing, workflows, etc.).

| Pipeline need | API area | Milestone |
|---------------|----------|-----------|
| Trajectory export | `GET /api/tasks/{task_id}/messages`, `…/all`, `…/stream` | M3 |
| Lineage | `GET /api/agents/{agent_id}`, `…/versions`, active version | M2–M3 |
| Skill bundle | `GET/PUT /api/agents/{agent_id}/skills` | M3 |
| Smoke / canary | `POST /api/agent/start` + stream | M4 |
| Promote candidate | `POST …/versions`, `PUT …/versions/{id}/activate` | M4 |
| Rollback | `POST …/versions/{id}/rollback` | M4 |

## Principles

- **Eval stays on AgentEvals** — do not use agent `/api/agent/start` for scheduled canary scoring.
- **Agent API supplies** trajectory export, version ids for `agent_config`, and deploy/rollback.
- **Human approval** before `activate` in production (deploy gate).

## Coach mode wiring

Each supervised agent maps to:

- `AGENT_ID` — UUID for API routes
- `--candidate` / `--production-candidate` — `version_id`
- Coaching root — local artifacts; API — runtime state

Trajectory export lands in `run_dir/data/trajectories.jsonl` (redacted) for curation.

## Configuration

| Variable | Purpose |
|----------|---------|
| `AGENT_API_BASE_URL` | e.g. staging host |
| `AGENT_API_TOKEN` | Bearer from `POST /api/auth/token` |
| `AGENT_ID` | Supervised subject |

OpenAPI snapshot: `docs/integration/api-snapshots/agent-openapi.json`.

## Deploy manifest

`deploy_manifest.json` records previous `version_id` for rollback. Live deploy replaces dry-run when M4 completes.

## Related

- [agentevals.md](agentevals.md) — scored eval
- [coaching_api.md](coaching_api.md) — learn / train spine
