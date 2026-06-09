# Self-coaching demo pipeline plan

**Status:** P0–P3 implemented (2026-06-09); P4–P5 not started  
**Goal:** Deploy a **demo-ready, deterministic pipeline** that shows how **self-coaching mode** runs continuously on top of the **mock platform**, and doubles as a **mock-completeness harness** beyond one-shot `run-all` / `production_readiness.py`.

**Implementation note:** Runtime code lives under `modes/self-coaching/` (not `mock-services/` as in §19) because the self-coaching mode package uses hyphenated directory names; imports use `sys.path` shims. Entry point: `loop_driver.run_tasks()`.

**Related:** [mock-platform-design.md](mock-platform-design.md) (Phases 0–4 done), [pipelines.md](../design/pipelines.md) (batch evolution engine), [roadmap.md](roadmap.md) (M0–M5), [progress.md](progress.md).

---

## 1. Problem statement

### What exists today

| Capability | Location | Limitation |
|------------|----------|------------|
| Mock platform (split services) | `mock-services/mock_*.py`, `scripts/mock-stack-up.sh` | Proves **endpoints** and **phase smokes** |
| Monolithic facade | `mock_self_coaching.py run-all` | Single batch; no task stream |
| Batch orchestrator | `services/orchestrator/` `record-eval` → `check-drop` → `run` | **Drop-triggered** improvement; coach-oriented |
| Production-readiness harness | `mock-services/production_readiness.py` | One pass; artifact contract + split hygiene |
| Coach demo | `scripts/mock-coach-demo.sh` | Two agents; not self-coaching continuous loop |

Nothing in-repo **simulates a live task stream** `{τᵢ}`, maintains a **generation-scoped tuning buffer** `B`, or runs the **dual evolution paths** (fast skill/memory vs slow model) from the logical design discussed with the team.

### What we need

1. **Demo:** A runnable script (and optional HTTP driver) that an operator or presenter can run in ~2–5 minutes and **see** agent version `M` improve over simulated tasks — without VPN, real AgentEvals, AERL, or a live LLM.
2. **Completeness audit:** A structured report that says, per pipeline step, whether mocks were **invoked** (artifact evidence) and whether **semantic** outcomes match scenario intent (e.g. promotion score did not regress) — exposing gaps before staging against real systems.
3. **Bridge to production:** Reuse existing `SelfCoachingClient`, registry, orchestrator gates — do not fork a parallel integration API.

---

## 2. Target agent model

Let agent state at generation `g` be:

```text
M_g = (θ_g, mem_g, S_g)
```

| Symbol | Meaning | Mock / registry field |
|--------|---------|------------------------|
| `θ_g` | Base model weights / checkpoint id | `components.model_id` |
| `mem_g` | Durable memory facts | `components.memory_ref` + `.self-coaching/memory/facts.jsonl` |
| `S_g` | Skill bundle version | `components.skill_bundle_version` + `.self-coaching/skills/patches/` |
| `g` | Evolution generation (monotonic) | `meta.generation` in coaching root + registry parent chain |

**Ensure (invariant):** After any skill/memory upgrade (`g ← g+1`), no sample in tuning buffer `B` with `sample.generation ≤ g` may be used for training. This is **support–query separation** across evolution types.

---

## 3. Formal pipeline (canonical spec)

Modules: **E** (self-learning), **P** (self-play), **T** (self-tuning / AERL), **R** (eval), **F** (free-time detector). Task stream `{τᵢ}`.

### 3.1 Initialization

```text
1.  Initialize coaching root; bootstrap registry agent M_0.
2.  g ← 0
3.  Support set Σ ← ∅
4.  Tuning buffer B ← ∅
5.  Load or generate skill bootstrap S_0 (existing init paths)
```

### 3.2 Per-task loop (always on while stream active)

```text
for each task τᵢ in stream:
  S_τ ← Retrieve(S_g, τᵢ)              // skill subset for task
  ξᵢ ← AgentServe(τᵢ, S_τ, M_g)          // trajectory
  rᵢ ← R_online(ξᵢ, τᵢ)                  // lightweight per-trajectory score
  stamp (τᵢ, ξᵢ, rᵢ, g, version_id(M_g))

  if rᵢ indicates failure:
    Σ ← Σ ∪ {(τᵢ, ξᵢ, rᵢ)}
  else:
    B ← B ∪ {(τᵢ, ξᵢ, rᵢ, g)}
```

**Design decisions (resolve ambiguities from draft pseudocode):**

