# AERL integration

**AERL** is the training backend for the **model path** in [pipelines.md](../pipelines.md): SFT and GRPO-style runs over curated data from learn / self-questioning / curation.

**Production path (2026-06):** Real GPU training on the AReaL host uses **CLI + db_bridge remote shell**, not HTTP. Set `ORCHESTRATOR_TRAIN_BACKEND=cli`. See [cli-training-implementation.md](../../project/cli-training-implementation.md) and [db_bridge_remote_shell.md](db_bridge_remote_shell.md).

The HTTP trainer path below remains for **mock-http CI** and optional future HTTP services (`ORCHESTRATOR_TRAIN_BACKEND=aerl`).

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

**Production spec (DRAFT):** [self-tuning-trainer-api-plan.md](../../project/self-tuning-trainer-api-plan.md) — **TrainerClient** (runs, config, loss) and **RestClient** (checkpoints, weights, processes); rollout proxy, `reward.ic.v1`, `agent_snapshot`.

| Client | Endpoints | Repo module (M4) |
|--------|-----------|------------------|
| **TrainerClient** | `POST/GET /v1/training/runs`, metrics, pipelines, rollout/reward validate | `services/adapters/trainer_client.py` |
| **RestClient** | `GET /v1/checkpoints`, `/v1/models`, `/v1/processes` | `services/adapters/trainer_rest_client.py` |

Coaching facade maps `POST /training/runs` → adapter → `POST /v1/training/runs` (`ORCHESTRATOR_TRAIN_BACKEND=aerl`).

Local mock: `mock-services/mock_aerl.py` on `:8004` (`MOCK_AERL_URL` / `TRAINER_BASE_URL`).

**Loop wiring (M4.3):** `mock-http` mode sets `ORCHESTRATOR_TRAIN_BACKEND=aerl` and `build_loop_client()` composes `TrainerClient` + `RestClient` from `LoopConfig.aerl_url`. See `modes/self-coaching/loop_env.py`.

## CLI production path (db_bridge)

| Item | Detail |
|------|--------|
| Backend flag | `ORCHESTRATOR_TRAIN_BACKEND=cli` |
| Transport | Supabase `areal_remote_commands` → `run_shell_runner` on AReaL host |
| Adapter | `services/adapters/cli_train_adapter.py` |
| Env template | `scenarios/demo.cli-train.env.example` |
| Smoke | `python scripts/cli_train_smoke.py --env-file scenarios/demo.cli-train.env --probe` |
| AReaL marker | [areal_cli_training_request.md](areal_cli_training_request.md) — `TRAINING_COMPLETE` stdout line |

Live mode infers `cli` when `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` + `BRIDGE_USER_ID` are set and no `TRAINER_BASE_URL` is configured.

## Local fallback

```bash
export PIPELINE_MODE=local
export AERL_ROOT=/path/to/AERL
```

## Configuration

| Variable | Purpose |
|----------|---------|
| `TRAINER_BASE_URL` | AERL HTTP endpoint (mock-http / legacy) |
| `ORCHESTRATOR_TRAIN_BACKEND` | `mock` \| `aerl` \| `cli` |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `BRIDGE_USER_ID` | CLI train via db_bridge |
| `CLI_TRAIN_CWD` / `CLI_TRAIN_CONFIG` / `CLI_TRAIN_SCRIPT` | Remote training command (CLI path) |
| `AERL_ROOT` | Local trainer tree |
| `PIPELINE_MODE` | `http` (default) \| `local` |
| `modes/self-coaching/self-tuning/services/.env` | API keys (gitignored) |

## Related

- [cli-training-implementation.md](../../project/cli-training-implementation.md) — CLI train tracker
- [self-tuning-trainer-api-plan.md](../../project/self-tuning-trainer-api-plan.md) — HTTP trainer API (mock CI)
- [db_bridge_remote_shell.md](db_bridge_remote_shell.md) — remote shell ops
- [areal_cli_training_request.md](areal_cli_training_request.md) — AReaL stdout marker request
- [coaching_api.md](coaching_api.md) — `POST /training/runs`
- [pipelines.md](../pipelines.md) — model vs skill path routing
