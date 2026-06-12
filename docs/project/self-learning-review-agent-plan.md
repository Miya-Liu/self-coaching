# Self-learning review agent — API & migration plan

**Status:** **DRAFT** — for review and edit (API shapes from Hermes learner service, 2026-06-12)  
**Goal:** Define the **real self-learning backend** as an **independent review agent** (Dream / Auto Dream–style), exposed via **POST/GET HTTP APIs**, while preserving the existing loop and orchestrator **`learn()`** contract through adapters.

**Related:** [mock-to-real-migration.md](mock-to-real-migration.md) (M2), [pipelines.md](../design/pipelines.md), [coaching_api.md](../design/integrations/coaching_api.md), [integration-plan.md](integration-plan.md), [mapping.md](../integration/mapping.md) (AgentEvals — add self-learning section in M2).

---

## 1. Problem statement

### 1.1 What exists today

| Piece | Location | Behavior |
|-------|----------|----------|
| Loop E-path | `modes/self-coaching/loop_driver.py` | On Σ threshold → `client.learn(event, source="loop-e-path")` → sync response |
| Mock engine | `mock-services/mock_self_learning.py` | Classifies one `event` string; writes artifacts; drafts registry version in-process |
| HTTP (mock) | `POST /learning/events` | Same as engine; optional split-stack on `:8766` |
| Client | `mock-services/client.py` | `SelfCoachingClient.learn()` — no review-job surface |
| OpenAPI | `mock-services/contracts/openapi.yaml` | Single-event `LearningEventRequest` / `LearningEventRecord` only |

The mock treats self-learning as a **synchronous classifier** over a single event string. Production intent is different:

- Self-learning runs as an **independent agent** (forked reviewer), analogous to **Claude Code Dream / Auto Dream** or the **background review fork** in Hermes Agent.
- It is **triggered externally** (scheduler, coach, loop, manual API).
- It **reviews recent active sessions and trajectories** (default **24 hours**), not only the last failure line in Σ.
- It **updates memories and skills** asynchronously and returns **registry-facing joint metadata** when done.

### 1.2 What we need

1. **HTTP API** for starting and polling review jobs (`POST` + `GET`).
2. **Adapter parity** — loop and orchestrator keep calling `learn()`; mode/env selects sync event vs review-job backend (same pattern as AgentEvals holdout and AERL train).
3. **Mock extension** — deterministic review jobs in CI; **R5** mock-module gate unchanged.
4. **Mapping discipline** — terminal review response → `draft_version_id` + `components` for local `registry.activate()` (M2 uses local registry; M5 optional for remote registry).

---

## 2. Design principles

| ID | Principle |
|----|-----------|
| **SL-R1** | **Adapter parity, not replacement.** Extend `services/adapters/` and mock HTTP; do not fork parallel client trees. |
| **SL-R2** | **One orchestrator surface.** `SelfCoachingClient.learn()` remains the only loop/orchestrator entry; review jobs are an implementation detail behind the adapter. |
| **SL-R3** | **Agent is the service.** The learning backend is a long-running service that runs an agent worker; callers do not embed classification logic. |
| **SL-R4** | **Sync or async per `wait`.** Service auto-picks sync when `≤ 5` sessions; async returns `job_id` + `GET /learning/status/{job_id}` poll (like AgentEvals / AERL). |
| **SL-R5** | **Preserve `source="loop-e-path"`.** E-path must pass this verbatim for audit and tests (`tests/test_loop_e_path.py`). |
| **SL-R6** | **Joint metadata unchanged.** Terminal job must expose `draft_version_id`, `routing`, and `components` fields the loop already consumes. |
| **SL-R7** | **Local registry for M2.** Review agent may write artifacts remotely, but **activation** stays in the loop via local `AgentRegistry` unless M5 applies. |

---

## 3. Target architecture

```text
                    +---------------------------+
                    |  Triggers                 |
                    |  - Cron (Auto-learn)      |
                    |  - CI / webhook (targeted)|
                    |  - Loop E-path (Σ)        |
                    |  - Manual curl / CLI      |
                    +-------------+-------------+
                                  |
                                  v
                    +---------------------------+
                    |  Self-learning API        |
                    |  POST /learning/evolve    |
                    |  POST /learning/evolve/   |
                    |       recent              |
                    |  GET  /learning/status/id |
                    |  GET  /learn/sessions     |
                    +-------------+-------------+
                                  |
                                  v
                    +---------------------------+
                    |  Learning review agent    |
                    |  (forked AIAgent / host)  |
                    +-------------+-------------+
                                  |
                                  v
                         SessionDB (sessions)
                                  |
                                  v
                    +---------------------------+
                    |  Outputs (per session)    |
                    |  memory_writes,           |
                    |  skills_created/patched,  |
                    |  summary text             |
                    +-------------+-------------+
                                  |
                                  v
                    +---------------------------+
                    |  Adapter (this repo)      |
                    |  → draft_version_id,      |
                    |    routing, components    |
                    |  → registry.activate()    |
                    +---------------------------+
```

### 3.1 Trigger modes (mapped to real endpoints)

| Mode | Trigger | API | `wait` typical |
|------|---------|-----|----------------|
| **Auto-learn (Dream)** | Daily cron | `POST /learning/evolve/recent` `{ hours: 24 }` | `false` (async default for cron) |
| **Targeted review** | CI hook, post-meeting webhook, manual | `POST /learning/evolve` `{ session_ids: [...] }` | `true` if ≤5 sessions; else `false` |
| **Loop E-path (reactive)** | Σ failures | Adapter resolves session ids (or calls `/evolve/recent` with tight window) + `wait: true` | `true` (loop blocks) |
| **Discover candidates** | Ops / preflight | `GET /learn/sessions?hours=24` | — |
| **Mock / thin sync** | Legacy demo | `POST /learning/events` (in-repo mock only) | immediate |

