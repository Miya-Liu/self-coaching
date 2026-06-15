# Integration progress

**Authoritative status** for components and migration phases. Design: [pipelines.md](../design/pipelines.md).

**Active deploy target:** T1 skill pack. T2/T3 optional for coach mode.

## Component status

| Component | Status | In repo | Next |
|-----------|--------|---------|------|
| Auto-evaluation | **Done** | Live AgentEvals + mock | Opt-in CI job |
| Drop detector | **Done** | `check-drop` CLI | Coach scheduler (M5) |
| Evolution engine | **Done** | `services/orchestrator/` | Real pipeline hooks (M2+) |
| Self-coaching loop demo | **P0–P4 done** | `mock-self-coaching-demo.sh` | P5 split-stack CI |
| Self-play | Mock stub | `mock_self_play.py` | Remote generator adapter |
| Skill learning | **M2.1 done** | mock routes + evolve API | M2.2 adapters |
| Model training | Mock + partial | `mock_aerl.py`, `aerl_client.py` | M4 production trainer |
| Coach mode shell | **In progress** | registry, clock, service | Production agent bridge |
| Deployment | Dry-run | `deploy_manifest.json` | Canary + rollback (M4) |
| LLM proxy | Not started | — | M5 optional |

## Deploy targets

| Target | Ready? | Notes |
|--------|--------|-------|
| **T1** skill pack | **Active** | v0.3.1, `install-skill-pack.sh --hermes` |
| **T2** Coaching API | Mock complete | Production M2 deferred |
| **T3** evolution engine | M1 done | Not required for T1-only |

## Migration M2 — self-learning

Spec: [self-learning-review-agent-plan.md](self-learning-review-agent-plan.md)

| Phase | Status |
|-------|--------|
| M2.0 Spec + OpenAPI | done |
| M2.1 Mock routes | done |
| M2.2 Adapters | not started |
| M2.3 Loop env wiring | not started |
| M2.4 Staging smoke | not started |
| M2.5 R5 regression | not started |

## Migration M4 — self-tuning

Spec: [self-tuning-trainer-api-plan.md](self-tuning-trainer-api-plan.md) — **DRAFT**; mock partial, production not wired.

## Recent milestones

- **2026-06-15:** M2.0 + M2.1 — evolve API in OpenAPI + `mock_self_learning.py`; L1 scripts at `modes/self-coaching/scripts/`
- **2026-06-10:** Migration M1 PASS — live AgentEvals holdout (`full_loop_live_smoke.py`)
- **2026-06-09:** Demo loop P0–P4 — `loop_driver.py`, completeness harness C01–C18, one-command demo
- **2026-06-08:** Mock platform phases 1–4 — learning, play, AERL, coach demo
- **2026-06-07:** Mock platform phase 0 — registry, AgentEvals, composite client

Full changelog: `git log --oneline docs/project/`.

## Architecture rule

**One evolution engine, one `SelfCoachingClient`, many adapters.** orchestrator → client → {mock | AgentEvals | AERL | production API}.

## Related

[roadmap.md](roadmap.md) · [mock-to-real-migration.md](mock-to-real-migration.md) · [integration-plan.md](integration-plan.md)
