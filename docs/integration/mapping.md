# AgentEvals → EvalMetrics mapping

Operational field mapping for adapter fixtures and smoke tests. **Design:** [design/integrations/agentevals.md](../design/integrations/agentevals.md). **Plan:** [integration-plan.md](../project/integration-plan.md).

Confirmed against mock fixture `tests/fixtures/agentevals/run_detail_succeeded.json` and live MemoryArena capture `tests/fixtures/agentevals/run_detail_memoryarena_succeeded.json` (2026-06-10, `localhost:8080`).

**Coach mode:** each **subject agent** has a **coaching root**; `record-eval` appends to `{coaching_root}/.self-coaching/metrics/eval_metrics.jsonl`. See [coach_mode.md](../design/coach_mode.md).

## API surface (AgentEvals)

| Orchestrator need | AgentEvals endpoint | Notes |
|-------------------|----------------------|--------|
| Start eval | `POST /api/runs` | Body: `suite_id`, `agent_config`, optional `num_trials` |
| Poll / report | `GET /api/runs/{run_id}` | Terminal: `succeeded` \| `failed` |
| Suite pick | `GET /api/suites` | Set `AGENTEVALS_SUITE_ID` / `AGENTEVALS_SUITE_ID_HOLDOUT` |

## `RunDetail` → `EvalMetrics`

| `EvalMetrics` field | Source (priority order) |
|---------------------|-------------------------|
| `run_id` | `id` |
| `agent_id` | `agent_config.agent_id` or CLI `--agent-id` |
| `model_checkpoint_id` | `agent_config.version_id` or orchestrator `--candidate` |
| `skill_bundle_version` | CLI `--skill-bundle-version` (not on RunDetail) |
| `score` | `metrics.overall` → `metrics.pass_rate` → mean of numeric `metrics` values |
| `baseline_score` | CLI override; else prior canary row; else `score` |
| `task_scores` | All numeric `metrics` keys except reserved (`overall`, `pass_rate`, `safety`, `cost_usd`, `latency_p95_ms`) |
| `safety_pass_rate` | `metrics.safety` (default `1.0`) |
| `cost_per_task` | `metrics.cost_usd` / `num_trials` (or `1`) |
| `latency_p95_ms` | `metrics.latency_p95_ms` |
| `split` | CLI `--split` (`canary` \| `holdout`) |
| `raw` | Full `RunDetail` JSON |

## Mock-compatible report (adapter internal)

`services/adapters/eval_adapter.py` builds a report shaped like the mock Coaching API so `normalize_from_mock_eval()` can be reused when `ORCHESTRATOR_EVAL_BACKEND=agentevals`. Prefer `normalize_from_agentevals()` in the orchestrator when the backend flag is `agentevals`.

## Configuration IDs (staging — fill when services are up)

| Variable | Purpose | Example |
|----------|---------|---------|
| `AGENT_ID` | Production agent UUID | `550e8400-e29b-41d4-a716-446655440000` |
| `AGENTEVALS_SUITE_ID` | Canary / `record-eval` | from `GET /api/suites` |
| `AGENTEVALS_SUITE_ID_HOLDOUT` | Candidate gate in `run` | separate suite |
| `--candidate` / `--baseline` | Maps to `agent_config.version_id` | version ids, not mock strings |

## Smoke checklist

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/api/suites
bash scripts/export-integration-snapshots.sh
# Capture: GET /api/runs/{id} succeeded → tests/fixtures/agentevals/run_detail_succeeded.json
```

---

## Trainer → `train()` result (M4.2)

Operational mapping for `AERLTrainAdapter` / `train_mapping.py`. **Spec:** [self-tuning-trainer-api-plan.md](../project/self-tuning-trainer-api-plan.md).

### API surface (trainer)

| Loop need | Trainer endpoint | Client |
|-----------|------------------|--------|
| Start train | `POST /v1/training/runs` | `TrainingClient.create_run` |
| Poll run | `GET /v1/training/runs/{id}` | `TrainingClient.get_run` / `wait_for_run` |
| Resolve weights | `GET /v1/checkpoints/{id}` | `RestClient.get_checkpoint` |
| Preflight rewards | `POST /v1/rewards/validate` | `TrainingClient.validate_rewards` |
| Preflight rollout | `POST /v1/rollout/configs/validate` | `TrainingClient.validate_rollout` |

### `TrainingRunRecord` + `Checkpoint` → normalized `train()`

| `train()` field | Source (priority order) |
|-----------------|-------------------------|
| `run_id` | `run.id` / `run.training_run_id` |
| `candidate` / `candidate_model_id` | `run.candidate_model_id` → `checkpoint.id` → `run.primary_checkpoint_id` |
| `primary_checkpoint_id` | `run.primary_checkpoint_id` → `checkpoint.id` |
| `weights_uri` | `checkpoint.weights.uri` |
| `manifest` | `{coaching_root}/.self-coaching/manifests/training_run_manifest.json` if file exists |
| `log_file` | `run.log_file` |
| `registry_version_id` | `run.registry_version_id` (mock writes via registry draft) |
| `metrics` | `run.metrics` |
| `trainer` | `run.trainer` |
| `training_data` | `run.training_data` |
| `agent_snapshot` | `run.agent_snapshot` |
| `rollout_summary` | `run.rollout_summary` (GRPO) |
| `_train_backend` | always `"aerl"` |

Fixtures: `tests/fixtures/aerl/run_completed_sft.json`, `checkpoint_sft.json`.