| Topic | Decision | Rationale |
|-------|----------|-----------|
| `R_online` vs suite eval | **Two-tier eval:** `R_online` = deterministic rubric on ξᵢ (fast); `R_suite` = AgentEvals/mock eval at generation boundaries and before θ hot-swap | Matches AgentEvals async model; still scores every task in demo |
| Failure threshold | `rᵢ < τ_fail` (default `0.75`; see §10) | Per-trajectory online rubric; independent of suite `min_score` |
| Retrieve | **Phase 1 stub:** full `S_g`; **Phase 2:** keyword/capability match from task tags | Unblocks demo without new retrieval service |

#### 3.2.1 `R_online` scoring function

`R_online` is **not** mock AgentEvals id-substring scoring (`bad` / `regress` in `version_id` applies only to `R_suite`). It is a **fixture-grounded rubric** implemented by `trajectory_scorer.score_trajectory(ξᵢ, τᵢ)`:

```text
tools_ok  ← every token in τᵢ.expected_tool_calls appears (case-insensitive) in some ξᵢ.tool_trace_summary entry
answer_ok ← every check in τᵢ.answer_checks passes on ξᵢ.final_answer (last assistant message; `contains` substring match)
if tools_ok and answer_ok: return 1.0
if tools_ok:               return 0.5    // tools ran but answer/evidence incomplete
return 0.0
```

Each task fixture row in `tool_use_v1.jsonl` carries `expected_tool_calls` and `answer_checks` so scores are **derivable from inputs**, not asserted in tests. `TrajectorySimulator` produces ξᵢ from `(τᵢ, agent_profile)`; P0 unit tests use golden `(τᵢ, ξᵢ) → score` triples (e.g. full success `1.0`, tools-only `0.5`, missing tools `0.0`) and compare against this function — not “whatever the scorer returns.”

### 3.3 Self-learning evolution (E-path)

**Trigger:** `|Σ| ≥ σ_min` (default `1`) — failures accumulated.

```text
if |Σ| ≥ σ_min:
  if 0 < |Σ| ≤ σ_play:                    // sparse real failures
    P.generate_similar(Σ) → augment Σ     // see API binding below (C06)
  else:
    skip extra self-play                  // enough real failures

  Δ ← E.learn(Σ)                          // memory and/or skill patch
  M_{g+1} ← apply( M_g, Δ )               // registry draft; S_{g+1} ← S_g ∪ ΔS, etc.
  B ← { x ∈ B : x.g > g }                 // flush stale successes
  Σ ← ∅
  g ← g + 1
  optionally: R_suite on holdout → record metrics (no θ change)
```

**Clarification:** Original line 13 (“not empty but not greater than threshold”) is interpreted as: **self-play augments when failure count is positive but ≤ `σ_play`** (default `3`). Above `σ_play`, real failures are sufficient.

**API binding (C06 — sparse, failure-conditioned):** not `SelfCoachingClient.self_play()` (that wraps batch generate only). The loop calls **`MockSelfPlayEngine.generate_suite()`** in-process, or **`POST /self-play/generate-suite`** on `:8767` when `MOCK_SELF_PLAY_URL` is set:

| Param | Source |
|-------|--------|
| `coaching_root` | loop `{root}` |
| `user_query` | `Σ[0].event_text` (or task `user_request`) |
| `trajectory` | ξᵢ loaded from `Σ[0].trajectory_ref` |
| `eval_score` | `Σ[0].score` (online rubric `rᵢ`) |
| `mode` | `"adversarial"` |
| `n_variants` | `min(|Σ|, σ_play)` |
| `agent_id` / `version_id` | active registry version at generation `g` |

Response `suite_id` is completeness evidence for C06; generated cases augment Σ before `E.learn`.

### 3.4 Self-tuning evolution (T-path)

**Trigger:** `F.idle()` **and** `|B| ≥ β` (batch size, default `4` in demo; `100` in production orchestrator).

```text
if F.idle():
  if |B| < β:
    P.generate_batch(n = β - |B|) → append to B with current g   // see API binding below (C07)
  if |B| ≥ β:
    θ' ← T.train(B, M_g)                  // mock AERL SFT/GRPO
    if R_suite(θ', holdout) passes gates:
      hot_swap(θ')                        // registry activate draft model_id
    B ← { x ∈ B : x.used_for_train }      // or clear consumed rows; tag in metadata
```

**Safety:** Unlike the draft pseudocode, **no hot-swap without holdout gate** — reuse `check_promotion()` from `services/orchestrator/drop_detector.py`.

**Clarification:** Original line 20 (“`|B| < batch` → self-play”) is **fill buffer when under batch** before training. Training runs only when `|B| ≥ β` after fill.