**Note:** Production learner reads **SessionDB** — not `coaching_root` trajectories directly. Loop demo adapter must map Σ failures → `session_ids` or use `/evolve/recent` when session linkage exists.

---

## 4. HTTP API specification (production learner)

**Base path:** `{SELF_LEARNING_BASE_URL}` or `{MOCK_SELF_LEARNING_URL}`  
**Auth:** Bearer token — `401 unauthorized` on bad/missing token.  
**Path prefix:** Canonical prefix is `/learning/…`. Some response bodies reference `/learn/status/…` — normalize in client (see §14 Q7).

### 4.0 Common request fields

Shared by `POST /learning/evolve` and `POST /learning/evolve/recent`:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `evolve_memory` | bool | `true` | Run memory-review prompt branch |
| `evolve_skills` | bool | `true` | Run skill-review prompt branch |
| `max_iterations` | int | `16` | Per-fork cap (server clamps to ≤ 32) |
| `dry_run` | bool | `false` | Forward to fork: log proposed changes, don't write |
| `wait` | bool | auto | `true` = block until all forks join (sync, **200**); `false` = return `job_id` immediately (**202**). **Auto:** sync if ≤ 5 sessions, else async |

**Validation:** If `evolve_memory=false` **and** `evolve_skills=false` → **400** `invalid_request` (nothing to do).

### 4.1 `POST /learning/evolve` — targeted session review

Ask the target agent to review **specified sessions**. Use when an external system (CI hook, post-meeting webhook, manual curl, loop adapter with known `session_ids`) wants a targeted review.

**Request:**

```json
{
  "session_ids": ["sess_abc123", "sess_def456"],
  "evolve_memory": true,
  "evolve_skills": true,
  "dry_run": false,
  "wait": true
}
```

**Sync response (200, when `wait=true`):**

```json
{
  "status": "completed",
  "duration_ms": 18432,
  "results": [
    {
      "session_id": "sess_abc123",
      "status": "ok",
      "actions": {
        "memory_writes": 2,
        "skills_created": 0,
        "skills_patched": 1,
        "summary": "Saved 2 memory entries; patched skill 'github-pr-workflow' with pitfall about stale draft PRs."
      },
      "fork_iterations": 7,
      "tokens": {"input": 12450, "output": 890}
    },
    {
      "session_id": "sess_def456",
      "status": "skipped",
      "reason": "session has learn_optout=true"
    }
  ]
}
```

**Async response (202, when `wait=false`):**

```json
{
  "status": "queued",
  "job_id": "learn_2026-06-12T15-03-22_a1b2",
  "session_count": 2,
  "poll_url": "/learn/status/learn_2026-06-12T15-03-22_a1b2"
}
```

**Errors:**

| HTTP | Code | When |
|------|------|------|
| 400 | `invalid_request` | Empty `session_ids`, both review flags false, malformed JSON |
| 401 | `unauthorized` | Bad/missing bearer |
| 404 | `session_not_found` | At least one ID missing from SessionDB; body lists missing ids; **nothing reviewed** |
| 413 | `too_many_sessions` | Exceeds `learner.max_sessions_per_call` (default **50**) |
| 500 | `fork_error` | Host `AIAgent` construction failed (e.g. no LLM provider) |

### 4.2 `POST /learning/evolve/recent` — Auto-learn (trailing window)

Review every session active in the trailing window. **Auto-learn mode** — typically called by cron once per day.

**Request:**

```json
{
  "hours": 24,
  "evolve_memory": true,
  "evolve_skills": true,
  "max_sessions": 10,
  "wait": false
}
```

| Field | Default | Notes |
|-------|---------|-------|
| `hours` | `24` | Trailing window (float; min **1**, max **168** = 7d) |
| `max_sessions` | `10` | Fan-out cap. Sessions sorted by `last_active DESC`; excess skipped (reported in response) |
| Other fields | — | Same common fields as §4.0 |

**Response shape:** Identical to §4.1 (sync or async). Cron callers typically use `wait: false` regardless of count.

**Additional fields on completed / recent responses:**

```json
{
  "window": {"hours": 24, "from": "2026-06-11T15:03:22Z", "to": "2026-06-12T15:03:22Z"},
  "sessions_found": 14,
  "sessions_reviewed": 10,
  "sessions_skipped": [
    {"session_id": "sess_xyz", "reason": "max_sessions cap"},
    {"session_id": "sess_uvw", "reason": "learn_optout"}
  ]
}
```

### 4.3 `GET /learning/status/{job_id}` — poll async job

**Response (running):**

```json
{
  "status": "running",
  "job_id": "learn_2026-06-12T15-03-22_a1b2",
  "progress": {"completed": 3, "total": 10},
  "started_at": "2026-06-12T15:03:22Z",
  "eta_seconds": 42
}
```

**Response (completed):**

```json
{
  "status": "completed",
  "job_id": "learn_2026-06-12T15-03-22_a1b2",
  "started_at": "2026-06-12T15:03:22Z",
  "completed_at": "2026-06-12T15:04:18Z",
  "duration_ms": 56000,
  "results": []
}
```

(`results` array — same per-session shape as §4.1 sync response.)

**Errors:**

| HTTP | Code | When |
|------|------|------|
| 404 | `job_not_found` | Unknown or evicted `job_id` (retention: `learner.job_ttl_hours`, default **24**) |

### 4.4 `GET /learn/sessions` — discover candidate sessions

Convenience endpoint to preview what `/learning/evolve/recent` would select.

**Query params:** `hours` (default 24), `limit` (default 50), `include_optout` (default false).

**Response (200):**

```json
{
  "window": {"hours": 24, "from": "...", "to": "..."},
  "sessions": [
    {
      "session_id": "sess_abc123",
      "title": "Refactor billing module",
      "last_active": "2026-06-12T14:55:01Z",
      "message_count": 42,
      "platform": "cli",
      "learn_optout": false
    }
  ]
}
```

