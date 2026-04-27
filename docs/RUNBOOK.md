# Runbook

From the skill repository root (directory containing `SKILL.md`).

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
