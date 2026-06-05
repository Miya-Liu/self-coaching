# AERL integration

**AERL** is the training backend for the **model path** in [pipelines.md](../pipelines.md): SFT and GRPO-style runs over curated data from learn / self-play / curation.

Skill-mode worktree training (`AUTORESEARCH_ROOT`, `run-once.sh`) is a separate path for autoresearch-style experiments.

## Repo layout

| Path | Role |
|------|------|
| `modes/skill/self-tuning/pipelines/registry.yaml` | Pipeline registry |
| `modes/skill/self-tuning/pipelines/sft/` | SFT pipeline |
| `modes/skill/self-tuning/pipelines/grpo/` | GRPO pipeline |
| `modes/skill/self-tuning/pipelines/_lib.sh` | HTTP vs local mode |
| `modes/skill/self-tuning/services/example.env` | Credentials template → `.env` |

Operators (repo root): `bash scripts/run-pipeline.sh <sft|grpo> logs/<id>.log`

## HTTP contract

Default trainer: `TRAINER_BASE_URL` (registry default `http://localhost:8004`).

```
POST /v1/pipelines/{sft|grpo}/run
```

Coaching API maps `POST /training/runs` → AERL adapter (M2).

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
| `modes/skill/self-tuning/services/.env` | API keys (gitignored) |

## Related

- [coaching_api.md](coaching_api.md) — `POST /training/runs`
- [pipelines.md](../pipelines.md) — model vs skill path routing
- [skill_mode.md](../skill_mode.md) — worktree / autoresearch path
