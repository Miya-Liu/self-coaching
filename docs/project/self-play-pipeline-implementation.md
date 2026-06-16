# Self-Play Pipeline Service — Implementation Tracker

> **Authoritative tracker** for integrating the real **Self-Questioning Agent Pipeline Service** as the self-play backend (migration **M3**). Analysis and API mapping: [self-play-integration-plan.md](self-play-integration-plan.md). Migration rules: [mock-to-real-migration.md](mock-to-real-migration.md).

**Status:** Complete (2026-06-16) — Sprints 0–3 shipped; live dry_run smoke verified  
**Scope (2026-06-16):** **Success signal only** — adapter reports whether the pipeline job completed (`proceed: true/false`). Generated data stays in the remote store; **no Supabase → `staging.jsonl` export** at this stage.

**Related:** [progress.md](progress.md) · [mock-to-real-migration.md](mock-to-real-migration.md) · [integration-plan.md](integration-plan.md) · [cli-training-integration-plan.md](cli-training-integration-plan.md) (training path; independent)

---

## 1. Goal

Wire the coaching loop to the real pipeline service at `http://10.110.158.146:8001` while keeping the mock self-play path unchanged for CI and local dev.

| Principle | Rule |
|-----------|------|
| **SP-R1** | Adapter parity — extend `services/adapters/`; do not fork parallel client trees |
| **SP-R2** | Explicit backend — `ORCHESTRATOR_SELFPLAY_BACKEND=mock\|pipeline` |
| **SP-R3** | Mock CI unchanged — R5 (`LOOP_SERVICE_MODE=mock-module`) stays green every PR |
| **SP-R4** | **Proceed signal** — `proceed: true` when all pipeline stages succeed; loop advances without local data writeback |
| **SP-R5** | Ship C07 before C06 — batch T-path is lower risk than failure-conditioned sparse |

---

## 2. Service contract (frozen)

**Title:** Self-Questioning Agent Pipeline Service v1.0.0

| Method | Path | Use |
|--------|------|-----|
| `GET` | `/health` | Liveness |
| `POST` | `/api/pipeline/submit` | Production — async job |
| `GET` | `/api/pipeline/status/{job_id}` | Poll |
| `GET` | `/api/pipeline/tasks` | List jobs (`?status=&limit=`) |
| `GET` | `/api/pipeline/logs/{job_id}` | Debug (`?lines=`) |
| `POST` | `/api/pipeline/run_sync` | Smoke only — blocks worker |

**Pipeline stages:** `1` → generate tasks from Supabase messages · `2` → env explore · `3` → import to Supabase `query_bank`

**Snapshot (when frozen):** `docs/integration/api-snapshots/pipeline-service-openapi.json`

### Request defaults (`PipelineRequest`)

| Field | Default | Loop mapping |
|-------|---------|--------------|
| `start_stage` | `1` | Full run; partial re-run for recovery |
| `generate_tasks_limit` | `0` (all) | **C07:** `n` (buffer deficit) · **C06:** `min(\|Σ\|, σ_play)` |
| `train_eval_flag` | `"eval"` | **C06:** `eval` · **C07:** `train` (env override) |
| `n` | `8` | Exploration branches; cap with `min(n, 8)` |
| `num_explore_threads` | `8` | Parallelism; cap with `min(n, 8)` |
| `dry_run` | `false` | CI connectivity only |
| `dry_run_import` | `false` | Stage-3 preview |
| `fail_fast` | `true` | Stop on first stage failure |
| `cpu_only` | `true` | Stage-2 resource mode |

### Response (`PipelineTaskInfo`)

`job_id`, `status` (`pending` \| `running` \| `success` \| `failed`), timestamps, `config`, `stage_results` (bool per stage), `error`.

---

## 3. Architecture

```
Coach / loop_driver / orchestrator
        │
        ├─ ORCHESTRATOR_SELFPLAY_BACKEND=mock
        │       → MockSelfPlayEngine (mock-services/mock_self_play.py)
        │
        └─ ORCHESTRATOR_SELFPLAY_BACKEND=pipeline
                → SelfPlayPipelineEngine (services/adapters/)
                        → PipelineServiceClient
                                → POST /api/pipeline/submit
                                → GET  /api/pipeline/status/{job_id}
                        → returns { proceed, job_id, stage_results } (no local export)
```

### Loop call sites (must all use factory by end of Sprint 2)

