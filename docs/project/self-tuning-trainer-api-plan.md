# Self-tuning trainer — API & migration plan

**Status:** **DRAFT** — for review and edit (API shapes from AERL trainer service + in-repo `mock_aerl.py`, 2026-06-15)  
**Goal:** Define the **real AERL / trainer backend** for the **model path** (SFT, GRPO, preference RL), exposed via **POST/GET HTTP APIs**, while preserving the existing loop and orchestrator **`train()`** contract through adapters.

**Related:** [self-learning-review-agent-plan.md](self-learning-review-agent-plan.md) (M2 learner API), [mock-to-real-migration.md](mock-to-real-migration.md) (M4), [pipelines.md](../design/pipelines.md), [integrations/aerl.md](../design/integrations/aerl.md), [integrations/coaching_api.md](../design/integrations/coaching_api.md), [integration/mapping.md](../integration/mapping.md).

---

## 1. Problem statement

### 1.1 What exists today

| Piece | Location | Behavior |
|-------|----------|----------|
| Loop T-path | `modes/self-coaching/loop_driver.py` | On buffer threshold → `client.train(pipeline, dataset, base_model)` → sync poll |
| Mock engine | `mock-services/mock_aerl.py` | Deterministic async runs; writes `training_run_manifest.json`; drafts registry `model_id` |
| HTTP (mock) | `POST /v1/training/runs`, `POST /v1/pipelines/{id}/run` | Same engine; `:8004` default |
| Client | `services/adapters/aerl_client.py` | `create_training_run`, `wait_for_training_run`, `run_pipeline_argv` |
| Train adapter | `services/adapters/train_adapter.py` | `AERLTrainAdapter.train()` — minimal fields only |
| Coaching facade | `POST /training/runs` in `mock-services/contracts/openapi.yaml` | Thin `TrainingRequest` (`pipeline`, `dataset`, `base_model`) |
| Pipeline scripts | `modes/self-coaching/self-tuning/pipelines/` | HTTP argv runner + local `AERL_ROOT` fallback |

The mock treats training as a **short async job** with synthetic `val_loss` and a candidate id. Production intent is different:

- Training runs as a **long-lived trainer worker** (GPU cluster job or AERL orchestrator), not an in-process classifier.
- **GRPO / RL** requires **rollout inference** against an OpenAI-compatible **LLM proxy** (policy model, reference model, judge).
- **Reward signals** arrive from evaluators, rubrics, and preference curation — a stable **interchange schema** is required.
- Runs should optionally **pin agent state** from self-learning (memory version, skill bundle, prompt bundle) for reproducibility and rollback.
- Callers need **async create + poll** (hours-long jobs) and a separate **argv/stream path** for operator scripts.

### 1.2 What we need

1. **HTTP API** for creating, polling, and cancelling training runs (`POST` + `GET`).
2. **Rollout + LLM proxy contract** — how the trainer reaches inference during GRPO rollouts.
3. **Reward interchange schema** — JSONL + inline spec for SFT, preference, and scalar-reward RL.
4. **Optional `agent_snapshot`** — memory/skill/prompt/registry versions at train start.
5. **Adapter parity** — loop and orchestrator keep calling `train()`; mode/env selects mock vs AERL backend (same pattern as AgentEvals M1 and self-learning M2).
6. **Mock extension** — deterministic production-shaped routes in CI; **R5** mock-module gate unchanged.
7. **Mapping discipline** — terminal run → `candidate_model_id`, `manifest`, `registry_version_id` for local `AgentRegistry` (M4 uses local registry; M5 optional for remote).
8. **Two typed clients** — **TrainingClient** (job + loss) and **RestClient** (checkpoints + weights + side processes); see §3.2.

---

## 2. Design principles

| ID | Principle |
|----|-----------|
| **ST-R1** | **Adapter parity, not replacement.** Extend `services/adapters/` and mock HTTP; do not fork parallel client trees. |
| **ST-R2** | **One orchestrator surface.** `SelfCoachingClient.train()` / `AERLTrainAdapter.train()` remain the only loop/orchestrator entry; trainer HTTP is an implementation detail. |
| **ST-R3** | **Trainer owns execution.** Callers submit datasets, hyperparameters, rollout/proxy config — not embedded training loops. |
| **ST-R4** | **Async by default.** `POST /v1/training/runs` returns **202** + `run_id`; poll `GET /v1/training/runs/{id}`. Coaching facade may block via adapter `wait`. |
| **ST-R5** | **Two entry surfaces, one engine.** Operator scripts use `POST /v1/pipelines/{id}/run` (argv → log text); orchestrator uses structured `POST /v1/training/runs`. Both must resolve to the same run record when `run_id` is returned. |
| **ST-R6** | **Rollout proxy is explicit.** Never assume `OPENAI_*` env on the trainer host; pass `rollout.llm_proxy` (or `rollout_config_ref`) on the run request. Env vars in `self-tuning/services/.env` are **client-side defaults** for scripts only. |
| **ST-R7** | **Rewards are data, not magic.** Datasets declare `reward_schema_version`; trainer validates before queueing. |
| **ST-R8** | **Snapshot is optional but typed.** When present, `agent_snapshot` records lineage; adapter copies into `training_run_manifest.json`. |
| **ST-R9** | **Local registry for M4.** Trainer may register checkpoints remotely, but **activation** stays in the loop via local `AgentRegistry` unless M5 applies. |
| **ST-R10** | **Two clients, one service.** **TrainingClient** owns the *job lifecycle* (run id, algorithm, data, config, loss). **RestClient** owns *durable artifacts* (checkpoints, weights, side processes). Same `TRAINER_BASE_URL`; different path prefixes and repo modules. |

---

## 3. Target architecture

```text
                    +---------------------------+
                    |  Triggers                 |
                    |  - Loop T-path (buffer B) |
                    |  - Orchestrator model path|
                    |  - Coach drop → train     |
                    |  - Operator run-pipeline  |
                    +-------------+-------------+
                                  |
                                  v
                    +---------------------------+
                    |  Coaching API (optional)  |
                    |  POST /training/runs      |
                    +-------------+-------------+
                                  |
                                  v
                    +---------------------------+
                    |  Train adapter            |
                    |  TrainingClient + mapping |
                    +-------------+-------------+
                                  |
          +-----------------------+-----------------------+
          |                       |                       |
          v                       v                       v
+-------------------+  +-------------------+  +-------------------+
| TrainingClient    |  | TrainingClient    |  | RestClient        |
| POST/GET          |  | POST /v1/pipelines|  | GET checkpoints,  |
| /v1/training/runs |  | /{id}/run (argv)  |  | models, processes |
+-------------------+  +-------------------+  +-------------------+
          |                       |                       |
          +-----------------------+-----------------------+
                                  |
                                  v
                    +---------------------------+
                    |  AERL trainer service     |
                    |  (job queue + workers)    |
                    +-------------+-------------+
                                  |
          +-----------------------+-----------------------+
          |                       |                       |
          v                       v                       v
   Curated JSONL            LLM proxy               Artifact store
   (SFT / pref / reward)    (rollout inference)     (checkpoints / weights)
                                  |
                                  v
                    +---------------------------+
                    |  Adapter (this repo)      |
                    |  → training_run_manifest  |
                    |  → candidate_model_id     |
                    |  → registry draft         |
                    +---------------------------+
```

### 3.1 Trigger modes (mapped to real endpoints)

