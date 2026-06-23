# Mock → real API migration plan

> **Implementation reference** — adapter migration M0–M6. Status: [progress.md](progress.md). User docs: [docs/README.md](../README.md).

**Status:** **M1–M4 adapter work complete** (2026-06-16) — M1 AgentEvals live holdout, M2 self-learning adapters, M3 pipeline self-questioning (proceed signal), M4 CLI train (trigger + status). Live Track 1: C06 ✓, C07 pending (timeout config), C12/C18 pending.  
**Ground truth:** tag **`v0.3.1-hermes-installable`** — mocks-only “it works” pin (Hermes pack + loop demo)  
**Related:** [self-coaching-demo-pipeline-plan.md](self-coaching-demo-pipeline-plan.md), [integration-plan.md](integration-plan.md), [integration/mapping.md](../integration/mapping.md), [mock-platform-design.md](mock-platform-design.md), [deploy-skill-pack.md](../guides/deploy-skill-pack.md), [self-learning-review-agent-plan.md](self-learning-review-agent-plan.md), [self-tuning-trainer-api-plan.md](self-tuning-trainer-api-plan.md)

> **Milestone naming:** **Migration M0–M6** (this doc) = loop mock→live adapter phases. **[Roadmap](roadmap.md) M0–M5** = deploy targets (T1 skill pack, T2 Coaching API, …). **[Integration plan](integration-plan.md) Phase 0–5** = adapter implementation steps. Example: migration **M1** (AgentEvals holdout) ≠ roadmap **M1** (evolution engine dry loop).

---

## 1. Goal

Move the self-coaching **loop demo** from in-process / HTTP **mocks** to **staging or production APIs** without replacing the mock spine. Operators switch behavior via **environment profile** (`LOOP_SERVICE_MODE` + service URLs), not code forks.

**Principle:** *adapter parity, not replacement.* Mocks stay for CI and local dev. Real backends plug in behind existing `services/adapters/` and env flags.

---

## 2. Migration rules (M0–M6)

These rules apply to **every** phase. Violating them blocks merge.

| ID | Rule |
|----|------|
| **R1** | **Adapter parity, not replacement.** Extend `services/adapters/` and env factories; do not fork parallel HTTP client trees or delete mock engines. |
| **R2** | **Mode is explicit.** `LOOP_SERVICE_MODE` + backend flags (`ORCHESTRATOR_*_BACKEND`) are authoritative — never infer mock vs live from hostname alone. |
| **R3** | **Extend the CI gate, never replace it.** `tests/test_mock_self_coaching_demo.sh` and the mock golden stay on the default PR path; staging smoke is opt-in only. |
| **R4** | **One phase, one adapter surface.** Each phase wires **one** real backend behind the existing loop contract; do not bundle unrelated service swaps in the same PR. |
| **R5** | **Mocks-only pin stays green.** Tag **`v0.3.1-hermes-installable`** is the bisect anchor for “mocks-only works.” After **every** migration phase (M0–M6), re-run the R5 smoke on **default mock settings** (`LOOP_SERVICE_MODE=mock-module`, no live URLs) and confirm exit 0 + golden audit PASS before merging. |
| **R6** | **Live ≠ mock golden.** Staging/live completeness uses `full_loop_live.json` (or checklist) — never require identical scores or evidence strings to the mock golden. |
| **R7** | **Mapping discipline.** Reject unmapped **required** API fields; **warn** on extra additive fields ([mapping.md](../integration/mapping.md)). Fix mappers, not upstream contracts, unless M0 snapshot proves a breaking change. |

### R5 smoke (re-run after each phase)

```bash
git checkout v0.3.1-hermes-installable   # bisect anchor only; on feature branches use HEAD with mock-module
unset MOCK_SELF_LEARNING_URL MOCK_SELF_QUESTIONING_URL MOCK_AERL_URL MOCK_AGENTEVALS_URL
export LOOP_SERVICE_MODE=mock-module
python scripts/mock_self_coaching_demo.py
# Linux CI equivalent:
bash tests/test_mock_self_coaching_demo.sh
```

**Expected:** exit 0; `completeness_report.json` with `status: PASS`; golden diff on invocation + semantic columns only (`tests/fixtures/golden/completeness_report_full_loop.json`).

On **`main` / feature branches**, run the same commands at **`LOOP_SERVICE_MODE=mock-module`** (no `--env-file` pointing at live URLs). The tag is the known-good anchor for bisect, not a requirement to develop from a detached HEAD.

### Phase overview

