# Integration progress

Status of [`pipeline.md`](pipeline.md) components against the [deployment roadmap](roadmap.md).

**Active deploy target:** **T1 — Skill pack** (M0). T2/T3 are optional; see [`deploy-t1-skill-pack.md`](deploy-t1-skill-pack.md).

## Component status

| Component | Milestone | Status | MVP in repo | Next deliverable |
|-----------|-----------|--------|-------------|------------------|
| **Production agent** | — | Out of scope | `client.py` consumers | Trajectory ingest SDK (agent-side) |
| **Trajectory store** | M3 | Not wired | `.self-coaching/events/*.jsonl` | `POST /trajectories` or extended learn payload |
| **Auto-evaluation** | M1–M2 | Partial | Mock eval + **`EvalMetrics`** (`record-eval` CLI) | AgentEvals adapter → same schema |
| **Drop detector** | M1 | **Done** | `python -m services.orchestrator check-drop` | Wire to scheduler/cron |
| **Improvement orchestrator** | M1 | **Done** | `services/orchestrator`, `scripts/run-orchestrator.sh` | Real `pipeline.yaml` shell hooks (M2+) |
| **Curation** | M3 | Stub | Mock self-play only | `scripts/curate_data.py` + PII flags |
| **Self-play** | M2 | Mock | `POST /self-play/generate` | Remote generator adapter |
| **Skill learning** | M3 | Policy only | `learn()` + SKILLs | Git-tagged bundle in run manifest |
| **Model training** | M2 | Partial | Shell + mock `train()` | AERL HTTP adapter + async runs |
| **Candidate evaluation** | M1 | Partial | Holdout `candidate_eval.json` + promotion gates in `decision.json` | Real holdout suite + cost/latency |
| **Deployment** | M1 dry / M4 live | **Dry-run** | `deploy_manifest.json` (`canary_fraction: 0`) | Canary script + rollback |
| **Version management** | M1 | Partial | `improvement_run_manifest.json`, skill `bundle.json` stub | Registry query by `agent_id` |

## Deploy targets

| Target | Ready? | Notes |
|--------|--------|-------|
| **T1 — Skill pack** | **Active** | `install-skill-pack.sh`, `SKILL_PACK_VERSION` 0.2.0, `deploy-t1-skill-pack.md` |
| **T2 — Coaching API** | Deferred | Mock ready; adopt when agents need HTTP |
| **T3 — Pipeline** | Optional | M1 orchestrator available; not required for T1 |

## Completed (integration layer)

- Phase 1 mock fixes: `--host`, `ValueError` for bad pipelines
- HTTP: bearer auth, idempotency, body size cap
- Client: `api_key`, headers, `AuthError`, CLI JSON parsing
- Tests: 36+ pytest cases; CI contract sync + smoke `run-all`
- Docs: `pipeline.md`, `roadmap.md`, `production-deployment.md`

## Architecture rule

**One spine, many adapters:** orchestrator → `SelfCoachingClient` → OpenAPI service → {mock | AgentEvals | AERL}. Do not add parallel “integration APIs” per component.

## Related

- [Integration plan](integration-plan.md) — production agent + AgentEvals adapters (step-wise)
- [Roadmap](roadmap.md) — M0–M4 milestones
- [Production deployment](production-deployment.md) — T1 / T2 / T3 how-to
- [Pipeline design](pipeline.md) — full loop specification
