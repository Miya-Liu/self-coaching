# Mock → real API migration plan

**Status:** **M1 AgentEvals PASS** (2026-06-10) — live smoke + holdout factory; `full_loop_live` E2E pending  
**Ground truth:** tag **`v0.3.1-hermes-installable`** — mocks-only “it works” pin (Hermes pack + loop demo)  
**Related:** [self-coaching-demo-pipeline-plan.md](self-coaching-demo-pipeline-plan.md), [integration-plan.md](integration-plan.md), [integration/mapping.md](../integration/mapping.md), [mock-platform-design.md](mock-platform-design.md), [install-as-hermes-skill.md](../guides/install-as-hermes-skill.md)

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
unset MOCK_SELF_LEARNING_URL MOCK_SELF_PLAY_URL MOCK_AERL_URL MOCK_AGENTEVALS_URL
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
| **M3** | Self-play real adapter | ~3d | C06/C07 endpoints + `staging.jsonl` writeback |
| **M4** | AERL training real adapter | ~5d | Full E+T loop on real train |
| **M5** | Agent registry real | ~2d | **Conditional** — only if a separate registry service exists |
| **M6** | Harden + cut to staging-default | ~3d | `demo.live.env`, opt-in CI matrix, runbook, release tag |

**Calendar:** ~20d (M5 +2d if separate registry). Buffer for VPN/auth/staging flakiness.

### Carry-over watchlist

| ID | Item | When to act |
|----|------|-------------|
| **M-W1** | Scorer 3-band collapse | Revisit if `LOOP_TAU_FAIL` (τ_fail) is tuned away from `0.75`, or before **P5** multi-scenario manifests ship — online rubric bands must stay derivable from fixtures. |
| **M-W2** | Golden-audit regeneration cadence | When a migration phase **flips** a completeness row (invocation or semantic), land **one** dedicated commit that refreshes `completeness_report_full_loop.json` — no drive-by golden edits. |
| **M-W3** | `LOOP_HOLDOUT_TIMEOUT_S` | Declared in [demo.env.example](../../scenarios/demo.env.example); **implement in M1** — `_holdout_metrics` hardcodes 5s today and is the first failure mode on real AgentEvals. |
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
- **Staging/live:** use scenario `full_loop_live.json` (future) and a **separate** golden or checklist — do not require identical scores/evidence strings to the mock golden.

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
| Self-learning | `MOCK_SELF_LEARNING_URL` | unset (in-process) | `https://…` |
| Self-play | `MOCK_SELF_PLAY_URL` | unset | `https://…` |
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
| Loop (to add) | `modes/self-coaching/loop_env.py`, `build_loop_client()` | Load `.env`, apply mode, same as orchestrator |
| Holdout (to add) | `services/adapters/holdout_engine.py` or factory in `loop_driver` | `create_run` / `get_run` for `_holdout_metrics` |

**Do not** add a parallel `integrations/*/http_client.py` tree; extend `services/adapters/`.

### 4.4 Known gaps (post-M1)

1. ~~Holdout ignores `AGENTEVALS_BASE_URL`~~ — fixed: `services/adapters/holdout_engine.py` + `LOOP_HOLDOUT_TIMEOUT_S`.
2. ~~`default_client` / `build_loop_client()` not wired~~ — fixed in `loop_env.py` + `self_coaching_loop.py`.
3. **`full_loop_live.json`** — not yet shipped; migration M1 loop E2E on live holdout (C12/C18) still open.
4. **Self-play** read path uses `curated/staging.jsonl` — real adapters must **write back** the same file (writeback contract §4.5; **M3**).

### 4.5 Self-play writeback contract (M3)

`augment_sigma_sparse` and `fill_buffer_batch` read `.self-coaching/curated/staging.jsonl`. Real self-play HTTP clients must:

1. Return trajectories in the HTTP response, **and**
2. Write the same rows to `staging.jsonl` so the loop read path stays unchanged.