| Mode | Trigger | API | `wait` typical |
|------|---------|-----|----------------|
| **Loop T-path** | Buffer `B` full | Adapter → `POST /v1/training/runs` + poll | `true` (loop blocks; env `AERL_TIMEOUT_S`) |
| **Orchestrator model path** | `improvement_path: model` | Same via `AERLTrainAdapter` | `true` or poll budget |
| **Operator SFT/GRPO** | `run-pipeline.sh` | `POST /v1/pipelines/{sft\|grpo}/run` | sync (log body) |
| **Coach scheduled train** | Drop + curation gate | `POST /v1/training/runs` `wait: false` | async + webhook optional |
| **Mock / thin sync** | Legacy demo | In-process `mock_aerl` or coaching `POST /training/runs` | immediate |

### 3.2 Two client interfaces

Production integrations expose **one trainer HTTP service** but **two typed clients** in this repo. Do not fold artifact listing into the training-run poll response — query RestClient after the run succeeds.

| Client | Responsibility | Primary paths | Repo module (M4) |
|--------|----------------|---------------|------------------|
| **TrainingClient** | Training **job** lifecycle: create, poll, cancel, metrics | `/v1/training/…`, `/v1/pipelines/…`, `/v1/rollout/…`, `/v1/rewards/…` | `services/adapters/training_client.py` |
| **RestClient** | **Durable artifacts** after or beside training: checkpoints, model weights, export/merge processes | `/v1/checkpoints/…`, `/v1/models/…`, `/v1/processes/…` | `services/adapters/trainer_rest_client.py` |

**TrainingClient** answers: *what run is this, what algorithm, what data, what config, what loss?*  
**RestClient** answers: *what checkpoints exist, where are the weights, what side jobs ran?*

```text
TrainingClient                          RestClient
────────────────────────────────        ────────────────────────────────
training_run_id  (id)                   checkpoint_id
base_model                               parent base_model / merged_from[]
trainer  (algorithm)                     format, shard_count, size_bytes
training_data  (refs, counts, schema)    weights_uri / artifact_manifest
pipeline_config  (hyperparams, rollout)  training_run_id  (lineage link)
metrics / loss_curve                     related processes (export, merge)
status, phase, progress                  served endpoint (if deployed)
```

**Loop / orchestrator path:** `AERLTrainAdapter` uses **TrainingClient only** until `status=succeeded`, then optionally **RestClient** `GET /v1/checkpoints?training_run_id=…` to resolve `candidate_model_id` and weight URIs for eval and manifest.

**Operator / coach path:** may use RestClient directly to list historical checkpoints, diff weights, or poll an export process without starting a new training run.

---

## 4. HTTP API specification (production trainer)

**Base path:** `{TRAINER_BASE_URL}` or `{MOCK_AERL_URL}` (default `http://localhost:8004`)  
**Auth:** Bearer token — `401 unauthorized` on bad/missing token (`TRAINER_API_KEY`).  
**Path prefix:** Canonical trainer API is `/v1/…`. Coaching facade uses `/training/runs` (adapter translates).

**Layout:**

| Part | Client | Sections |
|------|--------|----------|
| **A** | TrainingClient | §4.0–§4.12 — runs, pipelines, rollout, rewards, health |
| **B** | RestClient | §4.13–§4.16 — checkpoints, models, processes |

### 4.0 Common request fields (TrainingClient)