| ID | Step | File | Mock today | Pipeline mapping |
|----|------|------|------------|------------------|
| **C06** | Sparse self-play (E-path) | `modes/self-coaching/e_path.py` | `generate_suite` | Stage 1–3, `train_eval_flag=eval`, limit = σ size |
| **C07** | Batch buffer fill (T-path) | `modes/self-coaching/t_path.py` | `generate_batch` | Stage 1–3, `train_eval_flag=train`, limit = `n` |
| **C08** | Orchestrator collect | `services/orchestrator/runner.py` | `client.self_play()` | Same as C07 |

**Not yet wired:** `CompositeClient.self_play()` always delegates to inner mock — needs adapter in Sprint 2.

---

## 4. Proceed contract (success signal)

The loop needs to know **whether self-play finished successfully** so the agent can move to the next step (learn, eval, train, etc.). It does **not** need locally mirrored trajectory rows at this stage.

### Adapter return shape

**Batch (C07) — success:**

```json
{
  "status": "generated",
  "count": 4,
  "job_id": "a1b2c3…",
  "stage_results": { "1": true, "2": true, "3": true },
  "pipeline_service": true,
  "proceed": true
}
```

**Sparse (C06) — success:** same, but `"status": "registered"`.

**Failure / timeout:**

```json
{
  "status": "error",
  "error": "…",
  "count": 0,
  "job_id": "…",
  "stage_results": { "1": true, "2": false, "3": false },
  "pipeline_service": true,
  "proceed": false
}
```

**Caller rule:** use `result.get("proceed")` or `pipeline_job_succeeded(result)` before advancing.

### Loop read path (mock vs pipeline)

| Backend | After self-play | Buffer / Σ update |
|---------|-----------------|-------------------|
| **mock** | Reads `.self-coaching/curated/staging.jsonl` | Yes — trajectories appended locally |
| **pipeline** | Skips `staging.jsonl` read | No — remote data only; `proceed` gates next step |

Implemented in `e_path.augment_sigma_sparse` and `t_path.fill_buffer_batch` (`if not result.get("pipeline_service")`).

### Deferred: local writeback

Exporting Supabase `query_bank` → `staging.jsonl` is **deferred**. Revisit only if T-path must train from locally curated trajectories sourced from the pipeline.

---

## 5. Environment profile

```env
# Backend switch
ORCHESTRATOR_SELFPLAY_BACKEND=pipeline   # mock | pipeline

# Service URL (canonical)
PIPELINE_SERVICE_URL=http://10.110.158.146:8001

# Polling (production jobs may run 5–30+ min)
PIPELINE_POLL_INTERVAL_S=5
PIPELINE_POLL_TIMEOUT_S=3600

# Per-path flags
PIPELINE_TRAIN_EVAL_FLAG=eval            # C06 default
PIPELINE_BATCH_TRAIN_EVAL_FLAG=train     # C07 override

# Optional overrides (usually leave defaults)
# PIPELINE_ENV_URL=http://...
# PIPELINE_N=8
# PIPELINE_NUM_EXPLORE_THREADS=8
```

**Live profile example** (with other M1/M2 backends):

```env
LOOP_SERVICE_MODE=live
LOOP_HOLDOUT_TIMEOUT_S=300
ORCHESTRATOR_EVAL_BACKEND=agentevals
ORCHESTRATOR_LEARN_BACKEND=self-learning
ORCHESTRATOR_SELFPLAY_BACKEND=pipeline
PIPELINE_SERVICE_URL=http://10.110.158.146:8001
```

Template additions: `scenarios/demo.env.example` (Sprint 2).

---

## 6. Sprint plan

Calendar assumes ~3–4 working days per sprint. Adjust dates when sprint starts.

### Sprint 0 — Contract + client foundation

**Target:** Safe CI tests + HTTP client; no loop changes.

| ID | Task | Owner | Status |
|----|------|-------|--------|
| SP-T01 | Freeze OpenAPI → `docs/integration/api-snapshots/pipeline-service-openapi.json` | — | done |
| SP-T02 | `tests/integration/test_pipeline_service_availability.py` — health, dry_run submit, status poll, 404/422 | — | done |
| SP-T03 | `services/adapters/pipeline_service_client.py` — submit, status, wait_for_job, logs, run_sync | — | done |
| SP-T04 | **Writeback spike** — document `query_bank` path + Option A decision (§4) | — | done (schema sample → Sprint 1) |
| SP-T05 | Unit tests with fixtures (`tests/fixtures/pipeline/`) — no live network in default CI | — | done |