**API binding (C07 — batch buffer top-up):** **`MockSelfPlayEngine.generate_batch()`** in-process, or **`POST /self-play/generate`** on `:8767` (Coaching API shape; also what `SelfCoachingClient.self_play()` / `mock_self_coaching.self_play()` delegate to):

| Param | Source |
|-------|--------|
| `coaching_root` | loop `{root}` |
| `capability` | task-stream default (e.g. `"tool_use"`) |
| `n` | `β - |B|` |

No failure `trajectory` or `user_query` from Σ — engine seeds from the latest learning event (auto-seeds one if empty). Response `case_ids` + `suite_id`; loop converts curated trajectories into tuning-buffer rows stamped with current `g`. Distinct endpoint from §3.3 — **not** a `mode` flag on `generate-suite`.

### 3.5 Mutex and ordering

| Rule | Behavior |
|------|----------|
| E vs T same tick | **E first** if `|Σ| ≥ σ_min`; then evaluate T-path on remaining idle budget |
| In-flight train on E bump | Cancel or tag runs with `generation_at_start`; reject if `generation_at_start < g` |
| Task loop during train | Demo default: **pause stream** during T.train (simpler); Phase 2: concurrent with generation tags |

### 3.6 Concurrency in production

Demo §3.5 pauses the task stream for the duration of async `T.train` — acceptable for a bounded mock run, not for production where AERL jobs may run for hours. When an E-path bump advances `g` while a T-path train is in flight, pick one (or combine):

| Option | Production behavior |
|--------|---------------------|
| **Cancel stale runs** | On `g++`, cancel in-flight AERL runs whose `generation_at_start < g`; discard partial artifacts. |
| **Reject promotion** | Allow the run to finish, but reject hot-swap / `activate` if `generation_at_start < g` at gate time (I2). |
| **Serializable lock on `g`** | Hold a generation-scoped lock for the E-path transaction; T-path acquires the same lock before sampling `B` and starting train. |

Phase 2 enforces I2 only by flushing `B` (`generation ≤ g`); production must also cover async trains started before the flush.

---

## 4. Architecture

### 4.1 Topology

```text
+--------------------------------------------------------------------------+
|  Demo driver (new)                                                        |
|  mock-services/self_coaching_loop.py  OR  scripts/mock-self-coaching-demo.sh |
+-------------------------------+------------------------------------------+
                                |
        +-----------------------+-----------------------+
        |                       |                       |
+---------------+      +-----------------+     +------------------+
| TaskStream    |      | TrajectorySim   |     | GenerationState  |
| (fixtures)    |      | (mock agent)    |     | g, version_id    |
+-------+-------+      +--------+--------+     +---------+--------+
        |                       |                        |
        +-----------------------+------------------------+
                                |
                    +-----------v-----------+
                    | LoopController        |
                    | Σ, B, triggers        |
                    +-----------+-----------+
                                |
         +----------------------+----------------------+
         |                      |                      |
+---------------+      +---------------+      +---------------+
| SelfCoaching  |      | AgentRegistry |      | Completeness  |
| Client        |      | (lineage)     |      | Reporter      |
| (composite)   |      +---------------+      +---------------+
+-------+-------+
        | learn / self_play / evaluate / train
        v
+----------------------------------------------------------+
| Mock stack (existing)                                     |
| AgentEvals :8080 · Self-Learning :8766 · Self-Play :8767  |
| AERL :8004 · Coaching facade :8765 (optional)             |
+----------------------------------------------------------+
```

### 4.2 Relationship to batch orchestrator

| Layer | Role in demo |
|-------|----------------|
| **Loop driver** | Simulates `{τᵢ}`, maintains `Σ`, `B`, `g`; calls `client.learn()` / `client.train()` / eval; **C06** uses `generate_suite` directly (§3.3), **C07** uses `client.self_play()` → `generate_batch` (§3.4) |
| **Orchestrator** | **Promotion gates only** for θ path (`check_promotion`); optional `record-eval` after E-path suite eval |
| **Coach demo** | Unchanged; remains the coach-mode reference |

Do **not** replace `services/orchestrator/run.py` for coach mode. The loop driver is the self-coaching-mode runtime.

### 4.3 Transports

| Mode | Transport | When |
|------|-----------|------|
| **Demo default** | `module` + in-process engines | CI, fastest path |
| **Split stack** | `MOCK_*_URL` HTTP delegation | Proves port-separated mocks |
| **Facade** | `mock_self_coaching.py serve` + `HTTPClient` | Optional Phase 5 |

---

## 5. Gap analysis (current repo → demo-ready)

