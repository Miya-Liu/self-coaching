# AERL integration

**AERL** is the training backend for the **model path** in [pipelines.md](../pipelines.md): SFT and GRPO-style runs over curated data from learn / self-play / curation.

## Repo layout

| Path | Role |
|------|------|
| `modes/self-coaching/self-tuning/pipelines/registry.yaml` | Pipeline registry |
| `modes/self-coaching/self-tuning/pipelines/sft/` | SFT pipeline |
| `modes/self-coaching/self-tuning/pipelines/grpo/` | GRPO pipeline |
| `modes/self-coaching/self-tuning/pipelines/_lib.sh` | HTTP vs local mode |
| `modes/self-coaching/self-tuning/services/example.env` | Credentials template → `.env` |

Operators (repo root): `bash scripts/run-pipeline.sh <sft|grpo> logs/<id>.log`

## HTTP contract

Default trainer: `TRAINER_BASE_URL` (registry default `http://localhost:8004`).

**Production spec (DRAFT):** [self-tuning-trainer-api-plan.md](../../project/self-tuning-trainer-api-plan.md) — **TrainingClient** (runs, config, loss) and **RestClient** (checkpoints, weights, processes); rollout proxy, `reward.ic.v1`, `agent_snapshot`.

| Client | Endpoints | Repo module (M4) |
|--------|-----------|------------------|
| **TrainingClient** | `POST/GET /v1/training/runs`, metrics, pipelines, rollout/reward validate | `training_client.py` |
| **RestClient** | `GET /v1/checkpoints`, `/v1/models`, `/v1/processes` | `trainer_rest_client.py` |

Coaching facade maps `POST /training/runs` → adapter → `POST /v1/training/runs` (`ORCHESTRATOR_TRAIN_BACKEND=aerl`).

Local mock: `mock-services/mock_aerl.py` on `:8004` (`MOCK_AERL_URL` / `TRAINER_BASE_URL`).

## Local fallback

```bash
export PIPELINE_MODE=local
export AERL_ROOT=/path/to/AERL
```

## Configuration

| Variable | Purpose |
|----------|---------|
| `TRAINER_BASE_URL` | AERL HTTP endpoint |
| `AERL_ROOT` | Local trainer tree |
| `PIPELINE_MODE` | `http` (default) \| `local` |
| `modes/self-coaching/self-tuning/services/.env` | API keys (gitignored) |

## Related

- [self-tuning-trainer-api-plan.md](../../project/self-tuning-trainer-api-plan.md) — full trainer API (M4)
- [coaching_api.md](coaching_api.md) — `POST /training/runs`
- [pipelines.md](../pipelines.md) — model vs skill path routing
