# Deploy Target 1 — Self-coaching pack (self-coaching mode)

**Active deploy target — [self-coaching mode](../design/self_coaching_mode.md).**

Ship **`modes/self-coaching/`**: a portable, agent-agnostic skill pack that coaches the **host agent** through a gated loop (observe → **self-learning** → **self-play** → **self-evaluation** → optional **self-tuning** → Experience → human-approved merge). Markdown + Bash; not tied to one IDE.

When you clone the **full repository**, repo-root `scripts/`, `experience/`, and `mock-services/` are also available. Coaching API (T2) and evolution engine (T3) are optional.

## What you deploy

| Artifact | Path | Role |
|----------|------|------|
| Orchestration policy | `modes/self-coaching/SKILL.md` | Full self-coaching loop and gates |
| Stage index | `modes/self-coaching/DESCRIPTION.md` | When to load each phase |
| Submodules | `modes/self-coaching/{self-learning,self-play,self-evaluation,self-tuning}/SKILL.md` | Pipeline stages |
| Training pipelines | `modes/self-coaching/self-tuning/pipelines/` | AERL SFT/GRPO helpers |
| Host adapters | `modes/self-coaching/adapters/` | Install into Hermes, OpenClaw, etc. |
| Experience templates | `experience/` (repo root) | `EXPERIMENT_LOG.md`, `ERROR.md`, `LEARNINGS.md` |
| Version marker | `modes/self-coaching/SKILL_PACK_VERSION` | Pack revision |
| Example config | `configs/self-coaching.example.yaml` | Template (optional) |

Optional (not required for T1): `mock-services/`, `services/orchestrator/` (T2/T3).

## Prerequisites

| Tool | Required? | Purpose |
|------|-----------|---------|
| **bash** | Yes | All helpers |
| **git** | Yes | Worktree experiment flow |
| **python** | Recommended | Mock dry-run |
| **jq**, **curl** | For AERL HTTP pipelines | `run-pipeline.sh` |
| **uv** | For autoresearch `train.py` | `AUTORESEARCH_ROOT` path |

## Install (recommended)

From **repository root** (full clone):

```bash
bash scripts/install-skill-pack.sh . --with-mock
```

Or copy **`modes/self-coaching/`** into your agent's skill directory and point hooks at repo-root `scripts/` with absolute paths if needed.

Arguments:

- `[target-root]` — where `experience/`, `logs/`, `worktrees/` are created (default: repo root).
- `--with-mock` — runs `mock-run-all.sh`.
- `--with-trainer` — runs `preflight.sh` (needs `uv` + `AUTORESEARCH_ROOT`).

## Install paths (agents)

| Location | Example |
|----------|---------|
| Full repo | Clone repo; agent loads `modes/self-coaching/SKILL.md` |
| Pack copy | `~/skills/self-coaching/` ← contents of `modes/self-coaching/` |
| Cursor | `~/.cursor/skills/self-coaching/` |

## AERL training (optional)

1. `cp modes/self-coaching/self-tuning/services/example.env modes/self-coaching/self-tuning/services/.env`
2. Set `TRAINER_BASE_URL`.
3. `PIPELINE_MODE=local` + `AERL_ROOT` for local trainer source.
4. `bash scripts/run-pipeline.sh sft logs/my-run.log`

Never commit `.env`.

## Verification

```bash
bash scripts/doctor.sh
bash scripts/doctor.sh --json
```

## Upgrade

1. Pull or replace the tree.
2. Compare `modes/self-coaching/SKILL_PACK_VERSION` before/after.
3. Re-run `bash scripts/install-skill-pack.sh <root>`.
4. Re-read `modes/self-coaching/SKILL.md` if minor version changed.

## Out of scope for T1

- Hosting `mock_self_coaching.py serve` → [deploy-overview.md](deploy-overview.md) T2.
- Automated evolution engine → [deploy-overview.md](deploy-overview.md) T3.

## Related

- [self_coaching_mode.md](../design/self_coaching_mode.md) · [coach_mode.md](../design/coach_mode.md)
- [runbook.md](runbook.md) · [architecture.md](../design/architecture.md)