**Sprint 0 exit criteria:**

- [x] OpenAPI snapshot committed
- [x] `PipelineServiceClient` unit-tested offline
- [x] Opt-in live test: dry_run passes against `10.110.158.146:8001`
- [x] Writeback approach decided (Option A — Supabase export)
- [x] R5 mock-module demo still green

---

### Sprint 1 — Adapter + C07 (batch T-path)

**Target:** `SelfPlayPipelineEngine.generate_batch()` submits pipeline jobs and returns `proceed` signal.

| ID | Task | Owner | Status |
|----|------|-------|--------|
| SP-T06 | ~~`staging_writeback.py`~~ — **deferred** (no Supabase export) | — | cancelled |
| SP-T07 | `services/adapters/selfplay_pipeline_adapter.py` — `SelfPlayPipelineEngine` | — | done |
| SP-T08 | `services/adapters/pipeline_mapping.py` — C07/C06 request + result mapping | — | done |
| SP-T09 | `tests/test_selfplay_pipeline_adapter.py` | — | done |
| SP-T10 | `e_path` / `t_path` skip `staging.jsonl` when `pipeline_service` | — | done |

**Sprint 1 exit criteria:**

- [x] Adapter returns `{status, count, job_id, stage_results, pipeline_service, proceed}`
- [x] Unit tests pass in CI (no live network)
- [x] Loop call sites skip local staging read for pipeline backend
- [ ] Opt-in live smoke: real job returns `proceed: true` (manual)
- [x] R5 mock-module demo still green

---

### Sprint 2 — Loop wiring + orchestrator

**Target:** Env-driven backend switch; loop uses pipeline when configured.

| ID | Task | Owner | Status |
|----|------|-------|--------|
| SP-T11 | `LoopConfig` — `selfplay_backend`, `pipeline_service_url` | — | done |
| SP-T12 | `loop_env.py` — `ORCHESTRATOR_SELFPLAY_BACKEND`, `build_self_play_engine()` | — | done |
| SP-T13 | `self_play_factory.py` + `t_path` / `e_path` factory routing | — | done |
| SP-T14 | `composite_client.py` + `PipelineSelfPlayClientAdapter` | — | done |
| SP-T15 | `services/orchestrator/runner.py` → `build_loop_client()` | — | done |
| SP-T16 | `scenarios/demo.env.example` — pipeline env block | — | done |
| SP-T17 | Staging smoke: `clock_loop_smoke.py` with pipeline env | — | manual |

**Sprint 2 exit criteria:**

- [x] `ORCHESTRATOR_SELFPLAY_BACKEND=pipeline` drives self-play via factory
- [x] `ORCHESTRATOR_SELFPLAY_BACKEND=mock` unchanged (default)
- [x] Orchestrator `client.self_play()` uses pipeline adapter when configured
- [ ] Coach clock smoke with live pipeline (manual)
- [x] R5 mock-module demo still green

---

### Sprint 3 — C06 sparse + coach + hardening

**Target:** E-path sparse self-play; coach clock; docs and opt-in CI.

| ID | Task | Owner | Status |
|----|------|-------|--------|
| SP-T18 | `SelfPlayPipelineEngine.generate_suite()` — C06 mapping | — | done (Sprint 1) |
| SP-T19 | `e_path` via `run_suite_self_play` factory | — | done (Sprint 2) |
| SP-T20 | `clock.py` passes `build_self_play_engine()` | — | done (Sprint 2) |
| SP-T21 | C06 prerequisite documented (Supabase messages) | — | done |
| SP-T22 | `docs/guides/runbook.md` — pipeline self-play section | — | done |
| SP-T23 | Opt-in CI `.github/workflows/pipeline-integration.yml` | — | done |
| SP-T24 | `scenarios/demo.pipeline.env.example` + `scripts/pipeline_self_play_smoke.py` | — | done |

**Sprint 3 exit criteria:**

- [x] C06 / C07 pipeline paths return `proceed` (dry_run smoke verified)
- [x] E-path / T-path hold when `proceed: false`
- [x] Runbook published
- [x] Opt-in CI workflow added
- [x] R5 mock-module demo unchanged (default CI)

---

## 7. File map (planned)

