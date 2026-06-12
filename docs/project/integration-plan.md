# Integration plan: AgentEvals, production agent API, and Coaching API

Step-wise plan for wiring **real** production systems into the shared **evolution engine** without breaking the mock spine. Applies primarily to **Coach mode** (supervise external agents); Self-coaching mode can use the same eval/train adapters when automating locally.

Design: [architecture.md](../design/architecture.md), [coach_mode.md](../design/coach_mode.md), [integrations/](../design/integrations/). Milestones: [roadmap.md](roadmap.md) (deploy M0–M5). Status: [progress.md](progress.md). Loop migration: [mock-to-real-migration.md](mock-to-real-migration.md) (migration M0–M6).

> **Milestone naming:** **Integration Phase 0–5** (this doc) ≠ **[roadmap](roadmap.md) M0–M5** ≠ **[migration](mock-to-real-migration.md) M0–M6**. Example: Phase 1 AgentEvals adapter shipped; migration **M1 PASS**; roadmap **M2** Coaching API deploy still open.

**External API references (FastAPI / OpenAPI):**

| System | Docs URL | Role in the loop |
|--------|----------|------------------|
| **Production agent** | `http://10.110.158.146:8000/docs` | Serving agent: trajectories, versions, skills, deploy/rollback |
| **AgentEvals** | `http://localhost:8080/docs` | Benchmark suites, async eval runs, metrics for drop detection |
| **Coaching API (T2)** | `mock-services/contracts/openapi.yaml` | Contract spine: learn, self-play, eval, train |

**Rule:** one evolution engine, one `SelfCoachingClient` surface, many **adapters** — do not add parallel integration APIs per component.

## Coach mode context

In **Coach mode**, each **subject agent** (external) has its own **coaching root**:

```text
/var/lib/coach/agents/<agent_id>/
  experience/
  .self-coaching/metrics/eval_metrics.jsonl
```

Orchestrator commands take `--coaching-root` and `--agent-id` for that subject. Deploy and trajectory adapters use `AGENT_ID` and version ids from the production agent API. Scored evaluation uses **AgentEvals** — not the optional LLM proxy (observation only; see M5 in [roadmap.md](roadmap.md)).

---

## 1. Current state

### 1.1 What exists today

| Layer | Location | Status |
|-------|----------|--------|
| Coaching contract | `mock-services/contracts/openapi.yaml` | Source of truth for HTTP |
| Mock implementation | `mock-services/mock_self_coaching.py` | Deterministic learn → self-play → eval → train |
| Client | `mock-services/client.py` | `ModuleClient`, `CLIClient`, `HTTPClient` |
| Evolution engine (T3 / M1) | `services/orchestrator/` | `record-eval`, `check-drop`, `run` (dry deploy) |
| Metrics contract | `services/orchestrator/eval_metrics.py` | `EvalMetrics` + `normalize_from_mock_eval()` |
| CI | `.github/workflows/ci.yml` | Mock-only orchestrator smoke |

T1 (self-coaching pack) is the **active** deploy target. T2/T3 are optional until adapters land; see [`deploy-overview.md`](../guides/deploy-overview.md).

### 1.2 Target architecture

```text
                    +-------------------------------------+
                    |  Evolution engine (T3)              |
                    |  services/orchestrator              |
                    |  record-eval | check-drop | run     |
                    +-----------------+-------------------+
                                      |
                    +-----------------v-------------------+
                    |  SelfCoachingClient (composite)      |
                    |  evaluate / eval_report / learn / ...  |
                    +--+--------------+--------------+------+
                       |              |              |
              +--------v-----+  +-----v------+  +----v-----------+
              | AgentEvals   |  | Mock / AERL |  | Prod. agent   |
              | adapter      |  | (train,     |  | adapter       |
              | (eval)       |  |  self-play) |  | (trajectory,  |
              +------+-------+  +-------------+  |  deploy)     |
                     |                            +-------+-------+
              :8080 /api/runs                            |
                                                    :8000 /api/agents/...
```

---

## 2. API mapping

