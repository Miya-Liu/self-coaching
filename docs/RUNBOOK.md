# Runbook

From the skill repository root (directory containing `SKILL.md`). The runbook is **agent-agnostic**: any environment with `uv`, `git`, and Bash can follow it; you do not need a specific IDE.

## One-time: dependencies and data

1. Install [uv](https://docs.astral.sh/uv/).
2. `bash scripts/preflight.sh`
3. If needed: `uv --directory upstream/autoresearch run prepare.py` (cache per upstream docs).
4. `bash scripts/init-experience.sh`

## One-time: git in upstream (if not a repo)

See `SKILL.md` — `git init` in `upstream/autoresearch`, first commit on `main`.

## Per experiment: worktree

See `SKILL.md` — `git worktree add` to create `worktrees/<id>/`.

## Run training (log to file)

See `SKILL.md`, or:

```bash
bash scripts/run-once.sh "worktrees/<id>" "logs/<id>.log"
```

## Training pipelines (SFT / GRPO, **AERL** trainer HTTP API)

1. Copy `training/services/example.env` to `training/services/.env` and set `TRAINER_BASE_URL` (default **AERL** `http://localhost:8004` in `training/pipelines/registry.yaml` `service.url`) and keys as needed.
2. On your **AERL** trainer, implement `POST /v1/pipelines/{sft|grpo}/run`, or set `PIPELINE_MODE=local` (or `aerl`) and `AERL_ROOT` to a local **AERL** trainer source tree that provides the `examples/math/…` scripts (see `training/pipelines/_lib.sh`).
3. From skill root:

```bash
bash scripts/run-pipeline.sh grpo "logs/<id>-grpo.log" scheduler.type=local
bash scripts/run-pipeline.sh sft "logs/<id>-sft.log"
```

## Experience (log files)

Experience files:

```bash
bash scripts/init-experience.sh
```

This ensures `experience/EXPERIMENT_LOG.md`, `experience/ERROR.md`, and `experience/LEARNINGS.md` exist.
During runs:
- outcomes go to `experience/EXPERIMENT_LOG.md`
- failures go to `experience/ERROR.md`
- optimization lessons go to `experience/LEARNINGS.md`

## Merge (only after user authorizes)

See `SKILL.md` (`git checkout main`, `git merge`, optional `worktree remove`).

## Hooks

`references/hooks-setup.md` — experiment command, learnings inject, error inject.
