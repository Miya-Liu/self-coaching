# Runbook

From **repository root**. Bash required; **uv** only for external autoresearch.

Install: [deploy-skill-pack.md](deploy-skill-pack.md). Design: [architecture.md](../design/architecture.md).

## One-time setup

```bash
bash scripts/install-skill-pack.sh . --with-mock
```

Autoresearch worktrees: set `AUTORESEARCH_ROOT` ([upstream/README.md](../../upstream/README.md)), install [uv](https://docs.astral.sh/uv/), `bash scripts/preflight.sh`.

## Worktree experiment

See `modes/self-coaching/SKILL.md` — `git worktree add worktrees/<id>/` under the coaching root.

```bash
bash scripts/run-once.sh "worktrees/<id>" "logs/<id>.log"
```

Summaries → `experience/`; full train output → `logs/<id>.log` only. Merge after human approval per `SKILL.md`.

## AERL pipelines (optional)

1. Copy `modes/self-coaching/self-tuning/services/example.env` → `.env`; set `TRAINER_BASE_URL`
2. `bash scripts/run-pipeline.sh grpo logs/exp-01-grpo.log`

## Mock loop demo

One command (~30–60s):

```bash
bash scripts/mock-self-coaching-demo.sh                    # Git Bash / Linux
python scripts/mock_self_coaching_demo.py                    # Windows / cross-platform
```

Optional env: copy [scenarios/demo.env.example](../../scenarios/demo.env.example) → `scenarios/demo.env` (`LOOP_SERVICE_MODE`: `mock-module` | `mock-http` | `live`).

Expected: `completeness: PASS` (C01–C18). Key artifacts under `mock-services/demo-loop/.self-coaching/loop/`.

Verbose step-by-step and env knobs: [self-coaching-demo-pipeline-plan.md §10](../project/self-coaching-demo-pipeline-plan.md#10-configuration-environment).