### 2.1 AgentEvals → mock eval contract

AgentEvals is **async** and suite-based. The adapter must implement the same semantics as `client.evaluate()` and `client.eval_report()`.

| Mock (`openapi.yaml`) | AgentEvals | Integration notes |
|----------------------|------------|-------------------|
| `POST /eval/runs` | `POST /api/runs` | Body: `RunCreate` (`suite_id`, `agent_config`, `num_trials`, …) |
| Poll until done | `GET /api/runs/{run_id}` | Status: `queued` → `running` → `succeeded` \| `failed` |
| `GET /eval/runs/{id}/report` | Same GET when complete | `RunDetail.metrics` → normalized report |
| Suite selection | `GET /api/suites`, `GET /api/suites/{suite_id}` | Config: canary vs holdout suite IDs |
| (optional M3) | `POST /api/evals/protocols/run`, scorecards | Evolution protocols; not required for M2 eval |

**Candidate / baseline identity:** pass production `agent_id` and `version_id` (or checkpoint id) inside `RunCreate.agent_config` (opaque dict). Orchestrator CLI flags `--candidate` / `--baseline` should map to these fields, not mock strings like `mock-baseline-v0`.

**Metrics normalization:** add `normalize_from_agentevals()` beside `normalize_from_mock_eval()` in `eval_metrics.py`. Suggested mapping (confirm against one real `RunDetail` in Phase 0):

| `EvalMetrics` field | Source (typical) |
|---------------------|------------------|
| `score` | `metrics["overall"]` or `pass_rate` or mean of task scores |
| `task_scores` | Per-slice keys in `metrics` |
| `safety_pass_rate` | `metrics["safety"]` or derived from case results |
| `cost_per_task` | `metrics["cost_usd"]` / task count |
| `latency_p95_ms` | `metrics["latency_p95_ms"]` or trial aggregates |
| `raw` | Full `RunDetail` JSON |

### 2.2 Production agent → trajectories and deploy

The production agent API is a **large** platform (agents, tasks, versions, skills, workflows, billing, …). Scope integration to the **self-improvement slice** only.

| Pipeline need | Production agent API | Milestone |
|---------------|----------------------|-----------|
| Trajectory export | `GET /api/tasks/{task_id}/messages`, `…/messages/all`, `…/stream` | M3 |
| Lineage metadata | `GET /api/agents/{agent_id}`, `GET …/versions`, active version | M2–M3 |
| Skill bundle | `GET/PUT /api/agents/{agent_id}/skills` | M3 |
| Smoke / canary run | `POST /api/agent/start` + stream endpoint | M4 |
| Promote candidate | `POST …/versions`, `PUT …/versions/{id}/activate` | M4 |
| Rollback | `POST …/versions/{id}/rollback` | M4 |

**Do not** replace AgentEvals with agent `/api/agent/start` for scheduled canary scoring — eval stays on AgentEvals; the agent API supplies **runtime identity** and **deployment**.

### 2.3 What remains mock until AERL (migration M4 train)

| Mock endpoint | Real backend (later) |
|---------------|----------------------|
| `POST /training/runs` | AERL HTTP (`TRAINER_BASE_URL` in `modes/self-coaching/self-tuning/services/example.env`) |
| `POST /self-play/generate` | Remote generator or mock through M3 |
| `POST /learning/events` | Orchestrator + trajectory exporter (same JSONL shape) |

---

## 3. Phased implementation

### Phase 0 — Discovery and frozen contracts (1–2 days)

**Goal:** Agreed field mapping before adapter code.

| Step | Action | Deliverable |
|------|--------|-------------|
| 0.1 | Snapshot OpenAPI | `docs/integration/api-snapshots/agent-openapi.json`, `agentevals-openapi.json` |
| 0.2 | Manual smoke | Health, list suites, one completed eval run, list agent versions |
| 0.3 | Document mapping | `docs/integration/mapping.md` (field-level `RunDetail.metrics` → `EvalMetrics`) |
| 0.4 | Choose config IDs | `agent_id`, `AGENTEVALS_SUITE_ID_CANARY`, `AGENTEVALS_SUITE_ID_HOLDOUT`, baseline/candidate `version_id` |

