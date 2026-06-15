# Runbook

From **repository root**. Bash required.

Install: [deploy-skill-pack.md](deploy-skill-pack.md). Design: [architecture.md](../design/architecture.md).

## One-time setup

```bash
bash scripts/install-skill-pack.sh . --with-mock
```

Optional AERL: copy `modes/self-coaching/self-tuning/services/example.env` → `.env`, then `bash scripts/preflight.sh`.

## Training pipelines (SFT / GRPO)

```bash
bash scripts/run-pipeline.sh sft logs/exp-01-sft.log
bash scripts/run-pipeline.sh grpo logs/exp-01-grpo.log
```

Summaries → `experience/`; full train output → `logs/<id>.log` only.

## Mock loop demo

One command (~30–60s):

```bash
bash scripts/mock-self-coaching-demo.sh                    # Git Bash / Linux
python scripts/mock_self_coaching_demo.py                  # Windows / cross-platform
```

Optional env: copy [scenarios/demo.env.example](../../scenarios/demo.env.example) → `scenarios/demo.env`.

Expected: `completeness: PASS` (C01–C18). Env knobs: [self-coaching-demo-pipeline-plan.md §10](../project/self-coaching-demo-pipeline-plan.md#10-configuration-environment).