| Phase | Focus | Est. | Entry |
|-------|--------|------|-------|
| **M0** | Snapshot + contract freeze | ~3d | OpenAPI snapshots, fixture capture, mapping walk |
| **M1** | AgentEvals real adapter (read-only) | ~3d | **Start here** — holdout factory + `LOOP_HOLDOUT_TIMEOUT_S` |
| **M2** | Self-learning real adapter | ~3d | E-path with real learn + M1 eval |
| **M3** | Self-questioning real adapter | ~3d | C06/C07 endpoints + `staging.jsonl` writeback |
| **M4** | AERL training real adapter | ~5d | Full E+T loop on real train |
| **M5** | Agent registry real | ~2d | **Conditional** — only if a separate registry service exists |
| **M6** | Harden + cut to staging-default | ~3d | `demo.live.env`, opt-in CI matrix, runbook, release tag |

**Calendar:** ~20d (M5 +2d if separate registry). Buffer for VPN/auth/staging flakiness.

### Carry-over watchlist

| ID | Item | When to act |
|----|------|-------------|
| **M-W1** | Scorer 3-band collapse | Revisit if `LOOP_TAU_FAIL` (τ_fail) is tuned away from `0.75`, or before **P5** multi-scenario manifests ship — online rubric bands must stay derivable from fixtures. |
| **M-W2** | Golden-audit regeneration cadence | When a migration phase **flips** a completeness row (invocation or semantic), land **one** dedicated commit that refreshes `completeness_report_full_loop.json` — no drive-by golden edits. |
| ~~**M-W3**~~ | ~~`LOOP_HOLDOUT_TIMEOUT_S`~~ | **Done (migration M1)** — `holdout_engine.py` + env knob; was hardcoded 5s in `_holdout_metrics`. |
| **M-W4** | Per-phase commit discipline | Same discipline as M-W2 through M0–M6: phase-scoped PRs, R5 green before merge, golden refresh only when that phase changes mock audit shape. |

---

## 3. Regression net (do not break)

| Asset | Role |
|-------|------|
| Tag **`v0.3.1-hermes-installable`** | R5 bisect anchor; Hermes install + mock loop validation |
| `tests/test_mock_self_coaching_demo.sh` | CI gate; **extend**, never replace |
| `tests/fixtures/golden/completeness_report_full_loop.json` | Mock audit shape (C01–C18 invocation/semantic columns) |
| `python scripts/mock_self_coaching_demo.py` | Cross-platform demo entry (Windows + Linux) |

**Golden policy:**

- **Mock CI:** diff against `completeness_report_full_loop.json` (status + per-row invocation/semantic only).
- **Staging/live:** use scenario `full_loop_live.json` and opt-in smoke `scripts/full_loop_live_smoke.py` (separate golden/checklist) — do not require identical scores/evidence strings to the mock golden.

---

## 4. Service access model

### 4.1 `LOOP_SERVICE_MODE`

Single knob that classifies the run (set in `scenarios/demo.env` or shell):

| Mode | Meaning | Typical use |
|------|---------|-------------|
| `mock-module` | In-process mock engines; no `MOCK_*_URL` | Default local dev + CI (fastest) |
| `mock-http` | HTTP to local mock stack (`127.0.0.1` ports) | Fidelity / split-stack smoke |
| `live` | Real staging/production URLs; `ORCHESTRATOR_*_BACKEND=agentevals` / `aerl` | Staging integration |

Do **not** infer mock vs live from hostname alone. Mode + explicit backend flags are authoritative.

### 4.2 Environment variables (canonical names)

Reuse **existing** repo names — no parallel `SELF_*_BASE_URL` tree.

| Concern | Env vars | Mock default | Live / staging |
|---------|----------|--------------|----------------|
| Mode | `LOOP_SERVICE_MODE` | `mock-module` | `live` |
| Agent / loop | `LOOP_AGENT_ID`, `LOOP_TAU_FAIL`, `LOOP_SIGMA_MIN`, `LOOP_SIGMA_PLAY`, `LOOP_BATCH_SIZE`, `LOOP_IDLE_AFTER` | see [demo.env.example](../../scenarios/demo.env.example) | same |
| Holdout timeout | `LOOP_HOLDOUT_TIMEOUT_S` | `5` (mock) | `300`–`600` (real) |
| Self-learning | `MOCK_SELF_LEARNING_URL`, `SELF_LEARNING_BASE_URL`, `LOOP_LEARN_MODE` | unset (in-process); `sync` | learner URL; `evolve` / `evolve_recent` for production API — see [self-learning-review-agent-plan.md](self-learning-review-agent-plan.md) |
| Self-questioning | `MOCK_SELF_QUESTIONING_URL` | unset | `https://…` |
| Training (AERL) | `MOCK_AERL_URL`, `TRAINER_BASE_URL` | unset / local mock | staging trainer URL |
| AgentEvals | `AGENTEVALS_BASE_URL`, `MOCK_AGENTEVALS_URL` | unset / local mock | staging AgentEvals |
| Eval/train backends | `ORCHESTRATOR_EVAL_BACKEND`, `ORCHESTRATOR_TRAIN_BACKEND` | `mock` | `agentevals` / `aerl` |
| Coaching facade | `ORCHESTRATOR_TRANSPORT`, `ORCHESTRATOR_BASE_URL` | `module` | `http` + URL |
| Suites | `AGENTEVALS_SUITE_ID`, `AGENTEVALS_SUITE_ID_HOLDOUT` | tool-use-* | from `GET /api/suites` |
| Auth | `MOCK_SERVICE_TOKEN`, `TRAINER_API_KEY`, `AGENTEVALS_API_KEY` (as needed) | optional local | required on staging |