**Smoke commands (developer machine):**

```bash
# AgentEvals
curl -s http://localhost:8080/health
curl -s http://localhost:8080/api/suites

# Production agent (set TOKEN)
curl -s -H "Authorization: Bearer ${AGENT_API_TOKEN}" \
  http://10.110.158.146:8000/api/health
curl -s -H "Authorization: Bearer ${AGENT_API_TOKEN}" \
  "http://10.110.158.146:8000/api/agents/${AGENT_ID}/versions"
```

**Exit:** One captured `GET /api/runs/{id}` response with `status: succeeded` and documented `metrics` keys.

---

### Phase 1 — AgentEvals eval adapter (~3–5 days) — **shipped** (migration M1 PASS)

**Goal:** `record-eval` and orchestrator eval steps use real benchmarks; CI stays on mock by default.

| Step | Action | Location |
|------|--------|----------|
| 1.1 | Low-level HTTP client | `services/adapters/agentevals_client.py` |
| 1.2 | Eval adapter (`evaluate`, `eval_report`) | `services/adapters/eval_adapter.py` |
| 1.3 | Normalizer | `normalize_from_agentevals()` in `eval_metrics.py` |
| 1.4 | Orchestrator wiring | `ORCHESTRATOR_EVAL_BACKEND=mock\|agentevals` in `runner._build_client()` |
| 1.5 | Unit tests | `tests/fixtures/agentevals/` + `tests/test_agentevals_adapter.py` |

**Exit:** With env set, `python -m services.orchestrator record-eval --coaching-root /data/coaching` appends a real row to `.self-coaching/metrics/eval_metrics.jsonl`.

---

### Phase 2 — Composite coaching client (2–3 days)

**Goal:** Orchestrator call sites unchanged; backends selected by environment.

| Step | Action |
|------|--------|
| 2.1 | `CompositeClient` implementing `SelfCoachingClient` | `services/adapters/composite_client.py` | ✓ |
| 2.2 | Delegate `evaluate` / `eval_report` → AgentEvals; `learn` / `self_play` / `train` → mock (until M3/M2-train) | ✓ |
| 2.3 | Optional gateway | `mock_self_coaching.py serve --eval-backend agentevals` for HTTP contract tests |

**Exit:** `run --force` produces `current_eval.json` and `candidate_eval.json` from AgentEvals when backend flag set; existing mock CI unchanged.

---

### Phase 3 — Production agent read-only adapter (M3 prep, ~3–4 days)

**Goal:** Real trajectories and version/skill metadata in improvement runs.

| Step | Action |
|------|--------|
| 3.1 | `production_agent_client.py` — Bearer auth, retries, handle 402 |
| 3.2 | `export_trajectories(agent_id, since, out_path)` → JSONL under `run_dir/data/` |
| 3.3 | `get_production_lineage(agent_id)` → active `version_id`, skills for manifest |
| 3.4 | Replace stub `data/curation.json` with export paths + redaction flags |
| 3.5 | CLI: `--production-candidate` / `--production-baseline` accept `version_id` |

**Exit:** Improvement run includes `data/trajectories.jsonl` (or manifest pointer) with redacted excerpts.

---

### Phase 4 — Deploy adapter (M4)

**Goal:** Replace dry-run deploy with staging canary + rollback.

| Step | Action |
|------|--------|
| 4.1 | `deploy_candidate()` → create version and/or `activate` |
| 4.2 | Skill-only path → `PUT …/skills` when `improvement_path == skill` |
| 4.3 | `deploy_manifest.json` records previous `version_id` for rollback |
| 4.4 | Human approval gate before `activate` in production |

**Exit:** Staging agent promoted and rolled back via documented commands; production requires explicit approval.

---

### Phase 5 — AERL training adapter (migration M4, parallel)