| Pipeline step | Existing mock | Gap | Phase |
|---------------|---------------|-----|-------|
| Task stream `{τᵢ}` | — | Fixture JSONL + loader | P0 |
| `Retrieve(S, τ)` | — | Stub retriever | P0 |
| `AgentServe` → ξᵢ | — | `TrajectorySimulator` | P0 |
| `R_online(ξᵢ)` | rubric in self-play cases | `trajectory_scorer.score_trajectory()` per §3.2.1 | P0 |
| Support set Σ | learning events (implicit) | `.self-coaching/loop/support.jsonl` | P1 |
| Buffer B + `g` stamp | `curated/*.jsonl` (no `g`) | `.self-coaching/loop/tuning_buffer.jsonl` | P1 |
| E-path trigger + self-play sparse | `mock_self_play.generate_suite` | Loop wiring + thresholds | P2 |
| Registry apply + `g++` | `create_version` / `activate` | `GenerationState.bump()` | P2 |
| Flush B on `g++` | — | Buffer filter by generation | P2 |
| F-path free-time | — | `FreeTimeSimulator` (step budget) | P3 |
| T.train + hot-swap | `mock_aerl` | Loop + `check_promotion` | P3 |
| Completeness report | `production_readiness.py` | Per-step audit JSON/MD | **P3 done** (`tools/loop_completeness.py`) |
| Demo script + docs | `mock-run-all.sh` | `mock-self-coaching-demo.sh` | P4 |
| CI job | partial | `integration-self-coaching-loop` | P5 |

---

## 6. Data contracts (new artifacts)

All paths under coaching root `{root}/.self-coaching/loop/`:

### 6.1 `state.json`

`state.json` mirrors `meta.generation` from `mock_agent_registry`; loop store owns the `support_count` / `buffer_count` / `tasks_processed` counters.

```json
{
  "generation": 2,
  "active_version_id": "ver-abc123",
  "agent_id": "demo-agent",
  "support_count": 0,
  "buffer_count": 5,
  "tasks_processed": 24,
  "last_evo_at": "2026-06-09T12:00:00Z",
  "last_train_at": null
}
```

### 6.2 `support.jsonl` (Σ)

One row per failed `(τᵢ, ξᵢ)`:

```json
{
  "task_id": "task-003",
  "generation": 1,
  "version_id": "ver-0001",
  "trajectory_id": "traj-…",
  "score": 0.42,
  "event_text": "Agent claimed success without verification",
  "trajectory_ref": ".self-coaching/loop/trajectories/traj-….json"
}
```

### 6.3 `tuning_buffer.jsonl` (B)

```json
{
  "task_id": "task-007",
  "generation": 2,
  "version_id": "ver-abc123",
  "score": 0.91,
  "used_for_train": false,
  "trajectory_ref": "…"
}
```

### 6.4 `trajectories/{id}.json`

Full ξᵢ: messages, tool_trace_summary, task metadata, `capability`, `rubric_result`.

### 6.5 `completeness_report.json`

Emitted at end of demo (see §8). Each matrix row reports `invocation` and/or `semantic` status independently (null when that column is **—** in §7).

### 6.6 Task fixtures

`mock-services/fixtures/task_stream/tool_use_v1.jsonl` — deterministic τᵢ with `expected_tool_calls`, `answer_checks`, and simulator `agent_profile` hints so §3.2.1 scores are reproducible (not id-substring based).

---

## 7. Mock-completeness matrix

Each demo run produces counts against this matrix. Rows split into two **independent** pass dimensions:

| Column | Meaning | Example failure |
|--------|---------|-----------------|
| **[INVOCATION]** | Mock or step was called; expected artifact exists | Suite eval never ran → no `eval_runs/*/report.json` |
| **[SEMANTIC]** | Outcome matches scenario intent, not just “something was written” | Eval ran but `candidate_eval.score < current_eval.score` on a promote branch |

**PASS:** every row marked **yes** or **conditional** in a column must satisfy that column for the scenario. A row with **—** in a column is not checked on that dimension.

**Mock caveat:** `mock_agentevals` scores by deterministic name rules (`bad` / `regress` in `version_id` → lower score). C12 **[INVOCATION]** therefore proves the gate path ran; it does **not** prove the candidate actually improved. Semantic promotion quality is covered separately by C18.

