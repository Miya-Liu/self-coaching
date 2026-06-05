# Runbook

From the **repository root** (directory containing `modes/`, `scripts/`, `services/`). Bash required; **uv** only for external autoresearch training.

**Self-coaching mode (T1):** [deploy-skill-pack.md](deploy-skill-pack.md) or `bash scripts/install-skill-pack.sh . --with-mock`. **Coach mode:** [deploy-overview.md#coach-mode](deploy-overview.md#coach-mode). Design: [architecture.md](../design/architecture.md).

## One-time: dependencies and data

1. `bash scripts/install-skill-pack.sh .` (or `init-experience.sh` + `doctor.sh`).
2. **Autoresearch worktrees:** set `AUTORESEARCH_ROOT` ([upstream/README.md](../../upstream/README.md)), install [uv](https://docs.astral.sh/uv/), then `bash scripts/preflight.sh`.
3. If needed: `uv --directory "$AUTORESEARCH_ROOT" run prepare.py`.

## Per experiment: worktree

See `modes/self-coaching/SKILL.md` — `git worktree add` into `worktrees/<id>/` under the coaching root.

## Run training (log to file)

```bash
bash scripts/run-once.sh "worktrees/<id>" "logs/<id>.log"
```

## Training pipelines (SFT / GRPO, AERL)

1. Copy `modes/self-coaching/self-tuning/services/example.env` to `modes/self-coaching/self-tuning/services/.env`; set `TRAINER_BASE_URL` (default `http://localhost:8004` in `registry.yaml`).
2. Implement `POST /v1/pipelines/{sft|grpo}/run` on your trainer, or `PIPELINE_MODE=local` + `AERL_ROOT` (see `modes/self-coaching/self-tuning/pipelines/_lib.sh`).
3. `bash scripts/run-pipeline.sh grpo logs/exp-01-grpo.log`

## Experience logs

Summaries in `experience/`; full train output in `logs/<id>.log` only.

## Merge after approval

See `modes/self-coaching/SKILL.md` (`git checkout main`, `git merge`, optional `worktree remove`).