**Template:** [scenarios/demo.env.example](../../scenarios/demo.env.example) — copy to `scenarios/demo.env` (gitignored) and pass `--env-file` to the demo runner (when wired).

### 4.3 Code layers (no duplicate clients)

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Low-level HTTP | `services/adapters/agentevals_client.py`, `aerl_client.py` | REST to external APIs |
| Orchestrator-shaped | `services/adapters/eval_adapter.py`, `train_adapter.py` | `evaluate` / `train` contract |
| Composite | `services/adapters/composite_client.py` | `build_composite_client()` |
| Loop env | `modes/self-coaching/loop_env.py`, `build_loop_client()` | Load `.env`, apply mode (**shipped**, migration M1) |
| Holdout | `services/adapters/holdout_engine.py` | `create_run` / `get_run` for `_holdout_metrics` (**shipped**, migration M1) |
| Learn (planned) | `services/adapters/self_learning_client.py`, `learn_adapter.py` | Review API + `learn()` mapping (**migration M2**) |

**Do not** add a parallel `integrations/*/http_client.py` tree; extend `services/adapters/`.

### 4.4 Known gaps (post-M1)

1. ~~Holdout ignores `AGENTEVALS_BASE_URL`~~ — fixed: `services/adapters/holdout_engine.py` + `LOOP_HOLDOUT_TIMEOUT_S`.
2. ~~`default_client` / `build_loop_client()` not wired~~ — fixed in `loop_env.py` + `self_coaching_loop.py`.
3. ~~**`full_loop_live.json`**~~ — shipped; opt-in smoke `scripts/full_loop_live_smoke.py` (C12+C18 golden).
4. **Self-questioning** read path uses `curated/staging.jsonl` — real adapters must **write back** the same file (writeback contract §4.5; **M3**).

### 4.5 Self-questioning proceed contract (M3)

Pipeline backend returns **`proceed: true/false`** after a remote job completes. The loop uses this to decide whether to advance; it does **not** mirror Supabase rows into `staging.jsonl` at this stage.

Mock backend still writes `staging.jsonl` and the loop reads it. Pipeline backend sets `pipeline_service: true` and skips the local read path.

C06 uses `generate_suite`; C07 uses `generate_batch` — both map to `POST /api/pipeline/submit` + poll.

**Deferred:** Supabase `query_bank` → `staging.jsonl` export (only needed if T-path must train from locally curated pipeline data).

---

## 5. CI strategy

| Job | When | Command |
|-----|------|---------|
| Mock module (required) | Every PR | `python scripts/mock_self_coaching_demo.py` or `bash tests/test_mock_self_coaching_demo.sh` |
| Mock HTTP | PR or nightly | `python scripts/mock_self_coaching_demo.py --with-http` |
| Staging live | Opt-in / `integration/*` changes | `LOOP_SERVICE_MODE=live` + secrets; **not** default on all PRs |

Extend `tests/test_mock_self_coaching_demo.sh`; do not replace it.

---

## 6. Migration phases

**Per-phase checklist (all phases):** R5 green on `mock-module` · scoped PR (R4) · golden refresh only if a row flips (M-W2/M-W4) · phase exit criteria met.

### M0 — Snapshot + contract freeze (~3 days) — **partial** (overlapped M1)

**Goal:** Real OpenAPI shapes and fixtures; no live calls in CI.

**Build:**