| ID | Step | Mock service | [INVOCATION] | [SEMANTIC] | Evidence |
|----|------|--------------|--------------|------------|----------|
| C01 | Bootstrap registry | `mock_agent_registry` | yes | — | `agents/{id}/meta.json` |
| C02 | Serve task | `TrajectorySimulator` | yes | — | `trajectories/*.json` |
| C03 | Online eval | `score_trajectory` | yes | — | `rubric_result` on trajectory |
| C04 | Append Σ | loop store | yes | — | `support.jsonl` |
| C05 | Append B | loop store | yes | — | `tuning_buffer.jsonl` |
| C06 | Sparse self-play | `mock_self_play` | conditional | — | `POST /self-play/generate-suite` (or `generate_suite`) → `suite_id` when `0 < \|Σ\| ≤ σ_play` |
| C07 | Batch self-play | `mock_self_play` | conditional | — | `POST /self-play/generate` (or `generate_batch`) when `\|B\| < β` and idle |
| C08 | Self-learning | `mock_self_learning` | yes | — | draft `skill_bundle_version` or `memory_ref` |
| C09 | Registry draft | `mock_agent_registry` | yes | — | new `versions/*.json` |
| C10 | Generation bump | loop + registry | yes | — | `state.generation` increased |
| C11 | Buffer flush | loop store | yes | — | no B rows with `g ≤ old_g` after E-path |
| C12 | Suite eval (gate) | `mock_agentevals` | yes | — | eval report before θ swap |
| C13 | Train | `mock_aerl` | conditional | — | when `\|B\| ≥ β` and idle |
| C14 | Hot-swap | registry `activate` | conditional | — | `active.json` updated on promote |
| C15 | Split hygiene | `curate_data` | yes | — | validation/holdout non-empty if self-play ran |
| C16 | Invariant I1 | — | — | yes | `train ∩ holdout` empty (reuse production_readiness check) |
| C17 | Invariant I2 | — | — | yes | no training on flushed generations |
| C18 | Promote gate (score) | `loop_completeness` | — | conditional | `candidate_eval.score >= current_eval.score` when scenario expects T-path **promote** |

---

## 8. Completeness reporter

Extend pattern from `production_readiness.py`:

```text
mock-services/loop_completeness.py
  --root PATH
  --expect-json PATH   # optional scenario manifest
  --json | --markdown
```

**PASS criteria:**

- All matrix rows with **[INVOCATION]** = `yes` or `conditional` are `invoked` for the scenario.
- All matrix rows with **[SEMANTIC]** = `yes` or `conditional` pass their semantic predicate (see §7).
- `generation` increased ≥ 1 in standard demo scenario.
- `skill_bundle_version` or `memory_ref` changed ≥ 1 time (E-path demonstrated).
- If scenario includes idle window: `model_id` candidate activated OR `reject` with documented gate reason (T-path demonstrated).

**C18 (promote branch):** when the scenario manifest sets `t_path.outcome` to `promote` (as in `full_loop.json`), `loop_completeness.py` reads the holdout gate artifacts (`current_eval.json`, `candidate_eval.json` under the T-path run dir or equivalent loop store refs) and requires `candidate_eval.score >= current_eval.score`. This mirrors `check_promotion()`’s score comparison but is evaluated by the completeness harness so a silent regression cannot PASS on invocation evidence alone. Scenarios that expect `reject` skip C18.

Example fragment for `scenarios/full_loop.json`:

```json
{
  "name": "full_loop",
  "t_path": {
    "outcome": "promote",
    "semantic_checks": ["C18"]
  }
}
```

`completeness_report.json` should emit per-row `{ "id": "C12", "invocation": "pass", "semantic": null }` and `{ "id": "C18", "invocation": null, "semantic": "pass" }` so auditors can see which dimension failed.

Scenarios (JSON):

| Scenario file | Purpose |
|---------------|---------|
| `scenarios/e_path_only.json` | Failures → skill/memory; no idle train |
| `scenarios/t_path_only.json` | Mostly successes + idle → AERL |
| `scenarios/full_loop.json` | Mixed stream; both paths; **promote** branch triggers C18 |
| `scenarios/completeness_regress.json` | Intentionally skip a step → expect FAIL |

---

## 9. Implementation phases

### Phase P0 — Foundations (no mock stack HTTP required) — **done**

**Deliverables**

| Item | Path (implemented) |
|------|------|
| Plan doc (this file) | `docs/project/self-coaching-demo-pipeline-plan.md` |
| Task fixtures | `mock-services/fixtures/task_stream/tool_use_v1.jsonl` |
| Trajectory simulator | `modes/self-coaching/trajectory_simulator.py` |
| Online scorer | `modes/self-coaching/self-learning/trajectory_scorer.py` |
| Generation state | `modes/self-coaching/state.py` |
| Loop driver (skeleton) | `modes/self-coaching/loop_driver.py` |
| Unit tests | `tests/test_trajectory_scorer.py`, `tests/test_loop_driver_skeleton.py` |

**Exit:** Given fixture tasks, simulator produces ξᵢ; scorer returns scores matching §3.2.1 golden triples; `rᵢ < τ_fail` routes rows to Σ vs B; state read/write round-trips. **Met.**