| Step | Action |
|------|--------|
| 5.1 | Async `POST /training/runs` against AERL; poll status |
| 5.2 | Wire `CompositeClient.train()`; map `candidate` to checkpoint / version id |
| 5.3 | Reuse `modes/self-coaching/self-tuning/pipelines/` env (`TRAINER_BASE_URL`, `AERL_ROOT`) |

**Exit:** Orchestrator `improvement_path: model` triggers real training on staging.

---

## 4. Configuration

| Variable | Used by | Example |
|----------|---------|---------|
| `ORCHESTRATOR_EVAL_BACKEND` | Orchestrator | `mock` (CI default) \| `agentevals` |
| `ORCHESTRATOR_TRANSPORT` | Orchestrator | `module` \| `http` |
| `ORCHESTRATOR_BASE_URL` | HTTP coaching (learn/train) | `http://127.0.0.1:8765` |
| `AGENTEVALS_BASE_URL` | Eval adapter | `http://localhost:8080` |
| `AGENTEVALS_SUITE_ID` | Canary `record-eval` | from `GET /api/suites` |
| `AGENTEVALS_SUITE_ID_HOLDOUT` | Candidate eval in `run` | separate suite |
| `AGENTEVALS_POLL_INTERVAL_S` | Poll loop | `5` |
| `AGENTEVALS_TIMEOUT_S` | Poll loop | `3600` |
| `AGENT_API_BASE_URL` | Trajectory + deploy | `http://10.110.158.146:8000` |
| `AGENT_API_TOKEN` | Bearer | from `POST /api/auth/token` |
| `AGENT_ID` | Agent-scoped routes | production agent uuid |
| `MOCK_SERVICE_TOKEN` | Mock coaching HTTP | optional locally |

Document operational values in [`deploy-overview.md`](../guides/deploy-overview.md) when adapters ship.

---

## 5. Testing strategy

### Layer A — Unit (every PR, no network)

- `normalize_from_agentevals` with fixture `RunDetail` JSON
- Eval adapter: poll timeout, failed run handling
- Composite client delegation
- Existing `tests/test_orchestrator.py` (mock `module` transport)

### Layer B — Contract

- OpenAPI snapshot diff in CI (optional) when `docs/integration/api-snapshots/` changes
- Normalized scores in `[0, 1]`; required `EvalMetrics` fields present

### Layer C — Local integration harness

1. AgentEvals on `:8080`
2. Mock coaching on `:8765` (learn / train / self-play)
3. VPN access to `10.110.158.146:8000` for agent API

```bash
export ORCHESTRATOR_EVAL_BACKEND=agentevals
export AGENTEVALS_BASE_URL=http://localhost:8080
export AGENTEVALS_SUITE_ID=<canary-suite-id>
export ORCHESTRATOR_TRANSPORT=http
export ORCHESTRATOR_BASE_URL=http://127.0.0.1:8765

python -m services.orchestrator record-eval \
  --coaching-root ./integration-root \
  --agent-id "$AGENT_ID" \
  --candidate "$CANDIDATE_VERSION_ID" \
  --baseline "$BASELINE_VERSION_ID"

python -m services.orchestrator check-drop \
  --metrics-dir ./integration-root/.self-coaching/metrics

python -m services.orchestrator run \
  --coaching-root ./integration-root \
  --run-dir ./integration-root/improvement_runs/test-1 \
  --force-trigger
```

**Assert artifacts:** `current_eval.json`, `candidate_eval.json`, `decision.json`, `improvement_run_manifest.json`, `deploy_manifest.json` (`dry_run` until M4).

### Layer D — CI extensions

| Job | Trigger | Behavior |
|-----|---------|----------|
| `python-tests` (existing) | Every PR | Mock-only; no external URLs |
| `integration-agentevals` | `workflow_dispatch` or label | Fixtures or service container |
| `integration-staging` | Nightly / manual | Secrets for agent token + suite IDs |

**Safe drop test (no prod harm):** inject `eval_metrics.jsonl` line with `score: 0.70`, `baseline_score: 0.86` → `check-drop` exits non-zero → `run --force-trigger` → assert run directory layout.

### Layer E — Staging acceptance