| File | Sprint | Purpose |
|------|--------|---------|
| `docs/integration/api-snapshots/pipeline-service-openapi.json` | 0 | Contract freeze |
| `services/adapters/pipeline_service_client.py` | 0 | HTTP client |
| `services/adapters/pipeline_http.py` | 0 | Optional shared HTTP base (if needed) |
| `services/adapters/pipeline_mapping.py` | 1 | Request builders + `proceed` mapping |
| `services/adapters/selfplay_pipeline_adapter.py` | 1 | `SelfPlayPipelineEngine` |
| `tests/integration/test_pipeline_service_availability.py` | 0 | Live opt-in probes |
| `tests/test_pipeline_service_client.py` | 0 | Offline client tests |
| `tests/test_selfplay_pipeline_adapter.py` | 1 | Adapter unit tests |
| `tests/fixtures/pipeline/*.json` | 0 | Recorded responses |
| `modes/self-coaching/loop_config.py` | 2 | Config fields |
| `modes/self-coaching/loop_env.py` | 2 | Factory wiring |
| `modes/self-coaching/t_path.py` | 2 | Factory call site |
| `modes/self-coaching/e_path.py` | 3 | Factory call site |
| `services/adapters/composite_client.py` | 2 | Orchestrator `self_play` |
| `scenarios/demo.env.example` | 2 | Env template |

---

## 8. Testing strategy

| Layer | Command / file | Network | PR gate |
|-------|----------------|---------|---------|
| Mock regression (R5) | `bash tests/test_mock_self_coaching_demo.sh` | none | **required** |
| Client unit | `pytest tests/test_pipeline_service_client.py` | none | required |
| Adapter unit | `pytest tests/test_selfplay_pipeline_adapter.py` | none | required |
| Availability (dry_run) | `pytest tests/integration/test_pipeline_service_availability.py` | live VPN | opt-in |
| T-path loop | `pytest tests/test_loop_t_path.py` | none (mock) | required |
| Sparse loop | `pytest tests/test_loop_self_play_sparse.py` | none (mock) | required |
| Coach smoke | `python scripts/clock_loop_smoke.py` | staging | manual |
| Full live | `scripts/full_loop_live_smoke.py` | staging | manual |

---

## 9. Risks and decisions

| # | Risk / question | Mitigation | Decision |
|---|-----------------|------------|----------|
| Q1 | Writeback path unknown | SP-T04 spike before adapter work | **TBD** |
| Q2 | C06 not failure-targeted (no trajectory in API body) | Depends on M2 + eval → Supabase; ship C07 first | **Accepted for v1** |
| Q3 | No `suite_id` / AgentEvals registration | Return job metadata only; optional M3.1 suite registration | **Deferred** |
| Q4 | Long jobs block coach tick | `PIPELINE_POLL_TIMEOUT_S`; per-agent lock; document timeout budget | **TBD** |
| Q5 | `env_url` defaults to pipeline host localhost | Confirm env service reachable; override in request if needed | **TBD** |
| Q6 | `run_sync` in production | Use `submit`+poll only; `run_sync` for smoke | **Decided** |

---

## 10. Verified infrastructure (2026-06-16)

| Component | Status | Details |
|-----------|--------|---------|
| Pipeline service `/health` | ✅ | `status: ok`, `version: 1.0.0` |
| `POST /api/pipeline/submit` (dry_run) | ✅ | Returns `job_id`; stages 1–3 succeed |
| `GET /api/pipeline/status/{job_id}` | ✅ | Poll works |
| `GET /api/pipeline/tasks` | ✅ | Lists jobs |
| Supabase `query_bank` export | — | **Deferred** — success signal only |
| `staging.jsonl` writeback | ⏳ | Pending Sprint 1 |
| M2 messages in Supabase (C06) | ⏳ | Prerequisite for Sprint 3 |

---

## 11. Progress log

| Date | Sprint | Notes |
|------|--------|-------|
| 2026-06-16 | — | Implementation doc created; API connectivity verified (dry_run) |
| 2026-06-16 | Sprint 3 | Proceed gating, runbook, opt-in CI, live dry_run smoke PASS |
| | Sprint 1 | |
| | Sprint 2 | |
| | Sprint 3 | |

---

## 12. How to update this doc

1. Change task **Status** (`not started` → `in progress` → `done`) when work lands.
2. Check sprint **exit criteria** boxes when the sprint closes.
3. Append a row to **§11 Progress log** with date and PR reference.
4. Mirror headline status in [progress.md](progress.md) § Migration M3.

**Task status values:** `not started` · `in progress` · `done` · `blocked` · `deferred`
