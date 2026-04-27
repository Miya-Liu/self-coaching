# Experiment log (Experience)

**Experience** — persistent record of training experiment **outcomes**. See `SKILL.md`.

**Purpose**: Per-run / per-attempt **outcomes** and metrics. Primary results log for the coaching loop.

| run_id | iteration | worktree / branch | hypothesis | files_changed | metric_name | metric_value | best_before | decision | notes |
|---|---:|---|---|---|---|---:|---:|---|---|
| baseline-001 | 0 | (none) | baseline | — | val_bpb | | n/a | kept | no code change |
| exp-001 | 1 | worktrees/… | | train.py | val_bpb | | | keep/discard | |

## Per-run notes
- `log_file` (e.g. `logs/<id>.log`):
- `time_budget` / `stop_reason` (if any):

---