| ID | Scenario | Success criterion |
|----|----------|-------------------|
| E1 | Scheduled `record-eval` | New metrics line; suite completes |
| E2 | Real drop | `check-drop` triggers; improvement run started |
| E3 | Skill path | `improvement_path: skill`; bundle artifact |
| E4 | Model path | AERL train; new `candidate_ref` |
| E5 | Reject | Gates fail → `decision: reject`; no activate |
| E6 | Promote + rollback | Version activated then rolled back on staging |

---

## 6. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| AgentEvals runs slow or flaky | Timeouts; store `run_id` in `EvalMetrics.raw`; idempotency key = `improvement_run_id` |
| `metrics` schema varies by suite | Per-suite mapping tests; document fallback keys in Phase 0 |
| CI cannot reach internal agent host | Mock/fixtures in CI; integration on self-hosted / VPN runner |
| Two HTTP APIs confused | Never merge OpenAPIs; single composite client |
| Wrong version promoted | M4: human approval + rollback pointer in manifest |
| Scope creep (200+ agent routes) | Adapter module lists allowed paths; code review checklist |

---

## 7. Execution order (do not skip)

1. **Phase 0** — mapping doc + live smoke + fixture capture  
2. **Phase 1** — AgentEvals adapter + `record-eval` on staging  
3. **Layer A/C tests** — fixtures + local harness  
4. **Phase 2** — composite client; orchestrator `run` uses real eval  
5. **Phase 3** — trajectory export  
6. **Phase 5** — AERL train (parallel once eval stable)  
7. **Phase 4** — activate/rollback (staging only)  
8. **Layer D/E** — CI and acceptance  

Aligns with **[roadmap](roadmap.md)**: M1 dry loop done → Phase 0 smoke done → roadmap M2 Coaching API deploy → M3–M4 improvement/deploy. **[Migration](mock-to-real-migration.md)** M1 PASS (AgentEvals); **M2** self-learning next.

---

## 8. Immediate next actions

- [x] Export production agent OpenAPI → `docs/integration/api-snapshots/agent-openapi.json` (2026-05-29)
- [x] Export AgentEvals OpenAPI → `api-snapshots/agentevals-openapi.json` (2026-06-10; live service on `:8080`)
- [x] Run Phase 0 smoke; live succeeded `RunDetail` captured → `tests/fixtures/agentevals/run_detail_memoryarena_succeeded.json`
- [x] Choose `agent_id`, canary/holdout `suite_id` for local smoke — agent `6ed953f5-ca52-45ff-a137-9d2d1b2e1d8d`, suite `MemoryArena_Preview`, model `gpt-4o` (`scenarios/demo.agentevals.env.example`)
- [x] Implement Phase 1.1–1.3 behind `ORCHESTRATOR_EVAL_BACKEND` (`services/adapters/`, `mapping.md`); live smoke `scripts/agentevals_live_smoke.py` PASS
- [x] Add `tests/test_agentevals_adapter.py`, `tests/test_holdout_engine.py`, `tests/test_agentevals_mapping.py`
- [x] Update [`progress.md`](progress.md) — Auto-evaluation **Done (AgentEvals)** (2026-06-10)

---

## Related documents

- [Documentation index](../README.md)
- [design/integrations/](../design/integrations/) — adapter design per system
- [evaluators.md](../design/evaluators.md) — metrics and trigger policy
- [pipelines.md](../design/pipelines.md) — evolution engine loop
- [roadmap.md](roadmap.md) — deploy milestones (roadmap M0–M5)
- [mock-to-real-migration.md](mock-to-real-migration.md) — loop adapter phases (migration M0–M6)
- [self-learning-review-agent-plan.md](self-learning-review-agent-plan.md) — migration M2 self-learning review API
- [progress.md](progress.md) — component matrix
- [deploy-overview.md](../guides/deploy-overview.md) — T1 / T2 / T3 + Coach mode
- [runbook.md](../guides/runbook.md) — day-to-day operator commands
- `mock-services/contracts/openapi.yaml` — Coaching API (T2) contract
