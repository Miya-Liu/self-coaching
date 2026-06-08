# Mock platform design (M1.5)

Deterministic mock services for the full self-coaching / coach evolution loop **without** real AgentEvals, AERL, or production agent APIs.

**Status:** Phases 0–4 implemented (full mock platform). Live staging smoke remains.

Related: [roadmap.md](roadmap.md), [integration-plan.md](integration-plan.md), [mock-services/README.md](../../mock-services/README.md).

---

## Problem

`mock_self_coaching.py` bundles learn, self-play, eval, and train in one process (`:8765`). That suffices for T1 smoke tests but does not match the integration spine:

```text
Orchestrator → CompositeClient
                 ├── evaluate     → AgentEvals      (:8080)
                 ├── learn        → Self-learning   (:8766)
                 ├── self_play    → Self-play       (:8767)
                 └── train        → AERL            (:8004)
```

Coach mode and `ORCHESTRATOR_EVAL_BACKEND=agentevals` need a **separate AgentEvals-shaped** service and a **version registry** for `agent_config.version_id` lineage.

---

## Target topology

```text
                    ┌─────────────────────────────┐
                    │   Mock Agent Registry       │
                    │   skills / tools / memory / │
                    │   model_id per version      │
                    └──────────┬──────────────────┘
                               │
     ┌─────────────────────────┼─────────────────────────┐
     │                         │                         │
┌────▼─────────┐   ┌───────────▼──────────┐   ┌──────────▼─────────┐
│ Mock         │   │ Mock Self-Learning   │   │ Mock Self-Play       │
│ AgentEvals   │   │ :8766                │   │ :8767                │
│ :8080        │   └──────────────────────┘   └──────────────────────┘
└──────────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Mock AERL           │
                    │ :8004               │
                    └─────────────────────┘
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
| Suite registration | `POST /self-play/generate-suite` → AgentEvals `POST /api/suites` |
| Legacy batch | `POST /self-play/generate` (Coaching API compatible) |
| Curation | `scripts/curate_data.py` wired in engine + orchestrator `curation.json` |
| Facade | `mock_self_coaching.self_play()` → engine or `MOCK_SELF_PLAY_URL` |
| Smoke | `scripts/mock-self-play-smoke.sh` |

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
- [ ] Self-learning bumps `skill_bundle_version`
- [x] AERL mock returns new `model_id` (Phase 3)
- [ ] Production-readiness report PASS
- [ ] Monolithic `run-all` still passes via facade

---

## Open decisions

| Topic | Decision | Notes |
|-------|----------|-------|
| Separate ports | Yes | Matches real deploy |
| Registry separate from self-learning | Yes | Shared lineage store |
| `POST /api/suites` | Mock-only extension | Documented here + AgentEvals mock |
| SQLite persistence | Deferred | JSON files under `--data-dir` for now |
| AERL location | Mock in-repo; prod external | Phase 3 mock done |