---

### Phase P1 — Loop controller + E-path (in-process) — **done**

**Deliverables**

| Item | Path (implemented) |
|------|------|
| Loop controller | `modes/self-coaching/loop_driver.py` (`run_tasks`) |
| Loop store (Σ, B) | `modes/self-coaching/loop_store.py` → `.self-coaching/loop/*` |
| E-path | `run_e_path()` → `ModuleClient.learn()` / `MockSelfLearningEngine` |
| Registry bump | `mock_agent_registry` draft + `activate`; `state.generation` + `meta.generation` |
| Tests | `tests/test_loop_e_path.py`, fixture `e_path_v1.jsonl` |

**Exit:** After 10 tasks, `support.jsonl` and `tuning_buffer.jsonl` reflect injected failure rate; `state.json` consistent; 3 failures trigger learn + `g++`. **Met.**

---

### Phase P2 — Sparse self-play + T-path — **done** (plan had T-path as P3; implemented early)

**Deliverables**

| Item | Path (implemented) |
|------|------|
| Sparse self-play (C06) | `augment_sigma_sparse()` → `MockSelfPlayEngine.generate_suite()` before `learn()` |
| Buffer top-up (C07) | `fill_buffer_batch()` → `generate_batch()` / `MOCK_SELF_PLAY_URL` |
| T-path train + gate | `run_t_path()` → `client.train()`, holdout `MockAgentEvalsEngine`, `check_promotion()`, hot-swap |
| Free-time | `modes/self-coaching/free_time.py` (`LOOP_IDLE_AFTER`) |
| Buffer flush on E-path | `loop_store.flush_buffer_stale(g)` |
| Tests | `tests/test_loop_self_play_sparse.py`, `tests/test_loop_t_path.py`; fixtures `sparse_play_v1.jsonl`, `t_path_v1.jsonl` |

**Exit:** 3 failures → skill draft + `skill_bundle_version` change + B flushed + `g++`; T-path promotes on holdout pass and preserves B on reject. **Met.**

---

### Phase P3 — T-path (self-tuning + gates) — **done** (shipped in P2)

**Deliverables**

| Item | Path (implemented) |
|------|------|
| Free-time simulator | `modes/self-coaching/free_time.py` |
| Buffer fill self-play | `fill_buffer_batch()` → `generate_batch` (C07) |
| AERL train | `run_t_path()` → `client.train()` |
| Promotion gate | `check_promotion()` before `registry.activate` |
| Tests | `tests/test_loop_t_path.py` |

**Exit:** Success-heavy scenario fills B, trains, holdout eval → promote or reject; `training.json` / manifest present. **Met** (P2).

---

### Phase P3b — Completeness harness (C01–C18) — **done**

**Deliverables**

| Item | Path (implemented) |
|------|------|
| Completeness module | `tools/loop_completeness.py` |
| Scenario manifests | `scenarios/{full_loop,sparse_failures,dense_failures}.json` |
| T-path audit artifacts | `.self-coaching/loop/runs/t_path/`, `t_path_last.json`, `e_path_last.json` |
| Tests | `tests/test_loop_completeness.py` |

**Exit:** E2E on `full_loop.json`: generation increments, registry lineage, `completeness_report.json` PASS for every required row including **C18**; holdout gate honored. Negative: tampered `candidate_eval.score` → C18 semantic `fail` while invocation rows stay `pass`. **Met.**

This is the **“agent can validate framework end-to-end on mocks”** milestone.

---

### Phase P4 — Demo packaging

**Deliverables**

| Item | Path |
|------|------|
| Operator script | `scripts/mock-self-coaching-demo.sh` |
| Summary artifact | `{root}/.self-coaching/loop/demo_summary.md` |

**P4 documentation checklist** (required for P4 PR — not deferred to P6):

- [ ] Update [docs/guides/runbook.md](../guides/runbook.md) — add **§ Self-coaching demo (mock loop)** (new top-level section after “Merge after approval”): one-command `bash scripts/mock-self-coaching-demo.sh`, verbose `self_coaching_loop.py` + `loop_completeness.py` invocations (see Demo UX below), expected artifacts, and §10 env vars.
- [ ] Cross-link from [docs/README.md](../README.md) under Guides → runbook (one line pointing at the new section).

`deploy-skill-pack.md` stays unchanged until the script exists; the runbook section is the operator entry for the mock loop demo.

**Demo UX (target)**