- [x] `docs/integration/api-snapshots/agentevals-openapi.json` (2026-06-10)
- [x] `tests/fixtures/agentevals/run_detail_memoryarena_succeeded.json` (live capture)
- [x] [mapping.md](../integration/mapping.md) — AgentEvals `RunDetail` → `EvalMetrics` (active)
- [x] `docs/integration/api-snapshots/self-learning-openapi.json` — migration M2.0
- [x] `docs/integration/api-snapshots/pipeline-service-openapi.json` — migration M3.0 (2026-06-16)
- [ ] `docs/integration/api-snapshots/self-questioning-openapi.json`
- [x] `docs/integration/api-snapshots/aerl-openapi.json` — migration M4.0 (2026-06-16)
- [ ] Document auth per service in one place (Bearer, API keys) — partial via env templates

**Exit:** Every **shipped** adapter has a real-shape fixture. **R5** mock golden audit still passes. No live calls in default CI. Remaining snapshots gate M2–M4.

**Mapping rule:** R7 — reject unmapped **required** fields; **warn** on extra API fields.

---

### M1 — AgentEvals real adapter, read-only (~3 days) — **PASS**

**Why first:** Read-only; failure = “can’t promote”, not corrupt state. First code phase after contract snapshots (M0 may overlap).

**Build:**

- Holdout factory in `loop_driver._holdout_metrics` keyed off `ORCHESTRATOR_EVAL_BACKEND` + `AGENTEVALS_BASE_URL`
- Reuse `AgentEvalsClient` + `AgentEvalsEvalAdapter`; add thin `create_run`/`get_run` surface matching `MockAgentEvalsEngine` where needed
- **`LOOP_HOLDOUT_TIMEOUT_S` env knob** (M-W3 — replace hardcoded 5s in `_holdout_metrics`; default 5s mock, 300s+ live)
- Map `metrics` → `EvalMetrics.score` per mapping.md (critical for **C18**)

**Tests:**

- Replay from captured `run_detail` fixture (mock HTTP; `unittest.mock` or optional `respx`)
- `tests/test_holdout_timeout.py`
- **R5** mock demo script stays green (staging tests are opt-in)

**Exit:** Staging AgentEvals drives holdout gate; C12 invocation + C18 semantic pass under `full_loop_live` scenario (separate golden if needed). **R5** PASS before merge.

---

### M2 — Self-learning real adapter (~3 days)

**Spec (DRAFT):** [self-learning-review-agent-plan.md](self-learning-review-agent-plan.md) — independent review agent (`POST /learning/evolve`, `/learning/evolve/recent`, `GET /learning/status`), adapter-backed `learn()`. **Tasks:** spec §11 (M2.0–M2.5).

**Build:**

- Factory in learn path (`MOCK_SELF_LEARNING_URL` / `SELF_LEARNING_BASE_URL`; `LOOP_LEARN_MODE=sync|evolve|evolve_recent`)
- Preserve `source="loop-e-path"` verbatim
- Mapper: review job terminal response → `draft_version_id` + `components` for `registry.activate`
- Mock extension: production learner routes on `mock_self_learning.py` (§8 of spec)

**Tests:** E-path against staging self-learning + M1 AgentEvals; mock self-questioning + mock AERL.

**Exit:** E-path end-to-end with real learn + real eval. Local `support.jsonl` / loop store unchanged.

**Registry:** Use local `AgentRegistry` under coaching root unless M5 applies — do **not** block M2 on remote registry.

---

### M3 — Self-questioning real adapter (~3 days)

**Tracker:** [self-questioning-pipeline-implementation.md](self-questioning-pipeline-implementation.md) (sprint tasks SP-T01–SP-T24).  
**Service:** Self-Questioning Pipeline API (`PIPELINE_SERVICE_URL`) — not the mock `/self-questioning/generate` shape.

**Build:**

- `PipelineServiceClient` + `SelfQuestioningPipelineEngine` (maps C06/C07 → `/api/pipeline/submit`)
- Writeback to `staging.jsonl` (§4.5) — Supabase export or pipeline-team option
- Factory keyed off `ORCHESTRATOR_SELF_QUESTIONING_BACKEND` + `PIPELINE_SERVICE_URL`

**Tests:**

- `tests/integration/test_pipeline_service_availability.py` (dry_run, opt-in live)
- `test_loop_self_questioning_sparse` / `test_loop_t_path` against staging (C06/C07)
- R5 mock-module unchanged

**Exit:** C07 then C06 pass on staging; mock path unchanged when backend=mock.

---

### M4 — AERL training real adapter (~5 days) — **partial** (M4.0–M4.3 + M4.5 done; production CLI pending)

