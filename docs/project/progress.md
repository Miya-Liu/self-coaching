# Integration progress

Status of **evolution engine** components against [roadmap.md](roadmap.md). Design: [pipelines.md](../design/pipelines.md), [architecture.md](../design/architecture.md).

**Active deploy target:** **T1 — Skill pack** (Skill mode, M0). T2/T3 support Coach mode and optional Skill-mode automation.

## Component status

| Component | Milestone | Status | MVP in repo | Next deliverable |
|-----------|-----------|--------|-------------|------------------|
| **Production agent** | M3–M4 | Adapter planned | `client.py` consumers | Trajectory + deploy adapter |
| **Trajectory store** | M3 | Not wired | `.self-coaching/events/*.jsonl` | `POST /trajectories` or extended learn payload |
| **Auto-evaluation** | M1–M2 | Partial | Mock eval + **`EvalMetrics`**; AgentEvals adapter | Live smoke + `agentevals-openapi.json` snapshot |
| **Drop detector** | M1 | **Done** | `python -m services.orchestrator check-drop` | Wire to coach scheduler (M5) |
| **Evolution engine** | M1 | **Done** | `services/orchestrator/`, `scripts/run-orchestrator.sh` | Real `pipeline.yaml` shell hooks (M2+) |
| **Curation** | M3 | Stub | Mock self-play only | `scripts/curate_data.py` + PII flags |
| **Self-play** | M2 | Mock | `POST /self-play/generate` | Remote generator adapter |
| **Skill learning** | M3 | Policy only | `learn()` + SKILLs | Git-tagged bundle in run manifest |
| **Model training** | M2 | Partial | Shell + mock `train()` | AERL HTTP adapter + async runs |
| **Candidate evaluation** | M1 | Partial | Holdout `candidate_eval.json` + promotion gates | Real holdout suite + cost/latency |
| **Deployment** | M1 dry / M4 live | **Dry-run** | `deploy_manifest.json` (`canary_fraction: 0`) | Canary + rollback via agent API |
| **Version management** | M1 | Partial | `improvement_run_manifest.json` | Registry query by `agent_id` |
| **Coach mode shell** | M5 | Not started | `modes/coach/README.md` | Supervision registry + scheduler |
| **LLM proxy** | M5 | Not started | — | Optional observation adapter |

## Deploy targets and modes

| Target | Mode | Ready? | Notes |
|--------|------|--------|-------|
| **T1 — Skill pack** | Skill | **Active** | `install-skill-pack.sh`, `modes/skill/SKILL_PACK_VERSION` 0.2.0 |
| **T2 — Coaching API** | Coach | Deferred | Mock ready; adopt for coach mode |
| **T3 — Evolution engine** | Coach (+ Skill optional) | M1 done | Not required for T1-only Skill mode |

## Completed (integration layer)

- **2026-05-29:** M0 exit verified locally (`doctor.sh` + `install-skill-pack.sh . --with-mock`); production agent OpenAPI snapshot in `docs/integration/api-snapshots/agent-openapi.json`
- Phase 1 mock fixes: `--host`, `ValueError` for bad pipelines
- HTTP: bearer auth, idempotency, body size cap
- Client: `api_key`, headers, `AuthError`, CLI JSON parsing
- CI: contract sync, evolution engine smoke, mock `run-all`
- Docs: `design/` restructure (architecture, skill_mode, coach_mode, pipelines, evaluators, integrations)

## Architecture rule

**One evolution engine, one `SelfCoachingClient`, many adapters:** orchestrator → client → OpenAPI service → {mock | AgentEvals | AERL | production agent API}. Do not add parallel integration APIs per component.

## Related

- [Documentation index](../README.md)
- [design/README.md](../design/README.md) — design index
- [Integration plan](integration-plan.md) — adapter implementation
- [Roadmap](roadmap.md) — M0–M5 milestones
- [pipelines.md](../design/pipelines.md) — evolution engine specification