```bash
# One command — module transport, ~30–60s
bash scripts/mock-self-coaching-demo.sh

# Verbose + JSON audit
python mock-services/self_coaching_loop.py run \
  --root mock-services/demo-loop \
  --scenario mock-services/fixtures/scenarios/full_loop.json \
  --report json

python tools/loop_completeness.py --root mock-services/demo-loop \
  --expect-json scenarios/full_loop.json --json
```

**Exit:** Presenter runs one script; sees generation increase, registry diff, completeness **PASS**; runbook § Self-coaching demo (mock loop) documents the same commands without reading this plan.

**Estimate:** 2 days.

---

### Phase P5 — Split-stack + CI

**Deliverables**

| Item | Path |
|------|------|
| Stack wrapper | extend `mock-stack-up.sh` or `mock-self-coaching-demo.sh --with-http` |
| CI job | `.github/workflows/ci.yml` → `integration-self-coaching-loop` |
| Facade option | env `MOCK_*_URL` same as `mock-facade-run-all.sh` |

**Exit:** CI green on Ubuntu; matrix rows C06–C14 invoked in HTTP mode; C18 passes on `full_loop.json` promote branch.

**Estimate:** 1–2 days.

---

### Phase P6 — Polish (optional before external demo)

| Item | Notes |
|------|-------|
| Terminal UI / progress | `rich` or plain log milestones (stdlib preferred) |
| Mermaid trace export | `demo_summary.md` includes evolution timeline |
| Link from `modes/self-coaching/SKILL.md` | “Run deterministic demo” pointer → runbook § Self-coaching demo (mock loop) |
| `production_readiness.py` integration | Call shared split-hygiene helpers; avoid duplication |

**Exit:** External reviewer can follow runbook (shipped P4) plus SKILL.md cross-link; no new runbook section required in P6.

**Estimate:** 1–2 days.

---

## 10. Configuration (environment)

| Variable | Default (demo) | Meaning |
|----------|----------------|---------|
| `LOOP_AGENT_ID` | `demo-agent` | Registry agent |
| `LOOP_SCENARIO` | `full_loop.json` | Task + expectation manifest |
| `LOOP_SIGMA_MIN` | `1` | Min failures to trigger E-path |
| `LOOP_SIGMA_PLAY` | `3` | Max \|Σ\| for sparse self-play |
| `LOOP_BATCH_SIZE` | `4` | β for T-path |
| `LOOP_TAU_FAIL` | `0.75` | Online failure threshold (τ_fail) |
| `LOOP_IDLE_AFTER` | `8` | Tasks before free-time window |
| `ORCHESTRATOR_EVAL_BACKEND` | `agentevals` | Suite eval for gates |
| `ORCHESTRATOR_TRAIN_BACKEND` | `aerl` | T-path |
| `AGENTEVALS_SUITE_ID` | `tool-use-canary` | Canary |
| `AGENTEVALS_SUITE_ID_HOLDOUT` | `tool-use-holdout` | Promotion gate |

*τ_fail is the online rubric threshold per trajectory; `min_score` is the drop-detector floor on suite EvalMetrics ([evaluators.md](../design/evaluators.md), default `0.80`). They are independent.*

---

## 11. Testing strategy

| Layer | What |
|-------|------|
| **Unit** | simulator, scorer, state, flush logic, generation invariants |
| **Integration** | E-path only, T-path only, full loop (module) |
| **HTTP** | P5 split stack |
| **Regression** | `completeness_regress.json` must FAIL |
| **Existing** | Do not break `mock-coach-demo.sh`, `production_readiness.py`, `mock-facade-run-all.sh` |

**CI time budget:** full loop &lt; 90s (deterministic mocks, no long polling).

---

## 12. Documentation deliverables

| Doc | Phase | Action |
|-----|-------|--------|
| This plan | P0 | Source of truth for demo pipeline |
| [mock-platform-design.md](mock-platform-design.md) | P0 | § “Phase 5 — Self-coaching loop demo” with link (done) |
| [progress.md](progress.md) | P0–P5 | Track P0–P5 status |
| [docs/guides/runbook.md](../guides/runbook.md) | **P4** | New **§ Self-coaching demo (mock loop)** — operator commands for `mock-self-coaching-demo.sh` (see P4 checklist) |
| [docs/README.md](../README.md) | **P4** | Guides index entry → runbook § Self-coaching demo (mock loop) |
| `modes/self-coaching/SKILL.md` | P6 | One-paragraph “Run deterministic demo” → runbook (optional polish) |

---

## 13. Non-goals (this milestone)

- Real LLM inference or live agent API
- SQLite / async Coaching API (M2)
- Coach scheduler / cron (M5)
- Git-tagged skill bundle apply (M3) — record draft only
- Canary deploy to production agent API
- Replacing `services/orchestrator/run` for coach mode