### 4.5 `POST /learning/optout` — per-session opt-out

**Request:**

```json
{"session_id": "sess_abc123", "optout": true}
```

**Response (200):**

```json
{"session_id": "sess_abc123", "optout": true, "updated_at": "..."}
```

Sets `sessions.metadata.learn_optout` in SessionDB. Honored by `/learning/evolve` (`status: skipped`) and `/learning/evolve/recent` (excluded from fan-out). Also available via CLI: `hermes session learn-optout <sid>`.

### 4.6 `GET /learning/health` — readiness probe

**Response (200):**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "host_agent_ready": true,
  "session_db": "connected",
  "active_jobs": 2,
  "queue_depth": 0
}
```

Returns **503** if the target agent cannot be constructed (e.g. provider misconfigured) so orchestrators (k8s, systemd) can mark the learner unhealthy.

### 4.7 `POST /learning/events` — mock / legacy sync path (in-repo only)

**Purpose:** Single-event ingest for the deterministic mock loop demo. **Not** part of the production learner API above.

Retained in `mock-services/mock_self_learning.py` and `mock-services/contracts/openapi.yaml` for R5 CI. Production adapter uses §4.1–4.3 instead when `LOOP_LEARN_MODE=evolve` or `evolve_recent`.

---

## 5. Input model — SessionDB vs loop artifacts

Production learner input is **SessionDB** (host-managed sessions), not files under `coaching_root`.

| Source | API / store | Used by |
|--------|-------------|---------|
| **Sessions (targeted)** | `session_ids` on `POST /learning/evolve` | Webhooks, loop adapter (when ids known) |
| **Sessions (window)** | `POST /learning/evolve/recent` `{ hours, max_sessions }` | Cron Auto-learn |
| **Session discovery** | `GET /learn/sessions?hours=24` | Preflight, coach UI |
| **Opt-out** | `POST /learning/optout` | User / CLI privacy control |

**Loop demo gap:** Mock loop writes `support.jsonl` and `trajectories/` under `coaching_root` but does **not** populate SessionDB. For live E-path + review API:

1. Host must link task runs → `session_id`, **or**
2. Adapter calls `/evolve/recent` with a short `hours` window and accepts broader review scope, **or**
3. Staging smoke uses `/learning/evolve` with explicit test `session_ids` (bypass loop Σ linkage until bridged).

| Mock-only (CI) | Production learner |
|----------------|-------------------|
| `coaching_root` trajectories + `classify_event()` | SessionDB + forked `AIAgent` prompts |
| `POST /learning/events` | `POST /learning/evolve` or `/evolve/recent` |

---

## 6. Output contract — production API → loop joint metadata

Production learner returns **per-session `results[]`** with `actions` counts — **not** `draft_version_id`. The **adapter in this repo** must normalize completed jobs into the shape `run_e_path` already consumes:

```python
# loop_driver.run_e_path (unchanged)
routing = result.get("routing") or {}
draft_id = result.get("draft_version_id") or routing.get("draft_version_id")
if draft_id:
    registry.activate(agent_id, draft_id)
```

### 6.1 Production result shape (source of truth)

Per-session entry in `results[]`:

| Field | When present | Meaning |
|-------|--------------|---------|
| `session_id` | always | Session reviewed |
| `status` | always | `ok` \| `skipped` \| `error` |
| `reason` | skipped | e.g. `learn_optout=true` |
| `actions.memory_writes` | ok | Memory branch wrote N entries |
| `actions.skills_created` | ok | New skill count |
| `actions.skills_patched` | ok | Patched skill count |
| `actions.summary` | ok | Human-readable summary |
| `fork_iterations` | ok | Iterations used (≤ `max_iterations`) |
| `tokens` | ok | `{ input, output }` usage |

Job-level: `status` = `completed` \| `queued` \| `running`; async uses `job_id`.

### 6.2 Adapter mapping rules (proposed)

Aggregate across all `results` where `status == "ok"`:

| Condition | `routing.classification` | Registry action (local M2) |
|-----------|--------------------------|----------------------------|
| `sum(skills_patched + skills_created) > 0` | `skill_patch` | `create_version` with new `skill_bundle_version`; set `draft_version_id` |
| `sum(memory_writes) > 0` only | `memory` | `create_version` with updated `memory_ref` |
| Both memory and skills | `skill_patch` | Single draft; merge both component bumps (skills take precedence for classification) |
| All `skipped` or all zero actions | `no_op` | No `draft_version_id`; skip `activate` |
| `dry_run: true` | — | Never activate; return summary only |

**`skill_bundle_version` generation:** Derive stable id from job `job_id` or hash of `actions.summary` (adapter-owned until production registry API returns version ids — M5).

**`source` on learn record:** Adapter appends `learning_events.jsonl` row with `source` from caller (`loop-e-path` preserved).

### 6.3 Normalized `learn()` response (adapter output)

After mapping, adapter returns mock-compatible dict for loop:

```json
{
  "id": "learn-<derived>",
  "source": "loop-e-path",
  "classification": "skill_patch",
  "draft_version_id": "ver-<adapter-created>",
  "routing": {
    "classification": "skill_patch",
    "draft_version_id": "ver-<adapter-created>",
    "skill_bundle_version": "skills-<hash>",
    "next_artifact": "skill_patch"
  },
  "job_id": "learn_2026-06-12T15-03-22_a1b2",
  "review_summary": "Saved 2 memory entries; patched skill 'github-pr-workflow'…",
  "sessions_reviewed": 2
}
```

### 6.4 Mock `POST /learning/events` mapping (CI)

| Canonical (adapter) | Mock `classification` | Coaching OpenAPI |
|---------------------|-------------------------|------------------|
| `skill_patch` | `skill_patch` | `skill_patch_candidate` |
| `memory` | `memory` | — |
| `eval_case_candidate` | `eval_case_candidate` | — |
| `no_op` | (no draft) | — |

### 6.5 Registry draft semantics (M2 — local)

Production learner writes **host memory + skills** (Hermes skill store). Adapter additionally:

1. Creates local `AgentRegistry` draft from aggregated `actions` ( **recommended M2** ).
2. Calls `registry.activate()` only when not `dry_run` and classification ≠ `no_op`.

M5 (remote registry API) can replace step 1 later.

---

## 7. Client & adapter plan

### 7.1 New modules (repo)

| Module | Responsibility |
|--------|----------------|
| `services/adapters/self_learning_client.py` | HTTP: `evolve_sessions`, `evolve_recent`, `get_job_status`, `list_sessions`, `set_optout`, `health` |
| `services/adapters/learn_adapter.py` | `learn()` → pick endpoint + poll → `self_learning_mapping.normalize` |
| `services/adapters/self_learning_mapping.py` | `completed` job + `results[]` → loop-shaped `learn()` response + local registry draft |
| `docs/integration/mapping.md` | New § Self-learning (§6.2 rules) |
| `docs/integration/api-snapshots/self-learning-openapi.json` | Export from production learner |

### 7.2 `learn()` behavior by mode

| `LOOP_LEARN_MODE` | Backend | Behavior |
|-------------------|---------|----------|
| `sync` (default mock) | In-process / `POST /learning/events` | Today’s mock classifier |
| `evolve` | Production learner §4.1–4.3 | Forked agent review |
| `evolve_recent` | `POST /learning/evolve/recent` | Auto-learn style; used when no `session_ids` on E-path |

**E-path adapter flow (`LOOP_LEARN_MODE=evolve`):**

```text
learn(event, source="loop-e-path", capability)
  → resolve session_ids (env LOOP_LEARN_SESSION_IDS, or GET /learn/sessions, or fallback evolve_recent)
  → POST /learning/evolve {
       session_ids, evolve_memory, evolve_skills,
       wait: true,   # loop blocks
       dry_run: false
     }
  OR (async path) wait: false → poll GET /learning/status/{job_id}
  → aggregate results[].actions
  → mapping → local registry.create_version + { draft_version_id, routing }
  → return normalized dict (source preserved as loop-e-path on event log row)
