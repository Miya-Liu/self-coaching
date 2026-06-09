# Mock platform design (M1.5)

Deterministic mock services for the full self-coaching / coach evolution loop **without** real AgentEvals, AERL, or production agent APIs.

**Status:** Phases 0–4 implemented (mock T2 stack — facade + split services). Production T2 (M2) deploy deferred. Live staging smoke remains.

Related: [roadmap.md](roadmap.md), [integration-plan.md](integration-plan.md), [mock-services/README.md](../../mock-services/README.md).

---

## Problem

`mock_self_coaching.py` bundles learn, self-play, eval, and train in one process (`:8765`). That suffices for T1 smoke tests but does not match the integration spine:

```text
Orchestrator -> CompositeClient
                 +-- evaluate     -> AgentEvals      (:8080)
                 +-- learn        -> Self-learning   (:8766)
                 +-- self_play    -> Self-play       (:8767)
                 +-- train        -> AERL            (:8004)
```

Coach mode and `ORCHESTRATOR_EVAL_BACKEND=agentevals` need a **separate AgentEvals-shaped** service and a **version registry** for `agent_config.version_id` lineage.

---

## Target topology

```text
                    +-----------------------------+
                    |   Mock Agent Registry       |
                    |   skills / tools / memory / |
                    |   model_id per version      |
                    +-------------+---------------+
                                  |
     +----------------------------+----------------------------+
     |                            |                            |
+----v----------+   +------------v-----------+   +----------v---------+
| Mock          |   | Mock Self-Learning     |   | Mock Self-Play       |
| AgentEvals    |   | :8766                  |   | :8767                |
| :8080         |   +------------------------+   +----------------------+
+----------------+
                                  |
                    +-------------v-------------+
                    | Mock AERL                 |
                    | :8004                     |
                    +---------------------------+
```

`mock_self_coaching.py` remains a **compatibility facade** during migration (`run-all`, CI, `install-skill-pack.sh --with-mock`).

---

## Phase 0 — Registry + AgentEvals (done in repo)

| Deliverable | Path |
|-------------|------|
| Design doc | this file |
| Agent registry | `mock-services/mock_agent_registry.py` |
| AgentEvals mock | `mock-services/mock_agentevals.py` |
| Stack helper | `scripts/mock-stack-up.sh` |
| Evaluate facade | `MOCK_AGENTEVALS_URL` → delegate from `mock_self_coaching.evaluate()` |

### Mock Agent Registry

Persists under `{data_dir}/agents/{agent_id}/`:

- `meta.json` — agent metadata
- `active.json` — `{ "version_id": "..." }`
- `versions/{version_id}.json` — full version document

Version document:

```json
{
  "version_id": "ver-0001",
  "agent_id": "example-agent",
  "parent_version_id": null,
  "active": true,
  "components": {
    "model_id": "model-base-v1",
    "skill_bundle_version": "skills-bootstrap",
    "tools_ref": "tools-v1",
    "memory_ref": "mem-bootstrap"
  },
  "source": "bootstrap",
  "created_at": "2026-06-07T12:00:00Z"
}
```

Optional HTTP (`mock_agent_registry.py serve --port 8768`) mirrors production agent **version slice** for coach demos.

### Mock AgentEvals

Implements snapshot-compatible endpoints:

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | Liveness |
| GET | `/api/suites` | Built-in + registered suites |
| GET | `/api/suites/{id}` | Suite detail |
| POST | `/api/suites` | **Mock extension** — register customised suite |
| POST | `/api/runs` | `201` + async run (`queued` → `succeeded`) |
| GET | `/api/runs/{id}` | `RunDetail` + `metrics` |

Scoring reads `RunCreate.agent_config.version_id` via registry; deterministic rules (`bad` / `regress` in id → lower score; holdout suite stricter).

### Wiring

```bash
# Terminal 1 — registry data + AgentEvals (shares --data-dir)
python mock-services/mock_agentevals.py serve --data-dir mock-services/demo-stack --port 8080

# Terminal 2 — coaching API (optional for module-only flows)
python mock-services/mock_self_coaching.py serve --root mock-services/demo-stack --port 8765

# Orchestrator / facade
export AGENTEVALS_BASE_URL=http://127.0.0.1:8080
export ORCHESTRATOR_EVAL_BACKEND=agentevals
export AGENTEVALS_SUITE_ID=tool-use-canary
export AGENTEVALS_SUITE_ID_HOLDOUT=tool-use-holdout

# Facade evaluate() delegation
export MOCK_AGENTEVALS_URL=http://127.0.0.1:8080
```

Or: `bash scripts/mock-stack-up.sh`

---

## Phase 1 — Self-learning + versioning ✓

| Deliverable | Path |
|-------------|------|
| Self-learning mock | `mock-services/mock_self_learning.py` |
| Classify + route | `POST /learning/events`, `POST /learning/classify` |
| Registry drafts | In-process `AgentRegistry` (shared `--data-dir`) |
| Facade | `mock_self_coaching.learn()` → engine or `MOCK_SELF_LEARNING_URL` |
| Smoke | `scripts/mock-self-learning-smoke.sh` |