---

## 14. Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Ambiguous E-path self-play threshold | Wrong demo narrative | Fixed in §3.3; scenario JSON asserts C06 |
| Concurrent E + T | Stale training data | E before T; generation tags; pause stream in P3 |
| Per-task vs suite eval confusion | Integrators miswire R | Document two-tier eval; matrix C03 vs C12 |
| Invocation vs semantic conflation | PASS while candidate regresses | C12 **[INVOCATION]** only; C18 **[SEMANTIC]** score gate on `full_loop` promote branch |
| CI flakiness (async runs) | Red builds | Use in-process engines in CI; HTTP job optional |
| Scope creep into M2/M3 | Delayed demo | Strict non-goals; stub retrieve / skill apply |
| Duplication with `production_readiness` | Drift | Shared `curate_data` + split checks in `loop_completeness` |

---

## 15. Success criteria (demo-ready)

The pipeline is **demo-ready** when all of the following hold:

1. **Operator:** `bash scripts/mock-self-coaching-demo.sh` exits 0 on a clean machine (bash + Python 3.11 only).
2. **Narrative:** Logs show task serve → failures → learning → `g++` → idle → train → promote/reject.
3. **Artifacts:** `state.json`, registry versions, `support.jsonl`, `tuning_buffer.jsonl`, eval reports, training manifest.
4. **Audit:** `loop_completeness.py` returns **PASS** for `full_loop.json`.
5. **CI:** New job green on `main` PRs.
6. **No regressions:** Existing mock-platform CI jobs unchanged and passing.

---

## 16. Timeline summary

| Phase | Focus | Cumulative |
|-------|-------|------------|
| P0 | Fixtures + simulator + state | ~2 days |
| P1 | Loop controller (observe only) | ~5 days |
| P2 | E-path | ~8 days |
| P3 | T-path + gates | ~11 days |
| P4 | Demo script + completeness | ~13 days |
| P5 | HTTP + CI | ~15 days |
| P6 | Polish | ~17 days |

Parallelizable: P0 tests while reviewing plan; P5 can trail demo if module-only demo is sufficient for first presentation.

---

## 17. Post-demo path

| Demo component | Production evolution |
|----------------|---------------------|
| `TaskStream` fixtures | Production agent trajectory export |
| `TrajectorySimulator` | Real agent serve API |
| `R_online` | Proxy rubric or fast classifier |
| `R_suite` | Live AgentEvals (integration-plan Phase 0–1) |
| `FreeTimeSimulator` | Queue depth / cron idle window |
| Loop driver | Optional long-running service; coach still uses batch orchestrator |
| Completeness matrix | Staging smoke checklist before promote |

---

## 18. Open decisions (confirm before P2)

| # | Question | Recommendation |
|---|----------|----------------|
| D1 | E-path applies **skill only**, **memory only**, or classifier chooses? | Match `classify_event` — demo scenario forces one of each in different runs |
| D2 | After E-path, auto-**activate** draft or leave inactive until suite pass? | Leave inactive until `R_suite` pass (matches coach promote flow) |
| D3 | Default demo transport: module or HTTP? | Module for CI; HTTP flag for fidelity demo |
| D4 | Single coaching root vs per-agent subroots? | Single `demo-loop` root (self-coaching); unlike coach demo |
| D5 | Include generation timeline in SKILL.md? | Yes in P6 — one paragraph + link to runbook |

---

## 19. File tree (target)

```text
modes/self-coaching/
  loop_driver.py, loop_store.py, state.py, free_time.py
  trajectory_simulator.py, self-learning/trajectory_scorer.py
mock-services/fixtures/task_stream/*.jsonl
scenarios/{full_loop,sparse_failures,dense_failures}.json
tools/loop_completeness.py
scripts/mock-self-coaching-demo.sh          # P4
tests/test_loop_{completeness,e_path,t_path,self_play_sparse,driver_skeleton}.py
  test_trajectory_scorer.py
docs/project/self-coaching-demo-pipeline-plan.md
```

---

## 20. Related commands (today vs target)

| Today | Target |
|-------|--------|
| `python mock_self_coaching.py run-all` | Still valid; batch baseline |
| `bash scripts/mock-production-readiness.sh` | Still valid; artifact contract |
| `bash scripts/mock-coach-demo.sh` | Coach mode reference |
| — | `bash scripts/mock-self-coaching-demo.sh` **(new, P4)** — documented in runbook § Self-coaching demo (mock loop) |

---

*Last updated: 2026-06-09. P0–P3 implemented (completeness harness + C18); check off phases in [progress.md](progress.md).*
