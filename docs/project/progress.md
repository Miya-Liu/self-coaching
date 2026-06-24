# Integration progress

**Authoritative status** for components and migration phases. Design: [pipelines.md](../design/pipelines.md).

**Active deploy target:** T1 skill pack. T2/T3 optional for coach mode.

## Component status

| Component | Status | In repo | Next |
|-----------|--------|---------|------|
| Auto-evaluation | **Done** | Live AgentEvals + mock | Opt-in CI job |
| Drop detector | **Done** | `check-drop` CLI | Coach scheduler (M5) |
| Evolution engine | **Done** | `services/orchestrator/` | Real pipeline hooks (M2+) |
| Self-coaching loop demo | **P0–P5 done** | `mock-self-coaching-demo.sh` + HTTP transport CI | — |
| Self-play | **M3 complete** | `mock_self_questioning.py` + pipeline adapter | Opt-in `pipeline-integration` workflow |
| Skill learning | **M2 complete** | adapters + mock routes + evolve API | Production staging (M2 deferred) |
| Model training | **CLI v1 done** | `CLITrainAdapter`, db_bridge transport | CT-D01 dataset handoff · live T-path |
| Coach mode shell | **Scheduler shipped** | registry, clock, scheduler, service, live bridge opt-in | Cron/systemd examples, coaching-root validation |
| Deployment | Dry-run | `deploy_manifest.json` | Canary + rollback (M4) |
| LLM proxy | Not started | — | M5 optional |

## Deploy targets

| Target | Ready? | Notes |
|--------|--------|-------|
| **T1** skill pack | **Active** | v0.3.1, `install-skill-pack.sh --hermes` |
| **T2** Coaching API | Mock complete | Production M2 deferred |
| **T3** evolution engine | M1 done | Not required for T1-only |

## Track exit criteria

| Track | Exit criterion | Status |
|-------|---------------|--------|
| Mock-complete (R5) | `completeness PASS` on mock golden (`tests/fixtures/golden/completeness_report_full_loop.json`) | ✅ CI green |
| Live Track 1 | `evolution_loop_clock_smoke.py` exits 0 (C06 ✓, C07 ✓, C12 ✓, C18 ✓) | ⚠️ dry-run pass observed; **CLI probe fails** (runner); **full non-dry-run pending** |
| Live meaningful train | CT-D01 dataset handoff + CT-D05 holdout with real training data | ❌ deferred |
| Production deploy | T2 Dockerfile + sqlite + canary + rollback (roadmap M2–M4) | ❌ not started |

**Source of truth:** This file (`progress.md`). Other docs reference these criteria.

## Migration M2 — self-learning

Spec: [self-learning-review-agent-plan.md](self-learning-review-agent-plan.md)

| Phase | Status |
|-------|--------|
| M2.0 Spec + OpenAPI | done |
| M2.1 Mock routes | done |
| M2.2 Adapters | **done** (`self_learning_client.py` + `learn_adapter.py`) |
| M2.3 Loop env wiring | **done** (`build_loop_client` passes `learn_backend`) |
| M2.4 Staging smoke | **done** (mock HTTP split-stack in CI) |
| M2.5 R5 regression | **done** (166 tests pass in mock-module mode) |

## Migration M3 — self-questioning (pipeline service)

**Tracker:** [self-questioning-pipeline-implementation.md](self-questioning-pipeline-implementation.md)  
**Analysis:** [self-questioning-integration-plan.md](self-questioning-integration-plan.md)  
**Service:** `http://10.110.158.146:8001` — connectivity verified 2026-06-16 (dry_run)

| Sprint | Focus | Status |
|--------|-------|--------|
| Sprint 0 | OpenAPI snapshot, `PipelineServiceClient`, availability tests, writeback spike | **done** |
| Sprint 1 | `SelfQuestioningPipelineEngine` + proceed signal (no Supabase export) | **done** |
| Sprint 2 | Loop env wiring, T-path factory, orchestrator | **done** |
| Sprint 3 | C06 sparse, proceed gating, runbook, opt-in CI | **done** |

| Phase | Status |
|-------|--------|
| M3.0 Contract freeze + client | **done** |
| M3.1 C07 batch (T-path) | **done** (proceed signal; writeback deferred) |
| M3.2 Loop + orchestrator wiring | **done** |
| M3.3 C06 sparse (E-path) + proceed gating | **done** (dry_run smoke) |
| M3.4 R5 mock-module regression | **done** |

## Migration M4 — self-tuning

**HTTP mock path:** [self-tuning-trainer-api-plan.md](self-tuning-trainer-api-plan.md) — M4.0–M4.3 + M4.5 done (CI).  
**Production CLI path:** [cli-training-integration-plan.md](cli-training-integration-plan.md) · **Tracker:** [cli-training-implementation.md](cli-training-implementation.md)  
**Scope (v1):** trigger remote tuning CLI + collect status/logs — not full T-path dataset handoff.

| Phase | Status |
|-------|--------|
| M4.0 Spec + contract freeze | **done** — HTTP spec; CLI plan supersedes for production |
| M4.1 Mock trainer routes | **done** — Slice 1–2 (TrainerClient + RestClient minimal) |
| M4.2 HTTP clients + mapping | **done** — `TrainerClient`, `RestClient`, `train_mapping.py` |
| M4.3 Loop env wiring | **done** — mock-http aerl backend, T-path HTTP test |
| M4.4 CLI transport + adapter (Sprint 0–1) | **done** |
| M4.5 Loop wiring + smoke (Sprint 2) | **done** — `ORCHESTRATOR_TRAIN_BACKEND=cli` |
| M4.6 Hardening + docs (Sprint 3) | **done** |
| M4.R5 mock-module regression | **done** — completeness e2e green, golden unchanged |
| M4.D Dataset handoff + live T-path | **deferred** — CT-D01+ after v1 smoke |

## Recent milestones

- **2026-06-16:** CLI training Sprints 0–3 — `CLITrainAdapter`, loop `cli` backend, smoke script, runbook, opt-in live tests
- **2026-06-16:** Migration M3 — pipeline self-questioning adapter (Sprints 0–3), proceed-only contract, opt-in CI
- **2026-06-16:** Coach `ClockScheduler` — periodic per-agent ticks with locking + tick event log
- **2026-06-16:** `LoopConfig` dataclass + config threading through run_tasks/e_path/t_path
- **2026-06-16:** Loop driver refactored into `loop_config.py`, `scoring.py`, `e_path.py`, `t_path.py`
- **2026-06-16:** Proxy bypass for localhost mock HTTP (Windows WinINET fix)
- **2026-06-16:** pytest wired into CI (Python 3.10–3.12 matrix) + mypy job
- **2026-06-15:** M2.0 + M2.1 — evolve API in OpenAPI + `mock_self_learning.py`; L1 scripts at `modes/self-coaching/scripts/`
- **2026-06-10:** Migration M1 PASS — live AgentEvals holdout (`full_loop_live_smoke.py`)
- **2026-06-09:** Demo loop P0–P4 — `loop_driver.py`, completeness harness C01–C18, one-command demo

Full changelog: `git log --oneline docs/project/`.

## Architecture rule

**One evolution engine, one `SelfCoachingClient`, many adapters.** orchestrator → client → {mock | AgentEvals | AERL | production API}.

## Related

[roadmap.md](roadmap.md) · [mock-to-real-migration.md](mock-to-real-migration.md) · [integration-plan.md](integration-plan.md)
