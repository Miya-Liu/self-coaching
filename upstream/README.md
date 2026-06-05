# External trainer repo (not vendored)

This skill pack does **not** ship [karpathy/autoresearch](https://github.com/karpathy/autoresearch) inside the repository. Clone it elsewhere and point the scripts at it:

```bash
git clone https://github.com/karpathy/autoresearch.git ~/src/autoresearch
export AUTORESEARCH_ROOT=~/src/autoresearch
bash scripts/preflight.sh
```

Worktrees for experiments still live under the coaching root: `worktrees/<experiment_id>/` (see `modes/self-coaching/SKILL.md`).

**Optional legacy layout:** you may clone into `upstream/autoresearch/` here; that path is gitignored and never committed.

**Without autoresearch:** use AERL HTTP pipelines only (`modes/self-coaching/self-tuning/pipelines/`, `TRAINER_BASE_URL`) — no `AUTORESEARCH_ROOT` required.