Shared by `POST /v1/training/runs`:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `pipeline_id` | string | required | `sft` \| `grpo` \| `dpo` \| `orpo` (trainer advertises supported set via `GET /v1/pipelines`) |
| `base_model` | string | required | HuggingFace id, internal checkpoint id, or served model name |
| `dataset_refs` | string[] | `[]` | URIs or paths trainer can read (JSONL, parquet, hf://…) |
| `agent_id` | string | optional | Lineage / registry correlation |
| `coaching_root` | string | optional | Hint for manifest write-back (adapter-owned in M4) |
| `hyperparameters` | object | `{}` | Trainer-normalized keys (see §4.8) |
| `rollout` | object | optional | Required for `grpo` and RL pipelines (§4.5) |
| `reward_spec` | object | optional | Inline reward mapping when not solely in dataset (§4.6) |
| `agent_snapshot` | object | optional | Self-learning / registry pin (§4.7) |
| `dry_run` | bool | `false` | Validate + plan only; no GPU allocation |
| `wait` | bool | `false` | `true` = block until terminal status (**200**); `false` = **202** + poll |
| `idempotency_key` | string | optional | Duplicate POST returns same `run_id` within TTL |
| `labels` | object | `{}` | Freeform tags (`source`, `capability`, `coach_run_id`) |

**Validation:**

- Unknown `pipeline_id` → **400** `unsupported_pipeline`
- `grpo` without `rollout` → **400** `rollout_required`
- `dataset_refs` empty and no default pool for agent → **400** `dataset_required`
- `reward_schema_version` in dataset header incompatible with trainer → **400** `reward_schema_mismatch`

### 4.1 `POST /v1/training/runs` — create training job

**Request (SFT example):**

```json
{
  "pipeline_id": "sft",
  "base_model": "org/base-agent-7b",
  "dataset_refs": ["s3://coaching/curated/train.jsonl"],
  "agent_id": "agent_abc",
  "hyperparameters": {
    "method": "lora",
    "epochs": 2,
    "learning_rate": 2e-5,
    "lora_rank": 16
  },
  "agent_snapshot": {
    "registry_version_id": "ver-prod-42",
    "memory_version": "mem-2026-06-10T12:00:00Z",
    "skill_bundle_version": "skills-a1b2c3",
    "prompt_bundle_version": "prompts-v3",
    "eval_run_id": "eval_holdout_991"
  },
  "labels": {"source": "loop-t-path", "capability": "tool-use"},
  "wait": false
}
```

**Request (GRPO example — rollout + reward):**

```json
{
  "pipeline_id": "grpo",
  "base_model": "org/base-agent-7b",
  "dataset_refs": ["file:///coaching/curated/pref_train.jsonl"],
  "hyperparameters": {
    "group_size": 8,
    "num_iterations": 4,
    "kl_coef": 0.02
  },
  "rollout": {
    "llm_proxy": {
      "base_url": "https://llm-proxy.internal/v1",
      "api_key_ref": "vault:rollout-key",
      "models": {
        "policy": "candidate-lora-adapter",
        "reference": "org/base-agent-7b",
        "judge": "gpt-4o-mini"
      },
      "timeout_s": 120,
      "max_tokens": 4096
    },
    "env": {
      "type": "hermes_agent",
      "max_turns": 12,
      "tool_mode": "default"
    },
    "sampling": {
      "temperature": 0.7,
      "top_p": 0.95,
      "n_samples_per_prompt": 4
    }
  },
  "reward_spec": {
    "schema_version": "reward.ic.v1",
    "primary": "scalar",
    "components": [
      {"name": "task_success", "weight": 0.6, "source": "field:metrics.success"},
      {"name": "rubric_score", "weight": 0.3, "source": "field:rewards.rubric"},
      {"name": "length_penalty", "weight": -0.1, "source": "fn:length_penalty_v1"}
    ]
  },
  "wait": false
}
```

**Async response (202, `wait=false`):**

```json
{
  "id": "train_2026-06-15T09-12-00_f7e2",
  "pipeline_id": "grpo",
  "status": "queued",
  "created_at": "2026-06-15T09:12:00Z",
  "updated_at": "2026-06-15T09:12:00Z",
  "poll_url": "/v1/training/runs/train_2026-06-15T09-12-00_f7e2"
}
```

**Sync response (200, `wait=true`, terminal):** same shape as §4.2 completed run.

**Errors:**

| HTTP | Code | When |
|------|------|------|
| 400 | `invalid_request` | Malformed JSON, validation failures |
| 400 | `unsupported_pipeline` | Unknown `pipeline_id` |
| 400 | `rollout_required` | RL pipeline missing `rollout` |
| 400 | `dataset_required` | No datasets resolvable |
| 400 | `reward_schema_mismatch` | Dataset header vs `reward_spec` |
| 401 | `unauthorized` | Bad/missing bearer |
| 409 | `idempotency_conflict` | Same key, different body hash |
| 413 | `dataset_too_large` | Exceeds `trainer.max_records_per_run` |
| 422 | `proxy_unreachable` | `dry_run` or preflight cannot reach `rollout.llm_proxy` |
| 503 | `queue_full` | Backpressure; retry after `Retry-After` |

### 4.2 `GET /v1/training/runs/{run_id}` — poll run status (TrainingClient)

Returns a **`TrainingRunRecord`** (§4.2.1). Alias: `training_run_id` == `id`.

**Response (running):**

```json
{
  "id": "train_2026-06-15T09-12-00_f7e2",
  "training_run_id": "train_2026-06-15T09-12-00_f7e2",
  "status": "running",
  "phase": "rollout",
  "trainer": {
    "algorithm": "grpo",
    "pipeline_id": "grpo",
    "method": "lora",
    "implementation": "aerl-grpo-v2"
  },
  "base_model": "org/base-agent-7b",
  "training_data": {
    "dataset_refs": ["s3://coaching/curated/pref_train.jsonl"],
    "record_counts": {"preference": 1200},
    "reward_schema_version": "reward.ic.v1",
    "bytes_total": 4800000
  },
  "pipeline_config": {
    "hyperparameters": {"group_size": 8, "num_iterations": 4, "kl_coef": 0.02, "learning_rate": 1e-5},
    "rollout": {"config_ref": "hermes-tool-use-v1"},
    "reward_spec": {"schema_version": "reward.ic.v1", "primary": "scalar"}
  },
  "progress": {
    "epoch": 1,
    "step": 120,
    "total_steps": 400,
    "rollouts_completed": 96,
    "rollouts_total": 320
  },
  "metrics_partial": {
    "train_loss": 0.42,
    "val_loss": 0.38,
    "reward_mean": 0.55
  },
  "agent_id": "agent_abc",
  "agent_snapshot": {
    "registry_version_id": "ver-prod-42",
    "memory_version": "mem-2026-06-10T12:00:00Z",
    "skill_bundle_version": "skills-a1b2c3"
  },
  "created_at": "2026-06-15T09:12:00Z",
  "started_at": "2026-06-15T09:12:05Z",
  "updated_at": "2026-06-15T09:18:22Z"
}
```

**Response (completed):**

```json
{
  "id": "train_2026-06-15T09-12-00_f7e2",
  "training_run_id": "train_2026-06-15T09-12-00_f7e2",
  "status": "succeeded",
  "phase": "done",
  "trainer": {
    "algorithm": "grpo",
    "pipeline_id": "grpo",
    "method": "lora",
    "implementation": "aerl-grpo-v2"
  },
  "base_model": "org/base-agent-7b",
  "training_data": {
    "dataset_refs": ["s3://coaching/curated/pref_train.jsonl"],
    "record_counts": {"preference": 1200},
    "reward_schema_version": "reward.ic.v1"
  },
  "pipeline_config": {
    "hyperparameters": {"group_size": 8, "kl_coef": 0.02},
    "rollout": {"config_ref": "hermes-tool-use-v1"},
    "reward_spec": {"schema_version": "reward.ic.v1"}
  },
  "metrics": {
    "train_loss": 0.28,
    "val_loss": 0.31,
    "reward_mean": 0.72,
    "kl_to_reference": 0.04
  },
  "primary_checkpoint_id": "ckpt-grpo-f7e2",
  "candidate_model_id": "ckpt-grpo-f7e2",
  "candidate_endpoint": "https://infer.internal/v1/models/candidate-f7e2",
  "rollout_summary": {
    "proxy_base_url": "https://llm-proxy.internal/v1",
    "total_rollout_calls": 1280,
    "total_tokens": {"input": 2400000, "output": 890000}
  },
  "created_at": "2026-06-15T09:12:00Z",
  "started_at": "2026-06-15T09:12:05Z",
  "finished_at": "2026-06-15T09:45:10Z",
  "duration_ms": 1985000
}
```

**Note:** `candidate_model_id` on the run record is a **convenience pointer** to the primary checkpoint. Authoritative weight locations and shard manifests live on **RestClient** `GET /v1/checkpoints/{id}` (§4.13).

**Failed example:**

```json
{
  "id": "train_2026-06-15T09-12-00_f7e2",
  "status": "failed",
  "trainer": {"algorithm": "grpo", "pipeline_id": "grpo"},
  "base_model": "org/base-agent-7b",
  "error": {
    "code": "rollout_timeout",
    "message": "LLM proxy exceeded 120s on batch 14",
    "retryable": true
  }
}
```

**Errors:**

| HTTP | Code | When |
|------|------|------|
| 404 | `run_not_found` | Unknown or evicted `run_id` (retention: `trainer.run_ttl_hours`, default **168**) |

#### 4.2.1 `TrainingRunRecord` — TrainingClient report schema

Canonical object returned by `GET /v1/training/runs/{id}` and embedded in list responses.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Same as `training_run_id` |
| `training_run_id` | string | yes | Stable run identifier |
| `status` | string | yes | `queued` \| `running` \| `succeeded` \| `failed` \| `cancelled` |
| `phase` | string | when running | `queued` \| `data_prep` \| `rollout` \| `train` \| `checkpoint` \| `done` |
| `trainer` | object | yes | Tuning algorithm identity (§4.2.2) |
| `base_model` | string | yes | Starting weights / model id |
| `training_data` | object | yes | Dataset refs + resolved stats (§4.2.3) |
| `pipeline_config` | object | yes | Hyperparameters + rollout + reward (§4.2.4) |
| `metrics` | object | terminal ok | Final scalars: `train_loss`, `val_loss`, `reward_mean`, … |
| `metrics_partial` | object | running | Latest scalars; may change each poll |
| `loss_curve_url` | string | optional | Pointer to full series (§4.2.5); omitted when inline only |
| `progress` | object | running | Step/epoch/rollout counters |
| `primary_checkpoint_id` | string | succeeded | Top checkpoint from this run (RestClient key) |
| `candidate_model_id` | string | succeeded | Deprecated alias of `primary_checkpoint_id` in adapters |
| `candidate_endpoint` | string | optional | Served inference route if already deployed |
| `agent_snapshot` | object | optional | §4.7 |
| `rollout_summary` | object | GRPO terminal | Token / call accounting |
| `error` | object | failed | Structured failure |
| `created_at`, `started_at`, `finished_at`, `updated_at`, `duration_ms` | | | Timestamps |

#### 4.2.2 `trainer` object (algorithm)

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `algorithm` | string | `grpo` | Tuning family: `sft`, `grpo`, `dpo`, `orpo`, `ppo` |
| `pipeline_id` | string | `grpo` | Registered pipeline id (`GET /v1/pipelines`) |
| `method` | string | `lora` | Weight update mode: `full`, `lora`, `qlora` |
| `implementation` | string | `aerl-grpo-v2` | Trainer-internal stack id (for support/debug) |
| `loss_type` | string | `policy_gradient` | Optional: `cross_entropy`, `dpo`, `pairwise_ranking` |

#### 4.2.3 `training_data` object

| Field | Type | Notes |
|-------|------|-------|
| `dataset_refs` | string[] | URIs passed at create time |
| `record_counts` | object | Per-type counts after validation, e.g. `{"sft": 500, "preference": 1200}` |
| `reward_schema_version` | string | From dataset header / `reward_spec` |
| `bytes_total` | int | Optional total bytes read |
| `split` | object | Optional `{"train": 0.9, "val": 0.1}` when trainer holds out |
| `fingerprint` | string | Optional hash for reproducibility audit |

#### 4.2.4 `pipeline_config` object

Immutable copy of effective config after server defaults merged.

| Field | Type | Notes |
|-------|------|-------|
| `hyperparameters` | object | §4.8 normalized keys |
| `rollout` | object | §4.5 (GRPO/RL) |
| `reward_spec` | object | §4.6 |
| `seed` | int | Optional |
| `compute` | object | Optional `{"gpus": 4, "precision": "bf16"}` |

#### 4.2.5 `GET /v1/training/runs/{run_id}/metrics` — loss & reward series

TrainingClient endpoint for **time series** too large to inline on every poll.

**Query params:** `series` (comma-separated, default `train_loss,val_loss`), `downsample` (max points, default 500).

**Response (200):**

```json
{
  "training_run_id": "train_2026-06-15T09-12-00_f7e2",
  "series": {
    "train_loss": [{"step": 0, "epoch": 0, "value": 1.2}, {"step": 100, "epoch": 1, "value": 0.42}],
    "val_loss": [{"step": 100, "epoch": 1, "value": 0.38}],
    "reward_mean": [{"step": 50, "value": 0.55}]
  },
  "last_step": 120,
  "complete": false
}
```

Returns **404** `run_not_found`; **409** `metrics_not_ready` if run still `queued`.

### 4.3 `POST /v1/training/runs/{run_id}/cancel` — cancel queued or running job

**Response (200):**

```json
{
  "id": "train_2026-06-15T09-12-00_f7e2",
  "status": "cancelled",
  "cancelled_at": "2026-06-15T09:20:00Z"
}
```

Returns **409** `not_cancellable` if already terminal.

### 4.4 `GET /v1/training/runs` — list runs (ops)

**Query params:** `agent_id`, `pipeline_id`, `status`, `since`, `limit` (default 50, max 200).

**Response (200):**

```json
{
  "runs": [
    {
      "id": "train_2026-06-15T09-12-00_f7e2",
      "pipeline_id": "grpo",
      "status": "succeeded",
      "created_at": "2026-06-15T09:12:00Z",
      "candidate_model_id": "checkpoint/grpo-f7e2"
    }
  ],
  "next_cursor": null
}
```

### 4.5 Rollout configuration & LLM proxy

Production GRPO/agentic RL needs **inference during training**. The trainer does not read client-side `OPENAI_*` env; callers supply `rollout` on the run (or register a reusable config).

#### 4.5.1 `rollout` object

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `llm_proxy` | object | GRPO/RL | OpenAI-compatible gateway (§4.5.2) |
| `env` | object | optional | Agent environment (`hermes_agent`, `math`, `custom`) |
| `sampling` | object | optional | Temperature, top_p, n_samples |
| `config_ref` | string | optional | `rollout_configs/{id}` — alternative to inline `llm_proxy` |

#### 4.5.2 `rollout.llm_proxy` — OpenAI-compatible proxy

| Field | Type | Notes |
|-------|------|-------|
| `base_url` | string | e.g. `https://llm-proxy.internal/v1` — **no** trailing slash |
| `api_key` | string | Inline secret (discouraged; staging only) |
| `api_key_ref` | string | Preferred: `vault:…`, `k8s-secret:…` resolved by trainer |
| `models.policy` | string | Trainable / adapter-mounted model name |
| `models.reference` | string | Frozen reference for KL penalty |
| `models.judge` | string | Optional reward model or LLM-as-judge |
| `headers` | object | Extra headers (tenant, trace id) |
| `timeout_s` | number | Per-request timeout (default **120**) |
| `max_tokens` | int | Rollout generation cap |
| `rate_limit` | object | Optional `{rpm, tpm}` throttle hints |

**Proxy behavior (trainer-side requirements):**

1. Expose **chat/completions** (and **embeddings** if reward model needs it) compatible with OpenAI schema.
2. Support **hot-swapping** `models.policy` to the current training checkpoint (trainer updates proxy route table each checkpoint save).
3. Return **usage** tokens in response for `rollout_summary` accounting.
4. Fail fast with **422** on `dry_run: true` when proxy health check fails.

#### 4.5.3 `POST /v1/rollout/configs` — register reusable rollout profile (optional)

**Request:**

```json
{
  "id": "hermes-tool-use-v1",
  "llm_proxy": {
    "base_url": "https://llm-proxy.internal/v1",
    "api_key_ref": "vault:rollout-key",
    "models": {"policy": "dynamic", "reference": "org/base-agent-7b"}
  },
  "env": {"type": "hermes_agent", "max_turns": 12},
  "sampling": {"temperature": 0.7, "n_samples_per_prompt": 4}
}
```

**Response (201):** `{ "id": "hermes-tool-use-v1", "created_at": "…" }`

Training runs may set `"rollout": {"config_ref": "hermes-tool-use-v1"}` and override individual fields (shallow merge).

#### 4.5.4 `POST /v1/rollout/configs/validate` — preflight proxy + env

**Request:** same body as inline `rollout` on a training run.

**Response (200):**

```json
{
  "valid": true,
  "checks": [
    {"name": "proxy_health", "ok": true, "latency_ms": 42},
    {"name": "policy_model_route", "ok": true},
    {"name": "reference_model_route", "ok": true}
  ]
}
```

### 4.6 Reward interchange schema

Rewards flow from **self-play**, **self-evaluation**, and human curation into JSONL datasets. The trainer validates records before queueing.

#### 4.6.1 Schema version

Canonical version string: **`reward.ic.v1`** (interchange v1).

Dataset file **first line** (optional header record):

```json
{"_type": "dataset_header", "reward_schema_version": "reward.ic.v1", "record_types": ["sft", "preference", "trajectory_reward"]}
```

#### 4.6.2 Record types

**SFT** (supervised):

```json
{
  "id": "sft-001",
  "type": "sft",
  "messages": [{"role": "user", "content": "…"}, {"role": "assistant", "content": "…"}],
  "tool_trace_summary": [],
  "metadata": {"source": "eval_failure", "capability": ["debugging"], "privacy_checked": true}
}
```

**Preference** (pairwise):

```json
{
  "id": "pref-001",
  "type": "preference",
  "prompt": "…",
  "chosen": "…",
  "rejected": "…",
  "rewards": {"rubric": 0.85, "human": 1.0},
  "judge": {"model": "gpt-4o-mini", "rubric_id": "tool-use-v2"},
  "metadata": {"privacy_checked": true}
}
```

**Trajectory reward** (GRPO / scalar RL):

```json
{
  "id": "traj-001",
  "type": "trajectory_reward",
  "prompt": "…",
  "trajectory": [{"role": "assistant", "content": "…", "tool_calls": []}],
  "rewards": {
    "scalar": 0.72,
    "components": {"task_success": 1.0, "rubric_score": 0.8, "length_penalty": -0.05}
  },
  "metrics": {"success": true, "steps": 5},
  "metadata": {"session_id": "sess_abc", "eval_run_id": "eval_991"}
}
```

#### 4.6.3 `reward_spec` on training run (aggregation)

When rewards are split across fields or need runtime weighting:

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | string | Must match dataset header |
| `primary` | string | `scalar` \| `preference` \| `sft` |
| `components` | array | Weighted mapping (see GRPO example §4.1) |
| `clip_min` / `clip_max` | number | Optional normalization |
| `missing_policy` | string | `fail` \| `skip_record` \| `zero` (default `fail`) |

#### 4.6.4 `GET /v1/rewards/schema` — schema discovery

**Response (200):**

```json
{
  "current_version": "reward.ic.v1",
  "supported_versions": ["reward.ic.v1"],
  "record_types": ["sft", "preference", "trajectory_reward"],
  "component_functions": ["length_penalty_v1", "tool_error_penalty_v1"]
}
```

#### 4.6.5 `POST /v1/rewards/validate` — validate dataset without training

**Request:**

```json
{
  "dataset_refs": ["s3://coaching/curated/pref_train.jsonl"],
  "reward_spec": {"schema_version": "reward.ic.v1", "primary": "preference"}
}
```

**Response (200):**

```json
{
  "valid": true,
  "record_counts": {"preference": 1200, "sft": 0, "trajectory_reward": 0},
  "warnings": [{"line": 44, "code": "missing_human_review", "message": "human_reviewed=false"}]
}
```

### 4.7 Optional `agent_snapshot` (self-learning lineage)

Pins **non-model** agent state at train time for reproducibility, rollback, and coach audit. Populated by the adapter from local registry + optional learner service query.

| Field | Type | Source |
|-------|------|--------|
| `registry_version_id` | string | Parent production version (`loop_driver` T-path) |
| `memory_version` | string | Host memory store / learner `memory_ref` |
| `skill_bundle_version` | string | Host skill store hash or registry component |
| `prompt_bundle_version` | string | Prompt template bundle id |
| `eval_run_id` | string | Baseline or triggering eval (holdout) |
| `learning_job_id` | string | Optional cross-link to `POST /learning/evolve` job |
| `components` | object | Extensible: `tool_manifest_version`, etc. |

**Rules:**

- Snapshot is **immutable** on the run record once `status` leaves `queued`.
- Trainer **does not** apply snapshot to checkpoints — it is metadata only (M4). Deployment still uses `candidate_model_id`.
- Adapter copies snapshot into `training_run_manifest.json` under `coaching_root`.

### 4.8 Hyperparameters (trainer-normalized)

| Key | Pipelines | Notes |
|-----|-----------|-------|
| `method` | sft | `full` \| `lora` \| `qlora` |
| `epochs` | sft, grpo | |
| `learning_rate` | all | |
| `lora_rank`, `lora_alpha` | sft | |
| `group_size` | grpo | Samples per prompt group |
| `num_iterations` | grpo | Outer RL iterations |
| `kl_coef` | grpo | KL to reference |
| `batch_size`, `gradient_accumulation` | all | |
| `seed` | all | Reproducibility |

Pipeline argv path (`POST /v1/pipelines/{id}/run`) accepts **CLI-style overrides** in `argv` that map to these keys server-side.

### 4.9 `POST /v1/pipelines/{pipeline_id}/run` — argv / log stream (operators)

Used by `modes/self-coaching/self-tuning/pipelines/*/run.sh`. Unchanged contract, extended semantics:

**Request:**

```json
{
  "argv": ["dataset.path=/data/train.jsonl", "scheduler.type=local", "rollout.config_ref=hermes-tool-use-v1"],
  "run_id": null,
  "link_to_agent": {"agent_id": "agent_abc"}
}
```

| Field | Notes |
|-------|-------|
| `argv` | Key=value or positional args interpreted by pipeline entrypoint |
| `run_id` | If set, attach log stream to existing structured run |
| `link_to_agent` | Optional lineage |

**Response (200):** `text/plain` training log (stdout+stderr). Headers:

- `X-Training-Run-Id: train_…` when a run record is created
- `Content-Type: text/plain; charset=utf-8`

**Errors:** **400** unsupported pipeline; **404** unknown `config_ref` in argv.

### 4.10 `GET /v1/pipelines` — list pipelines

**Response (200):**

```json
{
  "pipelines": [
    {
      "id": "sft",
      "title": "Supervised fine-tuning",
      "requires_rollout": false,
      "supported_reward_types": ["sft"]
    },
    {
      "id": "grpo",
      "title": "GRPO",
      "requires_rollout": true,
      "supported_reward_types": ["preference", "trajectory_reward"]
    }
  ]
}
```

### 4.11 `GET /health` — readiness probe

**Response (200):**

```json
{
  "status": "ok",
  "version": "0.2.0",
  "gpu_available": true,
  "queue_depth": 3,
  "active_runs": 1,
  "default_llm_proxy": "https://llm-proxy.internal/v1",
  "supported_pipelines": ["sft", "grpo"]
}
```

Returns **503** when worker pool or required proxy is unavailable.

### 4.12 Coaching facade `POST /training/runs` (adapter-facing)

The loop demo OpenAPI keeps a **thin** facade; the adapter expands to §4.1.

| Facade field | Trainer field |
|--------------|---------------|
| `pipeline` | `pipeline_id` |
| `dataset` | `dataset_refs: [dataset]` |
| `base_model` | `base_model` |
| (missing) | `agent_snapshot` from registry env |
| (missing) | `rollout` from `LOOP_TRAIN_ROLLOUT_CONFIG` when `pipeline=grpo` |

Facade response remains mock-compatible (`status`, `run_id`, `candidate`, `manifest`, `log_file`) — see §6.3.

---

### 4.13 `GET /v1/checkpoints` — list checkpoints (RestClient)

List durable **model checkpoints** (saved weights), optionally filtered by training run or base model.

**Query params:** `training_run_id`, `base_model`, `agent_id`, `since`, `limit` (default 50), `status` (`available` \| `archived`).

**Response (200):**

```json
{
  "checkpoints": [
    {
      "id": "ckpt-grpo-f7e2",
      "training_run_id": "train_2026-06-15T09-12-00_f7e2",
      "base_model": "org/base-agent-7b",
      "trainer": {"algorithm": "grpo", "method": "lora"},
      "step": 400,
      "epoch": 2,
      "metrics": {"val_loss": 0.31, "reward_mean": 0.72},
      "format": "safetensors",
      "size_bytes": 14200000000,
      "status": "available",
      "created_at": "2026-06-15T09:45:10Z"
    }
  ],
  "next_cursor": null
}
```

### 4.14 `GET /v1/checkpoints/{checkpoint_id}` — checkpoint detail + weights

**Response (200):**

```json
{
  "id": "ckpt-grpo-f7e2",
  "training_run_id": "train_2026-06-15T09-12-00_f7e2",
  "base_model": "org/base-agent-7b",
  "trainer": {"algorithm": "grpo", "pipeline_id": "grpo", "method": "lora"},
  "agent_snapshot": {
    "registry_version_id": "ver-prod-42",
    "skill_bundle_version": "skills-a1b2c3"
  },
  "metrics": {"val_loss": 0.31, "train_loss": 0.28},
  "weights": {
    "format": "safetensors",
    "uri": "s3://checkpoints/grpo-f7e2/model.safetensors",
    "shard_uris": [
      "s3://checkpoints/grpo-f7e2/model-00001-of-00002.safetensors",
      "s3://checkpoints/grpo-f7e2/model-00002-of-00002.safetensors"
    ],
    "shard_count": 2,
    "size_bytes": 14200000000,
    "tokenizer_uri": "s3://checkpoints/grpo-f7e2/tokenizer.json",
    "adapter_only": true,
    "merged": false
  },
  "config_uri": "s3://checkpoints/grpo-f7e2/training_config.yaml",
  "related_process_ids": ["proc-merge-f7e2"],
  "served_model_id": null,
  "status": "available",
  "created_at": "2026-06-15T09:45:10Z"
}
```

| Field | Meaning |
|-------|---------|
| `weights.uri` | Primary weight blob or index |
| `weights.shard_uris` | Multi-file checkpoints (large models) |
| `weights.adapter_only` | `true` when only LoRA adapters, not full weights |
| `weights.merged` | `true` after merge process produced full weights |
| `related_process_ids` | Side jobs (export, merge, quantize) — §4.16 |
| `served_model_id` | Set when checkpoint is registered for inference |

**Errors:** **404** `checkpoint_not_found`

### 4.15 `GET /v1/models` — list served / registered models (RestClient)

Models **ready for inference** (may reference one or more checkpoints).

**Query params:** `agent_id`, `base_model`, `limit`.

**Response (200):**

```json
{
  "models": [
    {
      "id": "model-candidate-f7e2",
      "checkpoint_id": "ckpt-grpo-f7e2",
      "training_run_id": "train_2026-06-15T09-12-00_f7e2",
      "base_model": "org/base-agent-7b",
      "endpoint": "https://infer.internal/v1/models/candidate-f7e2",
      "status": "ready",
      "created_at": "2026-06-15T09:46:00Z"
    }
  ]
}
```

**`GET /v1/models/{model_id}`** returns the same object plus `weights` summary (delegates to linked checkpoint).

### 4.16 `GET /v1/processes` — related async processes (RestClient)

Side jobs spawned from training or checkpoint management: **merge** (LoRA into base), **export** (GGUF/ONNX), **quantize**, **upload**, **eval-bake**.

**Query params:** `training_run_id`, `checkpoint_id`, `type`, `status`.

**Response (200):**

```json
{
  "processes": [
    {
      "id": "proc-merge-f7e2",
      "type": "merge",
      "status": "succeeded",
      "training_run_id": "train_2026-06-15T09-12-00_f7e2",
      "checkpoint_id": "ckpt-grpo-f7e2",
      "input_checkpoint_ids": ["ckpt-grpo-f7e2"],
      "output_checkpoint_id": "ckpt-grpo-f7e2-merged",
      "created_at": "2026-06-15T09:45:30Z",
      "finished_at": "2026-06-15T09:47:00Z"
    }
  ]
}
```

**`GET /v1/processes/{process_id}`** — full detail + `error` on failure.

**`POST /v1/processes`** (optional, ops) — enqueue merge/export:

```json
{
  "type": "merge",
  "checkpoint_id": "ckpt-grpo-f7e2",
  "options": {"dtype": "bf16"}
}
```

Returns **202** + `process_id` for poll via RestClient.

---

## 5. Input model — datasets vs coaching root

| Source | API / store | Used by |
|--------|-------------|---------|
| **Curated train split** | `dataset_refs` or default `{coaching_root}/.self-coaching/curated/train.jsonl` | T-path export, coach curation |
| **Preference / RL pool** | `pref_train.jsonl`, `trajectory_reward` records | GRPO |
| **Reward validation** | `POST /v1/rewards/validate` | Preflight before long runs |
| **Rollout preflight** | `POST /v1/rollout/configs/validate` | GRPO staging smoke |
| **Checkpoint lookup** | RestClient `GET /v1/checkpoints?training_run_id=` | After train succeeds; eval + manifest |
| **Weight audit** | RestClient `GET /v1/checkpoints/{id}` | Ops, promotion gate |

**Loop demo:** `loop_store.export_train_dataset()` writes JSONL under `coaching_root`; adapter passes absolute path in `dataset_refs`. Production trainer must accept **file**, **s3**, **https** URIs per deployment policy.

---

## 6. Output contract — production API → loop `train()` result

Production **TrainingClient** returns `TrainingRunRecord` (§4.2.1) — **not** the thin coaching shape. **RestClient** supplies checkpoint/weight detail. The **adapter** normalizes both into the loop contract:

```python
# loop_driver.run_t_path (unchanged)
train_result = client.train(pipeline=pipeline, dataset=str(dataset_path), base_model=base_model)
trained_model = str(train_result.get("candidate") or train_result.get("candidate_model_id"))
```

### 6.1 TrainingClient result shape (source of truth)

| Field | When present | Meaning |
|-------|--------------|---------|
| `training_run_id` / `id` | always | Run identifier |
| `status` | always | Job lifecycle state |
| `trainer` | always | Algorithm + method (§4.2.2) |
| `base_model` | always | Starting model |
| `training_data` | always | Dataset refs + counts (§4.2.3) |
| `pipeline_config` | always | Hyperparameters, rollout, reward (§4.2.4) |
| `metrics` / `metrics_partial` | terminal / running | `train_loss`, `val_loss`, `reward_mean`, … |
| `primary_checkpoint_id` | succeeded | Link to RestClient |
| `candidate_model_id` | succeeded | Adapter alias of `primary_checkpoint_id` |
| `candidate_endpoint` | optional | If model already served |
| `agent_snapshot` | optional | Lineage pin |
| `rollout_summary` | GRPO | Token accounting |
| `error` | failed | Structured failure |

### 6.1b RestClient result shape (checkpoints & weights)

| Field | When present | Meaning |
|-------|--------------|---------|
| `id` | checkpoint | Checkpoint id (`ckpt-…`) |
| `training_run_id` | always | Producing run |
| `weights.uri` / `weights.shard_uris` | available | Durable weight locations |
| `weights.format` | always | `safetensors`, `pytorch`, `gguf`, … |
| `weights.adapter_only` | LoRA runs | Adapters vs full model |
| `related_process_ids` | optional | Merge/export jobs |
| `served_model_id` | when deployed | Inference registry id |

**Adapter rule:** If terminal run has `primary_checkpoint_id` but no inline weights, adapter calls `RestClient.get_checkpoint(primary_checkpoint_id)` before writing manifest.

### 6.2 Adapter mapping rules (proposed)

| Condition | Local registry action (M4) |
|-----------|----------------------------|
| `status == succeeded` | `create_version` with `components.model_id = candidate_model_id`; parent = `agent_snapshot.registry_version_id` or current active |
| `status == failed` | No draft; propagate `AERLError` to loop / orchestrator |
| `dry_run: true` | No registry write; return validation summary only |
| GRPO without holdout eval | Draft created but loop still runs holdout gate before `activate` |

**Manifest:** Adapter writes `coaching_root/.self-coaching/manifests/training_run_manifest.json`:

```json
{
  "run_id": "train_2026-06-15T09-12-00_f7e2",
  "timestamp": "2026-06-15T09:45:10Z",
  "pipeline_id": "grpo",
  "dataset_refs": ["…"],
  "base_model": "org/base-agent-7b",
  "candidate": "checkpoint/grpo-f7e2",
  "candidate_model_id": "checkpoint/grpo-f7e2",
  "method": "grpo",
  "hyperparameters": {"group_size": 8, "kl_coef": 0.02},
  "agent_snapshot": {
    "registry_version_id": "ver-prod-42",
    "memory_version": "mem-2026-06-10T12:00:00Z",
    "skill_bundle_version": "skills-a1b2c3"
  },
  "rollout_summary": {"total_tokens": {"input": 2400000, "output": 890000}},
  "metrics": {"val_loss": 0.31, "reward_mean": 0.72},
  "eval_run_id": null,
  "rollback_target": "org/base-agent-7b",
  "log_file": "/path/to/local/train.log",
  "registry_version_id": "ver-draft-88"
}
```

### 6.3 Normalized `train()` response (adapter output)

```json
{
  "status": "trained",
  "run_id": "train_2026-06-15T09-12-00_f7e2",
  "candidate": "checkpoint/grpo-f7e2",
  "candidate_model_id": "checkpoint/grpo-f7e2",
  "manifest": "/coaching/.self-coaching/manifests/training_run_manifest.json",
  "log_file": "/coaching/.self-coaching/logs/train_f7e2.log",
  "registry_version_id": "ver-draft-88",
  "metrics": {"val_loss": 0.31, "reward_mean": 0.72},
  "_train_backend": "aerl"
}
```

### 6.4 Coaching OpenAPI `TrainingResponse` mapping

| Trainer (terminal) | Coaching facade |
|--------------------|-----------------|
| `status: succeeded` | `status: trained` |
| `status: queued` (async facade) | `status: accepted` |
| `candidate_model_id` | `candidate` |
| local manifest path | `manifest` |
| local or `artifacts.log_uri` | `log_file` |

---

## 7. Client & adapter plan

### 7.1 Two Python clients (repo modules)

| Client class | Module | Methods (representative) |
|--------------|--------|--------------------------|
| **`TrainingClient`** | `services/adapters/training_client.py` | `create_run`, `get_run`, `wait_for_run`, `cancel_run`, `list_runs`, `get_metrics`, `validate_rollout`, `validate_rewards`, `run_pipeline_argv`, `list_pipelines`, `health` |
| **`RestClient`** | `services/adapters/trainer_rest_client.py` | `list_checkpoints`, `get_checkpoint`, `list_models`, `get_model`, `list_processes`, `get_process`, `create_process` (optional) |

**Migration note:** Today's `AERLClient` in `aerl_client.py` is a **TrainingClient** subset. M4 splits or re-exports:

```python
# training_client.py — job lifecycle
class TrainingClient:
    def get_run(self, training_run_id: str) -> TrainingRunRecord: ...
    def get_metrics(self, training_run_id: str, *, series: list[str] | None = None) -> dict: ...

# trainer_rest_client.py — artifacts
class RestClient:
    def list_checkpoints(self, *, training_run_id: str | None = None, ...) -> list[Checkpoint]: ...
    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint: ...
    def get_weights(self, checkpoint_id: str) -> WeightsManifest: ...  # shortcut to .weights
```

Both clients share `TRAINER_BASE_URL` + `TRAINER_API_KEY`. `train_adapter.py` composes **TrainingClient** (required) + **RestClient** (on success).

### 7.2 Other modules

| Module | Responsibility |
|--------|----------------|
| `services/adapters/train_adapter.py` | `train()` → TrainingClient + RestClient → mapping |
| `services/adapters/train_mapping.py` | `TrainingRunRecord` + `Checkpoint` → `train()` dict + manifest |
| `services/adapters/aerl_client.py` | **Deprecated alias** → thin wrapper over `TrainingClient` (M4.2) |
| `docs/integration/mapping.md` | § Self-tuning TrainingClient + RestClient fields |
| `docs/integration/api-snapshots/aerl-openapi.json` | Export from production trainer (both path groups) |

### 7.3 `train()` behavior by mode

| `ORCHESTRATOR_TRAIN_BACKEND` | Backend | Behavior |
|------------------------------|---------|----------|
| `mock` (default) | In-process `mock_aerl` | Today's deterministic engine |
| `aerl` | Production trainer §4.1–4.3 | TrainingClient async create + poll; RestClient on success |

**T-path adapter flow (`ORCHESTRATOR_TRAIN_BACKEND=aerl`):**

```text
train(pipeline, dataset, base_model)
  → TrainingClient.create_run({ pipeline_id, base_model, dataset_refs,
       agent_snapshot, rollout?, reward_spec?, wait })
  → TrainingClient.wait_for_run(training_run_id) until terminal
  → if succeeded and primary_checkpoint_id:
       RestClient.get_checkpoint(primary_checkpoint_id)  # weights URIs for manifest
  → train_mapping → training_run_manifest.json + { candidate, metrics, trainer, training_data }
  → return normalized dict
```

### 7.4 Environment variables (proposed)

Add to `scenarios/demo.env.example` when implementing M4:

| Variable | Default (mock) | Live |
|----------|----------------|------|
| `TRAINER_BASE_URL` | unset | Trainer service URL |
| `MOCK_AERL_URL` | unset | Alias for mock HTTP stack |
| `TRAINER_API_KEY` | optional | Bearer for staging |
| `ORCHESTRATOR_TRAIN_BACKEND` | `mock` | `aerl` |
| `AERL_TIMEOUT_S` | `3600` | Poll budget (long GRPO jobs) |
| `AERL_POLL_INTERVAL_S` | `2` | Poll interval |
| `LOOP_TRAIN_WAIT` | `true` | Block in adapter |
| `LOOP_TRAIN_ROLLOUT_CONFIG` | unset | Path to JSON or `config_ref` for GRPO |
| `LOOP_TRAIN_REWARD_SPEC` | unset | Path to JSON `reward_spec` override |
| `LOOP_TRAIN_AGENT_SNAPSHOT` | `true` | Attach registry/memory/skill versions |
| `OPENAI_BASE_URL` | — | **Script-only** default for `run-pipeline.sh` (§ST-R6) |
| `OPENAI_API_KEY` | — | Script-only; production uses `rollout.llm_proxy` on API |

Wire in `modes/self-coaching/loop_env.py` alongside eval/learn knobs.

---

## 8. Mock implementation plan

Extend `mock-services/mock_aerl.py` to **mirror production routes** (deterministic shims):

| Endpoint | Mock behavior |
|----------|---------------|
| **TrainingClient** | |
| `POST /v1/training/runs` | Accept `rollout`, `reward_spec`, `agent_snapshot`; echo `trainer`, `training_data`, `pipeline_config` on GET |
| `GET /v1/training/runs/{id}` | Phases + `TrainingRunRecord` shape; `primary_checkpoint_id` on success |
| `GET /v1/training/runs/{id}/metrics` | Synthetic loss series |
| `POST /v1/training/runs/{id}/cancel` | Flip to `cancelled` if not terminal |
| `GET /v1/training/runs` | Filter fixture list |
| `POST /v1/pipelines/{id}/run` | **Unchanged** argv log + `X-Training-Run-Id` |
| `GET /v1/pipelines` | Return `sft`, `grpo` metadata |
| `POST /v1/rollout/configs/validate` | Always `valid: true` unless `base_url` contains `invalid` |
| `POST /v1/rewards/validate` | Count record types from JSONL |
| `GET /v1/rewards/schema` | Return `reward.ic.v1` |
| **RestClient** | |
| `GET /v1/checkpoints` | Filter by `training_run_id`; deterministic ids |
| `GET /v1/checkpoints/{id}` | Weights block with `shard_uris`, `adapter_only` stub |
| `GET /v1/models` | Optional served model when run succeeds |
| `GET /v1/processes` | Empty or fixture merge job |
| `GET /health` | Always 200; optional 503 test hook |

**CI:** `LOOP_SERVICE_MODE=mock-module` keeps in-process engine. Production-shaped routes tested via `mock-http` or `MOCK_AERL_URL`.

**Determinism:** Mock worker completes in &lt;200ms; `val_loss` / `reward_mean` derived from dataset record count (same as today).

---

## 9. Integration with host platforms

### 9.1 Hermes / AERL cluster

| Concern | Integration |
|---------|-------------|
| GRPO rollouts | Register `rollout.config_ref` pointing at org LLM proxy |
| Checkpoint serving | `candidate_endpoint` → AgentEvals `agent_config.model` for holdout |
| Lineage | `agent_snapshot.skill_bundle_version` matches host skill store |

### 9.2 Self-coaching loop demo

| Concern | Integration |
|---------|-------------|
| Default CI | `ORCHESTRATOR_TRAIN_BACKEND=mock` — no GPU |
| Live T-path | `train_adapter` + `AERL_TIMEOUT_S` + optional `LOOP_TRAIN_ROLLOUT_CONFIG` |
| Holdout gate | Unchanged after train — `run_t_path` still calls AgentEvals |

### 9.3 Coach mode

| Concern | Integration |
|---------|-------------|
| Model path | Orchestrator `improvement_path: model` → full §4.1 body with eval-triggered `agent_snapshot.eval_run_id` |
| Preflight | `POST /v1/rewards/validate` + `POST /v1/rollout/configs/validate` before queue |

### 9.4 Self-learning cross-link (M2)

When a training run follows a learning job:

1. Adapter sets `agent_snapshot.learning_job_id` from `learn()` response `job_id`.
2. Optionally query learner for post-review `memory_version` / `skill_bundle_version` if host exposes them on `GET /learning/status/{job_id}` completed payload.
3. Trainer stores snapshot immutably; does not re-fetch learner state at completion.

---

## 10. Migration phases (M4)

| Step | Deliverable | Exit |
|------|-------------|------|
| **M4.0** | This spec approved; OpenAPI draft + `aerl-openapi.json` placeholder | Review sign-off |
| **M4.1** | Mock production routes (§8) + fixtures | Unit tests green |
| **M4.2** | `training_client.py` + `trainer_rest_client.py` + `train_mapping.py` | Replay test from fixture |
| **M4.3** | `loop_env.py` env wiring; GRPO rollout config | T-path test with mock HTTP |
| **M4.4** | Staging smoke: real trainer + proxy validate | `full_loop_live` T-path rows pass |
| **M4.5** | R5 mock-module regression | Golden unchanged |

**Dependency:** M1 holdout eval PASS. **Parallel:** M2 learner snapshot fields can land before M4 adapter reads them.

---

## 11. Implementation task lists

### 11.0 Master tracker

| Phase | Summary | Status | Depends on |
|-------|---------|--------|------------|
| **M4.0** | Spec + contract freeze | **in progress** (this doc) | — |
| **M4.1** | Mock services (production routes) | not started | M4.0 |
| **M4.2** | HTTP client + train mapping | not started | M4.1 |
| **M4.3** | Loop env + facade wiring | not started | M4.2 |
| **M4.4** | Staging smoke + live T-path | not started | M4.3, M1 |
| **M4.5** | R5 mock-module regression | not started | M4.3 |

### 11.1 M4.0 — Spec & contract freeze

| ID | Task | File(s) | Done |
|----|------|---------|------|
| M4.0-T01 | Resolve open questions §14 | this doc §14 | [ ] |
| M4.0-T02 | Extend Coaching OpenAPI `TrainingRequest` with optional snapshot + rollout refs | `mock-services/contracts/openapi.yaml` | [ ] |
| M4.0-T03 | Placeholder `aerl-openapi.json` snapshot | `docs/integration/api-snapshots/aerl-openapi.json` | [ ] |
| M4.0-T04 | Link spec from migration + integration plan | `mock-to-real-migration.md`, `integration-plan.md` | [ ] |

### 11.2 M4.1 — Mock trainer (production-shaped HTTP)

| ID | Task | Done |
|----|------|------|
| M4.1-T01 | `agent_snapshot`, `rollout`, `reward_spec` on create | [ ] |
| M4.1-T02 | `grpo` without rollout → 400 | [ ] |
| M4.1-T03 | `GET /v1/pipelines`, rollout/reward validate routes | [ ] |
| M4.1-T04 | Cancel + list runs | [ ] |
| M4.1-T05 | RestClient routes: checkpoints, models, processes | [ ] |
| M4.1-T06 | Fixtures under `tests/fixtures/aerl/` | [ ] |

---

## 12. Testing strategy

| Test | Purpose |
|------|---------|
| `tests/test_aerl_mock_extended.py` | Rollout required, snapshot echo, reward validate |
| `tests/test_train_adapter.py` | Fixture replay → manifest + `candidate` |
| `tests/test_loop_t_path.py` | T-path with `MOCK_AERL_URL` |
| `scripts/aerl_live_smoke.py` (new) | health → validate rollout → create run → poll |

**Fixtures (to add):**

- `tests/fixtures/aerl/run_create_grpo_queued.json`
- `tests/fixtures/aerl/run_completed_grpo.json`
- `tests/fixtures/aerl/reward_validate_ok.json`
- `tests/fixtures/aerl/rollout_validate_ok.json`

---

## 13. Non-goals (M4)

- Implementing the LLM proxy itself (trainer **consumes** a proxy; infra team owns gateway).
- Embedding AERL training scripts in this repo (trainer worker owns execution).
- Replacing local `mock_agent_registry` with production agent API (M5).
- Automatic promotion after train (holdout gate remains in loop / orchestrator).
- DPO/ORPO pipelines until trainer advertises them on `GET /v1/pipelines`.

---

## 14. Open questions (edit in review)

| # | Question | Options | Decision |
|---|----------|---------|----------|
| Q1 | Inline `api_key` vs `api_key_ref` only | Allow inline for dev; staging+ ref-only | _Recommend ref-only on staging_ |
| Q2 | Who writes `training_run_manifest.json` | Adapter (M4) vs trainer push to coaching_root | _Recommend adapter + local path_ |
| Q3 | `candidate` vs `candidate_endpoint` for eval | Eval adapter uses endpoint when set | _TBD_ |
| Q4 | Learner snapshot source | Env-only vs query learner `GET /learning/status` | _Recommend env + optional learner enrich_ |
| Q5 | argv run linked to structured `run_id` | Always create run record vs log-only | _Recommend always create for audit_ |
| Q6 | OpenAPI ownership | Separate `aerl-openapi.json` vs Coaching API only | _Recommend separate snapshot_ |
| Q7 | Reward schema versioning | Single `reward.ic.v1` vs per-pipeline | _Start with v1; bump on breaking change_ |
| Q8 | Proxy model hot-swap | Trainer pushes routes vs proxy polls checkpoint watcher | _Trainer-owned (§4.5.2)_ |
| Q9 | RestClient vs agent API | Checkpoints on trainer vs production `GET /api/agents/…/versions` | _Trainer RestClient for weights; agent API for deploy (M5)_ |
| Q10 | `candidate_model_id` naming | Keep adapter alias vs rename to `checkpoint_id` only | _Keep alias through M4; deprecate in M5_ |

---

## 15. Related commands (future)

| Today (mock) | Staging (real trainer) |
|--------------|------------------------|
| `python -m mock_aerl run --pipeline sft` | `curl -X POST …/v1/training/runs -d '{…}'` |
| `MOCK_AERL_URL=…` + loop demo | `ORCHESTRATOR_TRAIN_BACKEND=aerl TRAINER_BASE_URL=…` |
| `bash scripts/run-pipeline.sh grpo …` | Same; ensure `rollout.config_ref` in argv or env JSON |
| — | `curl …/v1/rollout/configs/validate` (preflight) |
| — | `curl …/v1/training/runs/{id}/metrics` (loss series) |
| — | `curl …/v1/checkpoints?training_run_id=…` (RestClient) |
| — | `curl …/v1/checkpoints/{id}` (weights / shards) |

---

## 16. Document history

| Date | Change |
|------|--------|
| 2026-06-15 | Initial DRAFT: production trainer API (runs, rollout/LLM proxy, reward.ic.v1, agent_snapshot); M4 task list |
| 2026-06-15 | §3.2 TrainingClient vs RestClient; `TrainingRunRecord`; checkpoint/model/process APIs (§4.13–4.16) |

---

*Edit this file freely. Implement **§11** task lists in order M4.0 → M4.5; check `[x]` as tasks land.*
