# Runbook

From the skill repository root (directory containing `SKILL.md`). The runbook is **agent-agnostic**: Bash is required; **uv** is only needed for the external autoresearch training path.

**T1 install:** see [`deploy-skill-pack.md`](deploy-skill-pack.md) or run `bash scripts/install-skill-pack.sh . --with-mock`.

## One-time: dependencies and data

1. `bash scripts/install-skill-pack.sh .` (or `init-experience.sh` + `doctor.sh` manually).
2. **If using autoresearch worktrees:** clone the trainer repo and set `AUTORESEARCH_ROOT` (see [`upstream/README.md`](../../upstream/README.md)), install [uv](https://docs.astral.sh/uv/), then `bash scripts/preflight.sh`.
3. If needed: `uv --directory "$AUTORESEARCH_ROOT" run prepare.py` (cache per autoresearch docs).

Example:

```bash
git clone https://github.com/karpathy/autoresearch.git ~/src/autoresearch
export AUTORESEARCH_ROOT=~/src/autoresearch
bash scripts/preflight.sh
```

## One-time: git in the trainer repo (if not a repo)

See `SKILL.md` — `git init` in your `AUTORESEARCH_ROOT` checkout, first commit on `main`.

## Per experiment: worktree

See `SKILL.md` — `git worktree add` into `worktrees/<id>/` under the skill root.

## Run training (log to file)

See `SKILL.md`, or:

```bash
bash scripts/run-once.sh "worktrees/<id>" "logs/<id>.log"
```

## Training pipelines (SFT / GRPO, **AERL** trainer HTTP API)

1. Copy `self-coaching-training/services/example.env` to `self-coaching-training/services/.env` and set `TRAINER_BASE_URL` (default **AERL** `http://localhost:8004` in `self-coaching-training/pipelines/registry.yaml` `service.url`) and keys as needed.
2. On your **AERL** trainer, implement `POST /v1/pipelines/{sft|grpo}/run`, or set `PIPELINE_MODE=local` (or `aerl`) and `AERL_ROOT` to a local **AERL** trainer source tree that provides the `examples/math/…` scripts (see `self-coaching-training/pipelines/_lib.sh`).
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
