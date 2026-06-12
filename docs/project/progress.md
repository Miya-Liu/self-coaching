# Integration progress

Status of **evolution engine** components against [roadmap.md](roadmap.md). Design: [pipelines.md](../design/pipelines.md), [architecture.md](../design/architecture.md).

**Active deploy target:** **T1 — Self-coaching pack** (Self-coaching mode, M0). T2/T3 support Coach mode and optional Self-coaching-mode automation.

## Component status

| Component | Milestone | Status | MVP in repo | Next deliverable |
|-----------|-----------|--------|-------------|------------------|
| **Production agent** | M3–M4 | Adapter planned | `client.py` consumers | Trajectory + deploy adapter |
| **Trajectory store** | M3 | Not wired | `.self-coaching/events/*.jsonl` | `POST /trajectories` or extended learn payload |
| **Auto-evaluation** | M1–M2 | **Done (AgentEvals)** | Mock + **live AgentEvals** adapter (`holdout_engine`, `agentevals_mapping`); `full_loop_live.json` + `scripts/full_loop_live_smoke.py` PASS | Opt-in CI job; cost/latency from suite when available |
| **Drop detector** | M1 | **Done** | `python -m services.orchestrator check-drop` | Wire to coach scheduler (M5) |
| **Evolution engine** | M1 | **Done** | `services/orchestrator/`, `scripts/run-orchestrator.sh` | Real `pipeline.yaml` shell hooks (M2+) |
| **Curation** | M3 | **Mock wired** | `curate_data.py` via self-play + orchestrator | Trajectory ingest + production export |
| **Self-play** | M2 | **Mock stub** | `mock_self_play.py` (`generate-suite` → AgentEvals) | Remote generator adapter |
| **Skill learning** | M2 | **In progress** | `mock_self_learning.py` (sync events only); review API **not wired** | M2.1 mock routes → M2.2 adapter — [task list](self-learning-review-agent-plan.md#11-implementation-task-lists) |
| **Model training** | M2 | **Mock stub** | `mock_aerl.py` + `aerl_client.py` / `train_adapter.py` | Live AERL staging smoke |
| **Candidate evaluation** | M1 | **Done (holdout)** | Live holdout via `full_loop_live.json` (C12+C18); mock promote path unchanged | Cost/latency from suite when available; full live promote (M4) |
| **Deployment** | M1 dry / M4 live | **Dry-run** | `deploy_manifest.json` (`canary_fraction: 0`) | Canary + rollback via agent API |
| **Version management** | M1 | **Mock stub** | `mock_agent_registry.py` | Production agent API adapter |
| **Coach mode shell** | M5 | **Started** | `modes/coach/registry.py`, `agents.example.yaml` | Scheduler examples + validation CLI |
| **LLM proxy** | M5 | Not started | — | Optional observation adapter |
| **Self-coaching loop demo** | M1.5+ | **P0–P4 done** | `mock-self-coaching-demo.sh`, `self_coaching_loop.py`, completeness harness | P5: split-stack CI job |

## Deploy targets and modes

| Target | Mode | Ready? | Notes |
|--------|------|--------|-------|
| **T1 — Self-coaching pack** | Self-coaching | **Active** | `install-skill-pack.sh --hermes`, `SKILL_PACK_VERSION` 0.3.1 (`v0.3.1-hermes-installable`) |
| **T2 — Coaching API** | Coach | Mock complete | M2 production deploy deferred; adopt mock for coach mode |
| **T3 — Evolution engine** | Coach (+ self-coaching optional) | M1 done | Not required for T1-only Self-coaching mode |

## M2 self-learning (remote review agent)

Spec: [self-learning-review-agent-plan.md](self-learning-review-agent-plan.md). **Status:** not started (docs only).

| Phase | Status |
|-------|--------|
| M2.0 Spec + OpenAPI draft | not started |
| M2.1 Mock production routes | not started |
| M2.2 Adapters (`self_learning_client`, `learn_adapter`) | not started |
| M2.3 Loop env + facade wiring | not started |
| M2.4 Staging smoke | not started |
| M2.5 R5 regression | not started |

**Skill pack (parallel):** [self-learning-review-agent-plan.md §11.8](self-learning-review-agent-plan.md#118-skill-pack--skillmd-alignment-l-series) — L1–L8 (scripts path, SKILL.md alignment). **not started**

---

## Completed (integration layer)

- **2026-06-10:** AgentEvals live integration **PASS** (migration M1) — holdout factory + MemoryArena mapping; `full_loop_live.json` + C12/C18 golden; `scripts/full_loop_live_smoke.py`; live E2E vs `localhost:8080` (agent `6ed953f5-…`, `MemoryArena_Preview`, `gpt-4o`); R5 mock-module unchanged
- **2026-06-09:** Self-coaching demo loop **P0–P2** — deterministic task-stream driver under `modes/self-coaching/`:
  - **P0:** `trajectory_scorer.py` (§3.2.1 rubric), `trajectory_simulator.py`, `state.py`, `loop_driver.py` skeleton, fixtures in `mock-services/fixtures/task_stream/tool_use_v1.jsonl`, tests `test_trajectory_scorer.py`, `test_loop_driver_skeleton.py`
  - **P1:** E-path — `support.jsonl` / `tuning_buffer.jsonl` / trajectory artifacts; `client.learn()` via `ModuleClient`; registry draft+activate; `g++` + A6 `meta.generation` mirror; fixtures `e_path_v1.jsonl`; tests `test_loop_e_path.py`
  - **P2:** Sparse self-play (C06) + T-path (C07) — `generate_suite` before `learn()` when `0 < |Σ| ≤ σ_play`; `FreeTimeSimulator`; `generate_batch` buffer top-up; `client.train()` + holdout `R_suite` + `check_promotion()` + hot-swap; fixtures `sparse_play_v1.jsonl`, `t_path_v1.jsonl`; tests `test_loop_self_play_sparse.py`, `test_loop_t_path.py`
  - Plan: [self-coaching-demo-pipeline-plan.md](self-coaching-demo-pipeline-plan.md) · **14 pytest cases** green (module transport; no HTTP stack required)
- **2026-06-09:** Self-coaching demo loop **P3 — completeness harness** — mock-completeness audit (C01–C18):
  - `tools/loop_completeness.py` — reads loop artifacts, registry lineage, T-path run dir (`current_eval.json`, `candidate_eval.json`, `decision.json`, `deploy_manifest.json`); emits `completeness_report.json`; **C18** semantic promote gate (`candidate_eval.score >= current_eval.score`)
  - Scenario manifests: `scenarios/full_loop.json`, `sparse_failures.json`, `dense_failures.json`
  - Loop driver persists `e_path_last.json`, `t_path_last.json`, `.self-coaching/loop/runs/t_path/` for audit evidence
  - `loop_store.export_train_dataset` tags `source: loop_buffer` for split-hygiene (C16)
  - Tests: `tests/test_loop_completeness.py` (synthetic matrix, C18 negative, sparse/dense C06, E2E full_loop PASS) · **19 pytest cases** green across loop suite
- **2026-06-09:** Self-coaching demo loop **P4 — one-command UX** — demo-ready milestone (`v0.3.0-self-coaching-demo`):
  - `scripts/mock-self-coaching-demo.sh` — idempotent loop + completeness PASS; optional `--with-http` split stack
  - `mock-services/self_coaching_loop.py` — `run` subcommand for `scenarios/full_loop.json`; writes `demo_summary.md`
  - Runbook [§ Self-coaching demo (mock loop)](../guides/runbook.md#self-coaching-demo-mock-loop); CI `tests/test_mock_self_coaching_demo.sh` + golden `completeness_report_full_loop.json`
- **2026-06-08:** Mock platform Phase 4 — `scripts/mock-coach-demo.sh` (two agents, drop loop, promote/reject); CI `integration-mock-stack`
- **2026-06-08:** Mock platform Phase 3 — `mock_aerl.py` (async training runs, registry `model_id` drafts, pipeline argv); `aerl_client.py`, `train_adapter.py`, `ORCHESTRATOR_TRAIN_BACKEND=aerl`
- **2026-06-08:** Mock platform Phase 2 — `mock_self_play.py` (generate-suite, AgentEvals registration, curation splits)
- **2026-06-08:** Mock platform Phase 1 — `mock_self_learning.py` (classify, memory/skill/error routing, registry drafts)
- **2026-06-07:** Mock platform Phase 0 — `mock_agent_registry.py`, `mock_agentevals.py`, `scripts/mock-stack-up.sh`; design doc [`mock-platform-design.md`](mock-platform-design.md)
- **2026-06-07:** Integration Phase 2 stub — `CompositeClient` / `build_composite_client`; `scripts/curate_data.py`; coach registry loader (`modes/coach/registry.py`)
- **2026-05-29:** M0 exit verified locally (`doctor.sh` + `install-skill-pack.sh . --with-mock`); production agent OpenAPI snapshot in `docs/integration/api-snapshots/agent-openapi.json`
- Phase 1 mock fixes: `--host`, `ValueError` for bad pipelines
- HTTP: bearer auth, idempotency, body size cap
- Client: `api_key`, headers, `AuthError`, CLI JSON parsing
- CI: contract sync, evolution engine smoke, mock `run-all`
- Docs: `design/` restructure (architecture, self_coaching_mode, coach_mode, pipelines, evaluators, integrations)

## Architecture rule

**One evolution engine, one `SelfCoachingClient`, many adapters:** orchestrator → client → OpenAPI service → {mock | AgentEvals | AERL | production agent API}. Do not add parallel integration APIs per component.

## Documentation debt (audit 2026-06-12)

Cross-doc cleanup **2026-06-12** — milestone naming, stale statuses, contract vs spec split.

| ID | Status | Fix applied |
|----|--------|-------------|
| D1 | **fixed** | Naming callout in `mock-to-real-migration.md`, `roadmap.md`, `integration-plan.md` |
| D2 | **fixed** | `docs/integration/README.md` — AgentEvals captured; pending snapshots listed |
| D3 | **fixed** | `mock-to-real-migration.md` §4.3 — loop/holdout marked shipped |
| D4 | **fixed** | M0 section — partial; AgentEvals snapshot checked off |
| D5 | **fixed** | Golden policy — `full_loop_live.json` no longer "(future)" |
| D6 | **fixed** | `roadmap.md` M2 — AgentEvals adapter `[x]` + migration M1 note |
| D7 | **fixed** | Component table Auto-evaluation "Next" updated |
| D8 | **fixed** | `coaching_api.md` — split in-yaml vs spec-only (M2) endpoints |
| D9 | **fixed** | Cross-links in `integration-plan.md` |
| D10 | **fixed** | Migration doc footer date + M2 pointer |
| D11 | **fixed** | M-W3 struck through / done |
| D12 | **fixed** | `docs/README.md` index |
| D13 | **fixed** | M2.0 tracker → in progress |
| D14 | **fixed** | §8 renamed "Completed prerequisites (M1)" |
| D15 | **fixed** | `integration/README.md` mapping status |

**Open (not doc-debt):** Skill pack tasks **SP/L1–L8** — implementation tracked in [self-learning-review-agent-plan.md §11.8](self-learning-review-agent-plan.md#118-skill-pack--skillmd-alignment-l-series); optional: one-line pointer in `changelog-skills.md` on next skill pack release.

---

## Related

- [Documentation index](../README.md)
- [design/README.md](../design/README.md) — design index
- [Integration plan](integration-plan.md) — adapter implementation
- [Roadmap](roadmap.md) — deploy milestones (roadmap M0–M5)
- [Mock→real migration](mock-to-real-migration.md) — loop adapters (migration M0–M6)
- [pipelines.md](../design/pipelines.md) — evolution engine specification