Classifications: `memory`, `skill_patch`, `eval_case_candidate`, `training_candidate`, `error_log`.
Draft versions are created for memory/skill_patch/training_candidate; activation stays behind eval gate.

---

## Phase 2 — Self-play → suite registration ✓

| Deliverable | Path |
|-------------|------|
| Self-play mock | `mock-services/mock_self_play.py` |
| Failure-conditioned suite | `POST /self-play/generate-suite` → `MockSelfPlayEngine.generate_suite()` |
| Batch buffer fill | `POST /self-play/generate` → `MockSelfPlayEngine.generate_batch()` |
| Suite registration | Both paths → AgentEvals `POST /api/suites` + `curate_data.py` |
| Curation | `scripts/curate_data.py` wired in engine + orchestrator `curation.json` |
| Facade | `mock_self_coaching.self_play()` → **`generate_batch` only** (T-path / C07); E-path uses `generate-suite` directly |
| Smoke | `scripts/mock-self-play-smoke.sh` |

**Two endpoints, two jobs** (used by [self-coaching-demo-pipeline-plan.md](self-coaching-demo-pipeline-plan.md) §3.3 vs §3.4):

| Endpoint | Engine method | When | Key request params |
|----------|---------------|------|-------------------|
| `POST /self-play/generate-suite` | `generate_suite()` | E-path sparse augment (C06): `0 < \|Σ\| ≤ σ_play` | `user_query`, `trajectory`, `eval_score`, `mode` (default `adversarial`), `n_variants` |
| `POST /self-play/generate` | `generate_batch()` | T-path buffer top-up (C07): idle and `\|B\| < β` | `capability`, `n` (= `β - \|B\|`) |

`generate-suite` is a **mock extension** (failure-conditioned variants + suite register). `generate` matches the Coaching API contract in `openapi.yaml`. They are **not** one endpoint with a `mode` switch.

---

## Phase 3 — AERL mock ✓

| Deliverable | Path |
|-------------|------|
| AERL mock | `mock-services/mock_aerl.py` |
| Async runs | `POST /v1/training/runs`, `GET /v1/training/runs/{id}` |
| Pipeline argv | `POST /v1/pipelines/{sft\|grpo}/run` (for `run-pipeline.sh`) |
| Registry drafts | New `model_id` draft version per run |
| Adapters | `services/adapters/aerl_client.py`, `train_adapter.py` |
| Composite | `ORCHESTRATOR_TRAIN_BACKEND=aerl` → `CompositeClient.train()` |
| Facade | `mock_self_coaching.train()` → engine or `MOCK_AERL_URL` |
| Smoke | `scripts/mock-aerl-smoke.sh` |

Production AERL may live in an external repo; this mock ships in-repo for CI and coach demos.

---

## Phase 4 — Coach demo pack ✓

| Deliverable | Path |
|-------------|------|
| Coach demo | `scripts/mock-coach-demo.sh` |
| Demo registry | `modes/coach/agents.demo.yaml` |
| Two agents | `agent-promote` (registry activate) / `agent-reject` (draft left inactive) |
| Full stack | AgentEvals + Self-Learning + Self-Play + AERL (+ Coaching API health) |
| Orchestrator | `record-eval` → `check-drop` → `run` (model path via env) |
| CI | `integration-mock-stack` job in `.github/workflows/ci.yml` |

Uses `ORCHESTRATOR_TRANSPORT=module` so each agent keeps its own coaching root.

---

## Facade lifecycle

`mock_self_coaching.py` is **not** removed when production T2 (M2) lands. Kept through M2 for `install-skill-pack.sh --with-mock` parity; reviewed at M3 (retire, keep as shim, or freeze at v1).

---

## Mode usage

| Mode | Default | Mock stack |
|------|---------|------------|
| **Self-coaching** | `module` transport, monolith | Opt-in `mock-stack-up.sh` |
| **Coach** | `http` + `agentevals` | Registry + AgentEvals + orchestrator |

---

## Exit criteria (full mock platform)

- [x] Coach demo without external services (Phase 4)
- [x] Phase 0: registry + AgentEvals mock + orchestrator `record-eval` against mock
- [x] Self-play registers suites in AgentEvals (Phase 2)
- [x] Self-learning bumps `skill_bundle_version` (skill_patch path; `test_mock_self_learning`)
- [x] AERL mock returns new `model_id` (Phase 3)
- [x] Production-readiness harness PASS (`mock-services/production_readiness.py`, CI)
- [x] Monolithic `run-all` via facade (`scripts/mock-facade-run-all.sh`, split-stack delegation)

---

## Phase 5 — Self-coaching loop demo (planned)

Continuous task-stream demo on mocks (dual E/T evolution paths, generation-scoped buffer, completeness audit). Not started — see [self-coaching-demo-pipeline-plan.md](self-coaching-demo-pipeline-plan.md).

---

## Open decisions

| Topic | Decision | Notes |
|-------|----------|-------|
| Separate ports | Yes | Matches real deploy |
| Registry separate from self-learning | Yes | Shared lineage store |
| `POST /api/suites` | Mock-only extension | Documented here + AgentEvals mock |
| SQLite persistence | Deferred | JSON files under `--data-dir` for now |
| AERL location | Mock in-repo; prod external | Phase 3 mock done |
