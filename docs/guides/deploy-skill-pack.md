# Deploy T1 — Self-coaching pack

**Active deploy target.** Ship `modes/self-coaching/`: markdown skills + Bash helpers. T2/T3 are optional — [deploy-overview.md](deploy-overview.md).

## What you deploy

| Artifact | Path |
|----------|------|
| Orchestration policy | `modes/self-coaching/SKILL.md` |
| Submodules | `modes/self-coaching/{self-learning,self-play,self-evaluation,self-tuning}/` |
| Training pipelines | `modes/self-coaching/self-tuning/pipelines/` |
| Experience templates | `experience/` |
| Version | `modes/self-coaching/SKILL_PACK_VERSION` |

## Prerequisites

**bash**, **git** (required). **python** 3.10+ (recommended for mock demo).

## Install

### Repo clone

```bash
bash scripts/install-skill-pack.sh . --with-mock
```

- `[target-root]` — coaching root for `experience/`, `logs/`, `worktrees/` (default: repo root)
- `--with-mock` — run mock pipeline smoke

### Hermes Agent

Use **Git Bash** or **WSL** on Windows (bash-only installer).

```bash
bash scripts/install-skill-pack.sh --hermes              # skills + mock harness
bash scripts/install-skill-pack.sh --hermes --with-mock    # + pip install -e . for python -m self_coaching.demo
```

Installs five skills under `~/.hermes/skills/self-coaching/` plus `mock-services/`, `scenarios/`, `tools/`. `pyproject.toml` does **not** install Hermes skills — use the script above.

| You want to… | Run |
| --- | --- |
| Skills only | `bash scripts/install-skill-pack.sh --hermes` |
| Full mock demo | `bash scripts/install-skill-pack.sh --hermes --with-mock` |
| Develop runtime | `pip install -e .` from repo clone |

Verify: `hermes skill list | grep self-coaching` (expect 5 skills). Demo: `python -m self_coaching.demo` → `completeness: PASS`.

### Pack copy / Cursor

Copy `modes/self-coaching/` to `~/skills/self-coaching/` or `~/.cursor/skills/self-coaching/`. Point hooks at repo `scripts/` with absolute paths if needed.

## Verify

```bash
bash scripts/doctor.sh
bash scripts/doctor.sh --json
```

## Upgrade

**Hermes** (from repo clone after `git pull`):

```bash
bash scripts/update-skill-pack.sh --hermes --dry-run
bash scripts/update-skill-pack.sh --hermes
bash scripts/update-skill-pack.sh --hermes --force   # overwrite local skill edits
```

**Clone / pack copy:** pull → compare `SKILL_PACK_VERSION` → re-copy or re-run `install-skill-pack.sh`. Changelog: [changelog-skills.md](../project/changelog-skills.md).

## AERL training (optional)

1. `cp modes/self-coaching/self-tuning/services/example.env modes/self-coaching/self-tuning/services/.env`
2. Set `TRAINER_BASE_URL`; never commit `.env`
3. `bash scripts/run-pipeline.sh sft logs/my-run.log`

## Related

- [runbook.md](runbook.md) · [self_coaching_mode.md](../design/self_coaching_mode.md)
- T2/T3: [deploy-overview.md](deploy-overview.md)
