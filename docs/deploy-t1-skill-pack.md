# Deploy Target 1 — Skill pack

**Active deploy target for this repository.** You ship markdown skills, Bash helpers, and an on-disk **Experience** layout. No HTTP service or orchestrator is required.

## What you deploy

| Artifact | Path | Role |
|----------|------|------|
| Orchestration policy | `SKILL.md` | Full self-coaching loop and gates |
| Phase skills | `self-coaching-*/SKILL.md` | Atomic steps (learn, self-play, eval, train) |
| Scripts | `scripts/*.sh` | init, doctor, training, mock dry-run |
| Training pipelines | `self-coaching-training/pipelines/` | AERL SFT/GRPO helpers |
| Experience templates | `experience/` | `EXPERIMENT_LOG.md`, `ERROR.md`, `LEARNINGS.md` |
| Version marker | `SKILL_PACK_VERSION` | Track which pack revision is installed |

Optional (not required for T1): `mock-services/`, `services/orchestrator/` (T2/T3).

## Prerequisites

| Tool | Required? | Purpose |
|------|-----------|---------|
| **bash** | Yes | All helpers |
| **git** | Yes | Worktree experiment flow |
| **python** | Recommended | Mock dry-run; some pipeline helpers |
| **jq**, **curl** | For AERL HTTP pipelines | `run-pipeline.sh` |
| **uv** | For autoresearch `train.py` only | `preflight.sh` + `run-once.sh`; optional if you use AERL HTTP only |

## Install (recommended)

From the repository root:

```bash
bash scripts/install-skill-pack.sh . --with-mock
```

Arguments:

- `[target-root]` — where `experience/`, `logs/`, `worktrees/` are created (default: repo root).
- `--with-mock` — runs `mock-run-all.sh` to prove the artifact layout.
- `--with-upstream` — runs `preflight.sh` (needs `uv` + `upstream/autoresearch`).

Or step by step:

```bash
bash scripts/init-experience.sh .
bash scripts/doctor.sh
bash scripts/mock-run-all.sh    # optional; needs python
```

## Install paths (agents)

Copy or clone this repo to one of:

| Location | Example |
|----------|---------|
| Project-local | `my-repo/skills/self-coaching/` |
| User global | `~/skills/self-coaching/` |
| Cursor | `~/.cursor/skills/self-coaching/` |

Configure your agent to load **`SKILL.md`** at the pack root (or a phase skill under `self-coaching-*/`).

## AERL training (optional)

1. `cp self-coaching-training/services/example.env self-coaching-training/services/.env`
2. Set `TRAINER_BASE_URL` (overrides default `http://localhost:8004` from `registry.yaml`).
3. For local trainer source: `PIPELINE_MODE=local` and `AERL_ROOT=/path/to/AERL` (must contain `train.py`).
4. Run: `bash scripts/run-pipeline.sh sft logs/my-run.log`

Never commit `.env`.

## Verification

```bash
bash scripts/doctor.sh          # must exit 0
bash scripts/doctor.sh --json   # machine-readable
```

CI runs the same checks on every push to `main`.

## Upgrade

1. Replace or `git pull` the skill tree.
2. Compare `SKILL_PACK_VERSION` before/after.
3. Re-run `bash scripts/install-skill-pack.sh <root>`.
4. Re-read `SKILL.md` if the minor version changed.

## Out of scope for T1

- Hosting `mock_self_coaching.py serve` → see [production-deployment.md](production-deployment.md) T2.
- Automatic improve-on-eval-drop → see T3 / `services/orchestrator/`.

## Related

- [RUNBOOK.md](RUNBOOK.md) — day-to-day commands
- [ARCHITECTURE.md](ARCHITECTURE.md) — control boundaries
- [roadmap.md](roadmap.md) — when to adopt T2/T3
