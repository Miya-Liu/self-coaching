# Mock platform design (M1.5)

Deterministic mock services for the full self-coaching / coach evolution loop **without** real AgentEvals, AERL, or production agent APIs.

**Status:** Phase 0 implemented (registry + AgentEvals mock). Phases 1–4 planned.

Related: [roadmap.md](roadmap.md), [integration-plan.md](integration-plan.md), [mock-services/README.md](../../mock-services/README.md).

---

## Problem

`mock_self_coaching.py` bundles learn, self-play, eval, and train in one process (`:8765`). That suffices for T1 smoke tests but does not match the integration spine:

```text
Orchestrator → CompositeClient
                 ├── evaluate     → AgentEvals      (:8080)
                 ├── learn        → Self-learning   (:8766, planned)
                 ├── self_play    → Self-play       (:8767, planned)
                 └── train        → AERL            (:8004, external)
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
│ AgentEvals   │   │ :8766 (Phase 1)      │   │ :8767 (Phase 2)      │
│ :8080        │   └──────────────────────┘   └──────────────────────┘
└──────────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Mock AERL           │
                    │ :8004 (Phase 3,     │
                    │  lives in AERL repo)│
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

## Phase 1 — Self-learning + versioning (planned)

- `mock_self_learning.py` on `:8766`
- `POST /learning/events` with classification → registry draft versions
- Skill patches, memory append, ERROR.md routing per `self-learning/SKILL.md`

---

## Phase 2 — Self-play → suite registration (planned)

- `mock_self_play.py` on `:8767`
- `POST /self-play/generate-suite` — input: user query, trajectory, eval score
- Output: `suite_id` via AgentEvals `POST /api/suites`
- Wire `scripts/curate_data.py` into pipeline

---

## Phase 3 — AERL mock (planned, **AERL repo**)

- `POST /v1/training/runs` + poll — returns `candidate_model_id`
- Auto-upgrade: `services/adapters/aerl_client.py` + `CompositeClient.train()`
- v1 argv endpoint retained for `run-pipeline.sh`

---

## Phase 4 — Coach demo pack (planned)

- `scripts/mock-coach-demo.sh` — two agents, drop loop, promote/reject
- CI job `integration-mock-stack`

---

## Mode usage

| Mode | Default | Mock stack |
|------|---------|------------|
| **Self-coaching** | `module` transport, monolith | Opt-in `mock-stack-up.sh` |
| **Coach** | `http` + `agentevals` | Registry + AgentEvals + orchestrator |

---

## Exit criteria (full mock platform)

- [ ] Coach demo without external services
- [x] Phase 0: registry + AgentEvals mock + orchestrator `record-eval` against mock
- [ ] Self-play registers suites in AgentEvals
- [ ] Self-learning bumps `skill_bundle_version`
- [ ] AERL mock returns new `model_id`
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
| AERL location | External repo | Phase 3 |