```

**Cron / coach Auto-learn:**

```text
POST /learning/evolve/recent { hours: 24, max_sessions: 10, wait: false }
→ poll GET /learning/status/{job_id}
→ optional: no local registry activate (coach may only update host skills)
```

### 7.3 Environment variables (proposed)

Add to `scenarios/demo.env.example` when implementing:

| Variable | Default (mock) | Live |
|----------|----------------|------|
| `SELF_LEARNING_BASE_URL` | unset | Learner service URL |
| `MOCK_SELF_LEARNING_URL` | unset | Alias for mock HTTP stack |
| `LOOP_LEARN_MODE` | `sync` | `evolve` \| `evolve_recent` |
| `LOOP_LEARN_SESSION_IDS` | unset | Comma-separated ids for targeted E-path |
| `LOOP_LEARN_HOURS` | `24` | Window for `/evolve/recent` |
| `LOOP_LEARN_MAX_SESSIONS` | `10` | Fan-out cap |
| `LOOP_LEARN_EVOLVE_MEMORY` | `true` | Pass-through |
| `LOOP_LEARN_EVOLVE_SKILLS` | `true` | Pass-through |
| `LOOP_LEARN_DRY_RUN` | `false` | Pass-through |
| `LOOP_LEARN_WAIT` | auto | Override service auto sync/async |
| `LOOP_LEARN_TIMEOUT_S` | `30` | Poll budget when `wait=false` |
| `LOOP_LEARN_POLL_INTERVAL_S` | `1` | Poll interval |
| `SELF_LEARNING_API_KEY` | optional | Bearer for staging |

Wire in `modes/self-coaching/loop_env.py` alongside existing service mode knobs.

---

## 8. Mock implementation plan

Extend `mock-services/mock_self_learning.py` to **mirror production routes** (deterministic shims):

| Endpoint | Mock behavior |
|----------|---------------|
| `POST /learning/evolve` | Map `session_ids` → synthetic `results[]` from `classify_event` + `create_version` |
| `POST /learning/evolve/recent` | Filter fake session list by `hours`; respect `max_sessions` skip reasons |
| `GET /learning/status/{job_id}` | In-memory job table; instant `completed` for tests |
| `GET /learn/sessions` | Return fixture session list |
| `POST /learning/optout` | In-memory opt-out set |
| `GET /learning/health` | Always 200 in mock; optional 503 test hook |
| `POST /learning/events` | **Unchanged** — R5 mock-module path |

**CI:** `LOOP_SERVICE_MODE=mock-module` keeps in-process `record_event` (no HTTP). Production-shaped routes tested via `mock-http` or unit tests with `MOCK_SELF_LEARNING_URL`.

**Determinism:** Mock worker completes in &lt;100ms; same classification rules as today for golden stability.

---

## 9. Integration with host platforms

### 9.1 Hermes Agent (background review fork)

| Concern | Integration |
|---------|-------------|
| Auto-learn cron | `POST /learning/evolve/recent` `{ hours: 24, wait: false }` |
| Post-session hook | `POST /learning/evolve` `{ session_ids: [sid], wait: true }` |
| User opt-out | `POST /learning/optout` / `hermes session learn-optout` |
| Skills / memory | Learner writes to host stores; adapter handles registry draft for loop/coach only |

### 9.2 Self-coaching loop demo

| Concern | Integration |
|---------|-------------|
| Default CI | `LOOP_LEARN_MODE=sync` — no SessionDB required |
| Live E-path | `learn_adapter` + session id bridge (§5) |
| Σ → event text | `learn_from_sigma` unchanged; adapter may log `hint` in `learning_events.jsonl` |
| Generation / buffer flush | Unchanged after `registry.activate` |

### 9.3 Coach mode

| Concern | Integration |
|---------|-------------|
| Auto-learn | Scheduler → `POST /learning/evolve/recent` per supervised agent |
| Targeted | After eval drop → resolve failing session ids → `POST /learning/evolve` |
| Preflight | `GET /learn/sessions?hours=24` before fan-out |

---

## 10. Migration phases (updates M2)

Replaces the narrow “wire `MOCK_SELF_LEARNING_URL`” bullet in [mock-to-real-migration.md](mock-to-real-migration.md) §M2 with:

| Step | Deliverable | Exit |
|------|-------------|------|
| **M2.0** | This spec approved; OpenAPI draft in `openapi.yaml` + snapshot placeholder | Review sign-off |
| **M2.1** | Mock production routes (§8) + fixtures | Unit tests green |
| **M2.2** | `self_learning_client.py` + `learn_adapter.py` + mapping doc | Replay test from fixture |
| **M2.3** | `loop_env.py` env wiring; `LOOP_LEARN_MODE` | E-path test with mock HTTP review |
| **M2.4** | Staging smoke: real review agent + M1 holdout | `full_loop_live` E-path rows pass |
| **M2.5** | R5 mock-module regression | Golden unchanged |

**Dependency:** M1 AgentEvals PASS (holdout) — no change.  
**Parallel:** M3 self-play may proceed; E-path only needs learn + eval for staging smoke.

**Task lists:** §11 (detailed checklists). Track status in [progress.md](progress.md) § M2 self-learning.

---

## 11. Implementation task lists

Use task IDs in PR titles / commit messages (e.g. `M2.1-T03: mock POST /learning/evolve`). Mark `[x]` when done.

### 11.0 Master tracker

| Phase | Summary | Status | Depends on |
|-------|---------|--------|------------|
| **M2.0** | Spec + contract freeze | **in progress** (DRAFT spec + §11 tasks) | — |
| **M2.1** | Mock services (production routes) | not started | M2.0 |
| **M2.2** | HTTP client + learn adapter + mapping | not started | M2.1 |
| **M2.3** | Loop env + facade wiring | not started | M2.2 |
| **M2.4** | Staging smoke + live E-path | not started | M2.3, M1 |
| **M2.5** | R5 mock-module regression | not started | M2.3 |
| **SP** | Skill pack & SKILL.md alignment (L1–L8) | not started | L8 → L1 |

**Parallel track:** §11.8 (skill pack) can land before or alongside M2; unblocks Hermes operators using Bash hooks.

---

### 11.1 M2.0 — Spec & contract freeze

| ID | Task | File(s) | Done |
|----|------|---------|------|
| M2.0-T01 | Resolve open questions §14 (Q1, Q7 minimum) | this doc §14 | [ ] |
| M2.0-T02 | Add review routes to Coaching OpenAPI (draft schemas) | `mock-services/contracts/openapi.yaml` | [ ] |
| M2.0-T03 | Sync `mock_service_contract.json` from OpenAPI | `mock-services/contracts/mock_service_contract.json` | [ ] |
| M2.0-T04 | Placeholder API snapshot for learner service | `docs/integration/api-snapshots/self-learning-openapi.json` | [ ] |
| M2.0-T05 | Link spec from integration plan | `docs/project/integration-plan.md` | [ ] |

**Exit:** Spec sign-off; OpenAPI draft merged; no runtime behavior change.

---

### 11.2 M2.1 — Mock services (production-shaped HTTP)

| ID | Task | File(s) | Done |
|----|------|---------|------|
| M2.1-T01 | In-memory `SessionDB` shim (sessions, opt-out, last_active) | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T02 | In-memory job table (`job_id`, status, results, TTL) | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T03 | `POST /learning/evolve` — sync (`wait=true`) + async (`wait=false`) | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T04 | `POST /learning/evolve/recent` — window, `max_sessions`, skip reasons | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T05 | `GET /learning/status/{job_id}` — running / completed | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T06 | `GET /learn/sessions` — query `hours`, `limit`, `include_optout` | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T07 | `POST /learning/optout` | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T08 | `GET /learning/health` (+ optional 503 test hook) | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T09 | Map review results → `actions` from `classify_event` / `record_event` logic | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T10 | Normalize `poll_url` to `/learning/status/{job_id}` in mock responses | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T11 | Bearer auth on new routes (match existing mock pattern) | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T12 | **Keep** `POST /learning/events` + in-process `record_event` unchanged | `mock-services/mock_self_learning.py` | [ ] |
| M2.1-T13 | Fixture: sync completed evolve | `tests/fixtures/self_learning/evolve_sync_completed.json` | [ ] |
| M2.1-T14 | Fixture: async queued + status completed | `tests/fixtures/self_learning/evolve_async_queued.json`, `status_completed_skill_patch.json` | [ ] |
| M2.1-T15 | Fixture: no-op (all skipped) | `tests/fixtures/self_learning/status_completed_no_op.json` | [ ] |
| M2.1-T16 | Fixture: sessions list | `tests/fixtures/self_learning/sessions_list.json` | [ ] |
| M2.1-T17 | Unit tests: review lifecycle, errors (400/404/413), opt-out | `tests/test_self_learning_review_mock.py` | [ ] |
| M2.1-T18 | Extend existing `test_mock_self_learning.py` — events path still green | `tests/test_mock_self_learning.py` | [ ] |
| M2.1-T19 | Update mock README + smoke script for review routes | `mock-services/README.md`, `scripts/mock-self-learning-smoke.sh` | [ ] |
| M2.1-T20 | Register new paths in `mock_self_coaching.py` facade (if split-stack lists routes) | `mock-services/mock_self_coaching.py` | [ ] |

**Exit:** `pytest tests/test_self_learning_review_mock.py tests/test_mock_self_learning.py` green; `POST /learning/events` unchanged.

---

### 11.3 M2.2 — Adapters (remote learning service client)

| ID | Task | File(s) | Done |
|----|------|---------|------|
| M2.2-T01 | Low-level HTTP client: `evolve_sessions`, `evolve_recent` | `services/adapters/self_learning_client.py` | [ ] |
| M2.2-T02 | Client: `get_job_status`, `poll_until_complete` | `services/adapters/self_learning_client.py` | [ ] |
| M2.2-T03 | Client: `list_sessions`, `set_optout`, `health` | `services/adapters/self_learning_client.py` | [ ] |
| M2.2-T04 | Path normalization (`poll_url` → `/learning/status/…`) | `services/adapters/self_learning_client.py` | [ ] |
| M2.2-T05 | Mapping: aggregate `results[].actions` → classification | `services/adapters/self_learning_mapping.py` | [ ] |
| M2.2-T06 | Mapping: create local `AgentRegistry` draft + `draft_version_id` | `services/adapters/self_learning_mapping.py` | [ ] |
| M2.2-T07 | Mapping: `no_op` when all skipped / zero actions | `services/adapters/self_learning_mapping.py` | [ ] |
| M2.2-T08 | `learn_adapter.learn()` — `LOOP_LEARN_MODE=sync` → events or in-process | `services/adapters/learn_adapter.py` | [ ] |
| M2.2-T09 | `learn_adapter.learn()` — `evolve` → POST evolve + poll + map | `services/adapters/learn_adapter.py` | [ ] |
| M2.2-T10 | `learn_adapter.learn()` — `evolve_recent` fallback when no session ids | `services/adapters/learn_adapter.py` | [ ] |
| M2.2-T11 | Preserve `source="loop-e-path"` on normalized response + event log | `services/adapters/learn_adapter.py` | [ ] |
| M2.2-T12 | Document field mapping | `docs/integration/mapping.md` (new § Self-learning) | [ ] |
| M2.2-T13 | Replay tests from fixtures (no network) | `tests/test_learn_adapter.py` | [ ] |
| M2.2-T14 | Client error mapping (401, 404, 413, 500) | `tests/test_self_learning_client.py` | [ ] |

**Exit:** Adapter tests pass with fixture replay; no loop wiring yet.

---

### 11.4 M2.3 — Loop env, facade, and composite client

| ID | Task | File(s) | Done |
|----|------|---------|------|
| M2.3-T01 | Add `LOOP_LEARN_*` env vars to template | `scenarios/demo.env.example` | [ ] |
| M2.3-T02 | Load learn env in `load_demo_env()` / `apply_service_mode()` | `modes/self-coaching/loop_env.py` | [ ] |
| M2.3-T03 | Factory: pick sync vs review client from env | `modes/self-coaching/loop_env.py` | [ ] |
| M2.3-T04 | Wire `mock_self_coaching.learn()` → review HTTP when mode + URL set | `mock-services/mock_self_coaching.py` | [ ] |
| M2.3-T05 | Optional: `composite_client.learn()` delegate to `learn_adapter` | `services/adapters/composite_client.py` | [ ] |
| M2.3-T06 | E-path integration test with `MOCK_SELF_LEARNING_URL` + `LOOP_LEARN_MODE=evolve` | `tests/test_loop_e_path.py` | [ ] |
| M2.3-T07 | HTTP smoke: review recent against mock server | `scripts/mock-self-learning-smoke.sh` | [ ] |
| M2.3-T08 | Document live learn profile (example env file) | `scenarios/demo.self-learning.env.example` | [ ] |

**Exit:** E-path passes against mock HTTP review stack; default `mock-module` still uses `record_event`.

---

### 11.5 M2.4 — Staging smoke & live E-path

| ID | Task | File(s) | Done |
|----|------|---------|------|
| M2.4-T01 | Opt-in smoke script: health → sessions → review → poll | `scripts/self_learning_live_smoke.py` | [ ] |
| M2.4-T02 | Capture live response fixtures (sanitized) | `tests/fixtures/self_learning/` | [ ] |
| M2.4-T03 | Staging env example | `scenarios/demo.self-learning.env.example` | [ ] |
| M2.4-T04 | E-path + M1 holdout on staging (session id bridge per §14 Q1) | manual / `full_loop_live.json` | [ ] |
| M2.4-T05 | Opt-in CI job (secrets) for integration branch | `.github/workflows/ci.yml` | [ ] |
| M2.4-T06 | Runbook subsection: Auto-learn cron + targeted review | `docs/guides/runbook.md` | [ ] |

**Exit:** Live learner smoke PASS; E-path rows in live completeness scenario (or documented gap if Q1 unresolved).

---

### 11.6 M2.5 — Regression & docs

| ID | Task | File(s) | Done |
|----|------|---------|------|
| M2.5-T01 | R5: `LOOP_SERVICE_MODE=mock-module` demo script exit 0 | `scripts/mock_self_coaching_demo.py` | [ ] |
| M2.5-T02 | R5: golden audit unchanged | `tests/fixtures/golden/completeness_report_full_loop.json` | [ ] |
| M2.5-T03 | Update component status in progress tracker | `docs/project/progress.md` | [ ] |
| M2.5-T04 | Mark M2 PASS in migration doc | `docs/project/mock-to-real-migration.md` | [ ] |
| M2.5-T05 | Set spec status APPROVED / IMPLEMENTED | this doc header | [ ] |

**Exit:** R5 green on default mock settings; M2 marked complete.

---

### 11.7 Cross-cutting (coach mode & orchestrator)

Not blocking loop E-path; schedule after M2.3 or in parallel.

| ID | Task | File(s) | Done |
|----|------|---------|------|
| M2.X-T01 | Orchestrator `run` / coach: call `evolve_recent` on schedule | `services/orchestrator/runner.py`, `modes/coach/` | [ ] |
| M2.X-T02 | Coach demo: optional review step after drop | `scripts/mock-coach-demo.sh` | [ ] |
| M2.X-T03 | `production_readiness.py` contract checks for new endpoints | `mock-services/production_readiness.py` | [ ] |

---

### 11.8 Skill pack & SKILL.md alignment (L-series)

Review findings for the **Hermes-installable skill pack** and `self-learning/SKILL.md`. These are separate from M2 HTTP adapters but block a coherent operator story for self-learning.

**Root cause (L1):** `self-learning/SKILL.md` advertises `$SKILL_ROOT/scripts/{init-experience,hook-inject-*}.sh`, but **`modes/self-coaching/scripts/` does not exist** in the pack. Working references live at repo [`scripts/`](../../scripts/) and duplicates under [`modes/self-coaching/self-learning/scripts/`](../../modes/self-coaching/self-learning/scripts/) — install path must be unified.

#### Severity summary

| ID | Sev | Title | Blocks |
|----|-----|-------|--------|
| L1 | HIGH | Missing `scripts/` at umbrella skill install path | L8, operator hooks |
| L2 | HIGH | Umbrella vs child SKILL.md describe conflicting entry surfaces | Operator confusion |
| L3 | MEDIUM | Decision table conflates user vs agent memory | Wrong Hermes `target=` routing |
| L4 | LOW | No validator for ERROR/LEARNINGS templates | Optional quality gate |
| L6 | LOW | `EXPERIMENT_LOG.md` has no schema in Step 0 | Inconsistent with siblings |
| L7 | LOW | "Stale within a week" duplicates Hermes core guidance | Doc drift |
| L8 | LOW | Verification checklist references missing `init-experience.sh` | Downstream of L1 |

#### L1 — Ship experience hook scripts (HIGH)

| ID | Task | File(s) | Done |
|----|------|---------|------|
| L1-T01 | Add umbrella `scripts/` to skill pack (canonical copy from repo `scripts/`) | `modes/self-coaching/scripts/init-experience.sh`, `hook-inject-errors.sh`, `hook-inject-learnings.sh` | [ ] |
| L1-T02 | Ensure Hermes install copies `scripts/` asset kind to `$SKILL_ROOT/scripts/` | `scripts/lib/hermes-skill-pack.sh`, `scripts/install-skill-pack.sh` | [ ] |
| L1-T03 | Deduplicate: single source of truth (repo `scripts/` → pack); remove or symlink stale `self-learning/scripts/` copies | `modes/self-coaching/self-learning/scripts/` | [ ] |
| L1-T04 | `init-experience.sh`: idempotent init of `experience/{ERROR,LEARNINGS,EXPERIMENT_LOG}.md`, `logs/`, `worktrees/` | `modes/self-coaching/scripts/init-experience.sh` | [ ] |
| L1-T05 | `hook-inject-errors.sh`: bounded tail, `ERROR_TAIL_LINES` (default 120), begin/end markers; missing log → exit 0; bad env → exit 2 | `modes/self-coaching/scripts/hook-inject-errors.sh` | [ ] |
| L1-T06 | `hook-inject-learnings.sh`: same contract for `LEARNINGS.md` / `LEARNINGS_TAIL_LINES` | `modes/self-coaching/scripts/hook-inject-learnings.sh` | [ ] |
| L1-T07 | Smoke test script or CI step: fresh init → exit 0; re-run → exit 0, content unchanged | `tests/test_skill_pack_scripts.sh` or extend `doctor.sh` | [ ] |
| L1-T08 | Smoke: hooks — missing log silent 0; invalid tail lines → exit 2 + message | same | [ ] |

**Reference behavior (verified):**

| Script | Behavior | Smoke |
|--------|----------|-------|
| `init-experience.sh` | Creates experience templates; idempotent | Fresh + re-run → exit 0, content preserved |
| `hook-inject-errors.sh` | Bounded `ERROR.md` tail; env validation | Missing log → 0; bad `ERROR_TAIL_LINES` → 2 |
| `hook-inject-learnings.sh` | Bounded `LEARNINGS.md` tail | Same profile as errors hook |

#### L2 — Canonical executable surface (HIGH)

| ID | Task | File(s) | Done |
|----|------|---------|------|
| L2-T01 | **Decision:** Bash hooks + `init-experience.sh` = canonical entry for self-learning skill | this doc §11.8 | [ ] |
| L2-T02 | Umbrella `SKILL.md`: demote `python -m self_coaching.demo` to "future / repo dev" or move to Mode 2 appendix with `pip install -e .` prerequisite | `modes/self-coaching/SKILL.md` | [ ] |
| L2-T03 | Child `self-learning/SKILL.md`: cross-link umbrella install paths + Bash workflow as primary | `modes/self-coaching/self-learning/SKILL.md` | [ ] |
| L2-T04 | Fix `$SKILL_ROOT` examples to resolve to installed pack root (where `scripts/` lives post-L1) | both SKILL.md files | [ ] |
| L2-T05 | Align `references/hooks-setup.md` paths with pack `scripts/` | `references/hooks-setup.md` | [ ] |

#### L3 — User memory vs agent memory vocabulary (MEDIUM)

| ID | Task | File(s) | Done |
|----|------|---------|------|
| L3-T01 | Rename decision table "Memory" rows → **User memory** (`target='user'`) vs **Agent memory** (`target='memory'`) per Hermes core | `modes/self-coaching/self-learning/SKILL.md` § Decision Table | [ ] |
| L3-T02 | Same split in umbrella `SKILL.md` decision table + Memory Guidelines | `modes/self-coaching/SKILL.md` | [ ] |
| L3-T03 | Add one-line glossary: user memory = preferences for user; agent memory = durable facts for agent across sessions | both SKILL.md | [ ] |

#### L4 — Experience log validation (LOW)

| ID | Task | File(s) | Done |
|----|------|---------|------|
| L4-T01 | **Decision:** ship `validate-experience.sh` **or** drop required-field schema from templates | this doc §11.8 | [ ] |
| L4-T02 | If ship: validator for ERROR.md / LEARNINGS.md required fields | `modes/self-coaching/scripts/validate-experience.sh` | [ ] |
| L4-T03 | Reference validator in verification checklist (optional step) | `self-learning/SKILL.md` | [ ] |

#### L6 — EXPERIMENT_LOG schema (LOW)

| ID | Task | File(s) | Done |
|----|------|---------|------|
| L6-T01 | Add `EXPERIMENT_LOG.md` block template to Step 1 (match ERROR/LEARNINGS style) | `self-learning/SKILL.md` | [ ] |
| L6-T02 | Ensure `init-experience.sh` seeds template from `experience/EXPERIMENT_LOG.md` stub | `experience/EXPERIMENT_LOG.md`, init script | [ ] |

#### L7 — Stale-content rule (LOW)

| ID | Task | File(s) | Done |
|----|------|---------|------|
| L7-T01 | Replace verbatim "stale within a week" copy with named reference to Hermes core memory guidance | `self-learning/SKILL.md`, umbrella `SKILL.md` | [ ] |

#### L8 — Verification checklist (LOW, blocked by L1)

| ID | Task | File(s) | Done |
|----|------|---------|------|
| L8-T01 | Re-verify checklist item 1 after L1 ships (`init-experience.sh` path works from `$SKILL_ROOT`) | `self-learning/SKILL.md` § Verification Checklist | [ ] |

**Exit (SP track):** `bash "$SKILL_ROOT/scripts/init-experience.sh" .` works after `--hermes` install; smoke tests green; umbrella + child SKILL.md agree on Bash-first entry.

---

## 12. Testing strategy

| Test | Purpose |
|------|---------|
| `tests/test_self_learning_review_mock.py` | Mock review job lifecycle |
| `tests/test_learn_adapter.py` | Fixture replay → `draft_version_id` mapping |
| `tests/test_loop_e_path.py` | Still asserts `source=="loop-e-path"` |
| `tests/test_mock_self_coaching_demo.sh` | R5 — mock-module unchanged |
| `scripts/self_learning_live_smoke.py` (new) | Opt-in staging POST + poll |

**Fixtures (to add):**

- `tests/fixtures/self_learning/evolve_sync_completed.json`
- `tests/fixtures/self_learning/evolve_async_queued.json`
- `tests/fixtures/self_learning/status_completed_skill_patch.json`
- `tests/fixtures/self_learning/status_completed_no_op.json`
- `tests/fixtures/self_learning/sessions_list.json`

---

## 13. Non-goals (M2)

- Replacing local `mock_agent_registry` with production agent API (M5).
- Embedding the learning agent’s LLM prompts in this repo (live service owns worker).
- Real-time streaming of review reasoning into the loop (logs on service side only).
- Automatic Hermes skill pack publish after patch write.
- Removing `POST /learning/events` (keep for thin/manual path).

---

## 14. Open questions (edit in review)

| # | Question | Options | Decision |
|---|----------|---------|----------|
| Q1 | Loop Σ → `session_id` bridge | Task stream carries `session_id`; env override; always `evolve_recent` | _TBD_ |
| Q2 | Who creates registry draft | Adapter + local registry (§6.5) vs production version API (M5) | _Recommend adapter + local for M2_ |
| Q3 | Default `LOOP_LEARN_MODE` for live | `evolve` vs `evolve_recent` for E-path | _TBD_ |
| Q4 | E-path `wait` override | Force `wait: true` vs respect service auto (≤5 async) | _Recommend force `wait: true` for loop_ |
| Q5 | All skipped → E-path behavior | Treat as `no_op` (no activate) vs fail loop | _Recommend no_op_ |
| Q6 | OpenAPI ownership | Separate `self-learning-openapi.json` vs extend Coaching API | _Recommend separate snapshot from learner service_ |
| Q7 | Path prefix normalization | `poll_url` uses `/learn/status/`; spec uses `/learning/status/`; sessions at `/learn/sessions` | _Confirm canonical paths with learner team_ |
| Q8 | `skill_bundle_version` from host | Adapter-generated hash vs query host skill store for version id | _TBD_ |

---

## 15. Related commands (future)

| Today (mock sync) | Staging (review agent) |
|-------------------|------------------------|
| `python -m mock_self_learning record --event "..."` | `curl -X POST …/learning/evolve/recent -d '{"hours":24,"wait":false}'` |
| `MOCK_SELF_LEARNING_URL=…` + loop demo | `LOOP_LEARN_MODE=evolve SELF_LEARNING_BASE_URL=…` |
| `bash scripts/mock-self-learning-smoke.sh` | `python scripts/self_learning_live_smoke.py` |
| — | `curl …/learn/sessions?hours=24` (discover) |
| — | `curl …/learning/status/{job_id}` (poll) |

---

## 16. Document history

| Date | Change |
|------|--------|
| 2026-06-12 | Initial DRAFT from loop migration + Dream-style review agent discussion |
| 2026-06-12 | Replaced §4 with production learner API (`/learning/evolve`, `/evolve/recent`, `/learning/status`, optout, health); updated adapter mapping §6 |
| 2026-06-12 | Added §11 implementation task lists (M2.0–M2.5); synced paths to `/learning/evolve` |
| 2026-06-12 | Canonical learner paths: `/learning/evolve`, `/learning/evolve/recent` (not `/learning/review`) |
| 2026-06-12 | Added §11.8 skill pack alignment (L1–L8): scripts path, SKILL.md surfaces, memory vocabulary |

---

*Edit this file freely. Implement **§11** task lists in order M2.0 → M2.5; check `[x]` as tasks land.*