C06 uses `POST /self-play/generate-suite`; C07 uses `POST /self-play/generate` — **not** a single endpoint with a mode flag.

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

### M0 — Snapshot + contract freeze (~3 days)

**Goal:** Real OpenAPI shapes and fixtures; no live calls in CI.

**Build:**

- `docs/integration/api-snapshots/agentevals-openapi.json` (pending)
- `docs/integration/api-snapshots/self-learning-openapi.json`
- `docs/integration/api-snapshots/self-play-openapi.json`
- `docs/integration/api-snapshots/aerl-openapi.json`
- Replace placeholder `tests/fixtures/agentevals/run_detail_succeeded.json` with captured shape
- Walk [mapping.md](../integration/mapping.md); fix mappers, not contracts
- Document auth per service (Bearer, API keys)

**Exit:** Every mapped field has a real-shape fixture. **R5** mock golden audit still passes. No live calls in default CI.

**Mapping rule:** R7 — reject unmapped **required** fields; **warn** on extra API fields.

---

### M1 — AgentEvals real adapter, read-only (~3 days) — **PASS** (live smoke; loop E2E open)

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

**Build:**

- Factory in learn path (`MOCK_SELF_LEARNING_URL` or live URL)
- Preserve `source="loop-e-path"` verbatim
- Mapper: real response → `draft_version_id` + `components` for `registry.activate`

**Tests:** E-path against staging self-learning + M1 AgentEvals; mock self-play + mock AERL.

**Exit:** E-path end-to-end with real learn + real eval. Local `support.jsonl` / loop store unchanged.

**Registry:** Use local `AgentRegistry` under coaching root unless M5 applies — do **not** block M2 on remote registry.

---

### M3 — Self-play real adapter (~3 days)

**Build:**

- `generate_suite` (C06) vs `generate_batch` (C07) — distinct endpoints
- Writeback to `staging.jsonl` (§4.5)
- Factory keyed off `MOCK_SELF_PLAY_URL`

**Tests:**

- `test_loop_self_play_sparse` against staging
- `tests/test_self_play_endpoint_distinction.py`

**Exit:** C06 + C07 pass on staging; mock path unchanged when URL unset.

---

### M4 — AERL training real adapter (~5 days)

**Build:**

- Reuse `AERLTrainAdapter` / `AERLClient`
- Loop stays **synchronous** (blocks on train)
- Dataset handoff (path vs upload) decided in **M0**
- `candidate` `model_id` → real artifact ref in `registry.create_version`
- Longer `LOOP_HOLDOUT_TIMEOUT_S` when training is real

**Tests:** `test_loop_t_path` promote + reject on staging; `tests/test_aerl_train_timeout.py`

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
M2 (self-learning) ──► M3 (self-play)   # M3 may parallelize with M2
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

## 8. Prerequisites before M1 (small, recommended)

| Item | Path | Purpose |
|------|------|---------|
| Env template | `scenarios/demo.env.example` | Document all knobs; copy → `demo.env` |
| Loop env loader | `modes/self-coaching/loop_env.py` | `load_demo_env()`, `apply_service_mode()`, `build_loop_client()` |
| Demo `--env-file` | `scripts/mock_self_coaching_demo.py` | Load profile before run |
| Live scenario | `scenarios/full_loop_live.json` | Staging completeness expectations (M1+) |

---

## 9. Related commands

| Today (mock) | Staging (future) |
|--------------|------------------|
| `python scripts/mock_self_coaching_demo.py` | `LOOP_SERVICE_MODE=live python scripts/mock_self_coaching_demo.py --env-file scenarios/demo.env` |
| `bash tests/test_mock_self_coaching_demo.sh` | `STAGING_SMOKE=1 …` (opt-in CI) |
| [runbook § Self-coaching demo](../guides/runbook.md#self-coaching-demo-mock-loop) | Same section, live subsection (M6) |

---

*Last updated: 2026-06-09. Track progress in [progress.md](progress.md).*