**HTTP mock spec:** [self-tuning-trainer-api-plan.md](self-tuning-trainer-api-plan.md) — frozen M4.0; mock trainer + `TrainerClient`/`RestClient` + loop wiring shipped.  
**Production path:** [cli-training-integration-plan.md](cli-training-integration-plan.md) — db_bridge remote shell (supersedes HTTP for GPU host).  
**Tracker:** [cli-training-implementation.md](cli-training-implementation.md) — sprint tasks CT-T01+; v1 scope = trigger + status only.

**Done (2026-06-16):**

- [x] Production-shaped mock (`mock_aerl.py` M4.1)
- [x] `trainer_client.py`, `trainer_rest_client.py`, `train_mapping.py`, `AERLTrainAdapter` (M4.2)
- [x] `build_loop_client` + mock-http aerl backend (M4.3)
- [x] `aerl-openapi.json` placeholder + Coaching OpenAPI `TrainingRequest` extensions (M4.0)
- [x] R5 mock-module regression green (M4.5)

**Remaining:**

- [x] CLI train adapter + transport — Sprints 0–3 done (2026-06-16); see [cli-training-implementation.md](cli-training-implementation.md)
- [ ] Dataset handoff: loop buffer `train.jsonl` → remote path (CT-D01)
- [ ] Full T-path live E2E: train + holdout + promote (CT-D04/D05)
- [ ] `tests/test_aerl_train_timeout.py` (long GRPO poll budget) — reuse for CLI timeout tests

**Build:**

- Extend `AERLTrainAdapter` / `AERLClient` (rollout, reward validate, snapshot)
- Loop stays **synchronous** in adapter (blocks on poll; `AERL_TIMEOUT_S` for long GRPO)
- Dataset handoff via `dataset_refs` (file / s3 / https per deployment)
- `candidate_model_id` → real checkpoint ref in `registry.create_version`
- GRPO: `LOOP_TRAIN_ROLLOUT_CONFIG` or inline `rollout.llm_proxy` on API
- Longer `LOOP_HOLDOUT_TIMEOUT_S` when training is real

**Tests:** `test_loop_t_path` promote + reject on staging; `tests/test_aerl_train_timeout.py`; rollout/reward validate fixtures

**Exit:** Full E+T loop on all real services; completeness PASS for **live scenario rows**; **R5** mock CI unchanged.

---

### M5 — Agent registry (conditional, ~2 days)

Only if a **separate** registry service exists. Otherwise local `mock_agent_registry` remains the store under `{coaching_root}/agents/`.

---

### M6 — Harden + cut to staging-default (~3 days)

**Build:**

- `LOOP_SERVICE_MODE=live` + `scenarios/demo.live.env.example` for staging operators
- CI matrix: staging smoke on `integration/*` changes (opt-in; R3)
- Runbook: three flows (mock-module, mock-http, live)
- Tag `v0.4.0-self-coaching-staging` when live path proven

**Do not** flip repo-wide default to live — explicit `LOOP_SERVICE_MODE` only. Mock-module remains the PR default and **R5** anchor.

**Exit:** Staging profile documented and smoke-tested; **R5** still green on `v0.3.1-hermes-installable` mock path.

---

## 7. Dependency graph

```text
M0 (contracts)
 │
 ▼
M1 (AgentEvals read)
 │
 ▼
M2 (self-learning) ──► M3 (self-questioning)   # M3 may parallelize with M2
 │                        │
 └──────────┬─────────────┘
            ▼
M4 (AERL train)
 │
 ▼
M5? (registry, if separate)
 │
 ▼
M6 (staging-default profile + tag)
```

---

## 8. Completed prerequisites (migration M1)

Shipped before / during migration M1; retained for reference.

| Item | Path | Status |
|------|------|--------|
| Env template | `scenarios/demo.env.example` | shipped |
| Loop env loader | `modes/self-coaching/loop_env.py` | shipped |
| Demo `--env-file` | `scripts/mock_self_coaching_demo.py` | shipped |
| Live scenario | `scenarios/full_loop_live.json` | shipped |
| Holdout smoke | `scripts/full_loop_live_smoke.py` | shipped |

---

## 9. Related commands

| Today (mock) | Staging (future) |
|--------------|------------------|
| `python scripts/mock_self_coaching_demo.py` | `LOOP_SERVICE_MODE=live python scripts/mock_self_coaching_demo.py --env-file scenarios/demo.env` |
| `bash tests/test_mock_self_coaching_demo.sh` | `STAGING_SMOKE=1 …` (opt-in CI) |
| [runbook § Mock loop demo](../guides/runbook.md#mock-loop-demo) | Same section, live subsection (M6) |

---

*Last updated: 2026-06-23. Track progress in [progress.md](progress.md). Next: live Track 1 green (C07 timeout fix) + CT-D01 dataset handoff.*
