---
name: self-tuning
description: "Use when routing curated self-coaching data into SFT, LoRA, preference, or RL training runs, with executable SFT/GRPO pipeline helpers, manifests, split hygiene, evaluation gates, and rollback."
version: 0.3.1
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, sft, rl, grpo, preference-training, lora, dataset-curation, model-training, aerl]
    related_skills: [self-coaching, self-play, self-evaluation, self-learning, huggingface-hub, weights-and-biases]
---

# Self-Coaching: Training

## Overview

Training is the most expensive self-coaching path. Use it only when skills, prompts, tools, and eval fixes are insufficient or when the explicit goal is model improvement.

This skill includes executable pipeline helpers for SFT and GRPO-style RL under `self-tuning/pipelines/`, plus category-level scripts under `../scripts/` for preflight, named pipeline runs, and the mock loop demo.

## When to Use

Use training when:

- the weakness repeats across many tasks;
- curated examples are high-quality, licensed, deduplicated, and privacy-checked;
- an eval pipeline can compare candidate vs baseline;
- deployment, canary, and rollback are defined;
- cheaper improvements, such as skill patches or tools, are insufficient.

Do not train when fewer examples, clearer instructions, a skill patch, or a tool would solve the problem.

## Folder Map

The category root (`SKILL_ROOT`) is wherever the `self-coaching` skill is installed. All paths below are relative to `SKILL_ROOT`:

```text
$SKILL_ROOT/
  scripts/
    preflight.sh
    run-pipeline.sh
    hook-experiment.sh
    hook-inject-errors.sh
    hook-inject-learnings.sh
    init-experience.sh
  experience/
    EXPERIMENT_LOG.md
    ERROR.md
    LEARNINGS.md
    RUN_SUMMARY.json
  self-tuning/
    services/example.env
    pipelines/registry.yaml
    pipelines/_lib.sh
    pipelines/sft/pipeline.yaml
    pipelines/sft/run.sh
    pipelines/grpo/pipeline.yaml
    pipelines/grpo/run.sh
```

Copy `self-tuning/services/example.env` to `self-tuning/services/.env` only when you need real service credentials. Never commit or paste credential values.

## Preflight and Environment

Validate trainer configuration before first pipeline run:

```bash
bash "$SKILL_ROOT/scripts/preflight.sh"
```

Checks `self-tuning/services/.env` (from `example.env`) and optional `AERL_ROOT` for local source mode.

For HTTP pipeline mode, configure a service compatible with this contract:

```text
POST {TRAINER_BASE_URL}/v1/pipelines/{sft|grpo}/run
body: {"argv": ["scheduler.type=local", "..."]}
response body: training log stream/text
```

```bash
cp "$SKILL_ROOT/self-tuning/services/example.env" \
   "$SKILL_ROOT/self-tuning/services/.env"
# edit .env locally; keep secrets out of chat and source control
```

## Running a Named Pipeline

```bash
bash "$SKILL_ROOT/scripts/run-pipeline.sh" \
  sft "$SKILL_ROOT/logs/sft-001.log" \
  dataset.path=.self-coaching/curated/train.jsonl

bash "$SKILL_ROOT/scripts/run-pipeline.sh" \
  grpo "$SKILL_ROOT/logs/grpo-001.log" \
  scheduler.type=local
```

Pipeline IDs: `self-tuning/pipelines/registry.yaml`

Default mode is HTTP via `TRAINER_BASE_URL` (default `http://localhost:8004`). Local AERL source:

```bash
PIPELINE_MODE=local AERL_ROOT=/path/to/AERL \
  bash "$SKILL_ROOT/scripts/run-pipeline.sh" \
  grpo "$SKILL_ROOT/logs/grpo-local-001.log"
```

All stdout/stderr must go to log files. Read only relevant line ranges back into context.

## Mock loop (end-to-end validation)

Before live training, validate the gated loop on mocks:

```bash
python -m self_coaching.demo
```

See umbrella `SKILL.md` § Validating the Loop on Mocks.

## SFT Procedure

1. Collect curated demonstrations from real tasks and self-play.
2. Redact secrets and verify license/consent.
3. Convert to target chat/tool-call format.
4. Split by task family, not random transcript chunks.
5. Run SFT or LoRA conservatively via the `sft` pipeline.
6. Evaluate against fixed regression and held-out suites.
7. Inspect top failures manually.
8. Version dataset, config, model, logs, and eval report together.

## Preference / RL Procedure

1. Generate multiple candidate solutions for each task.
2. Score with rubrics, human review, or multiple judges.
3. Store chosen/rejected pairs or scalar rewards.
4. Drop ambiguous and judge-unstable examples.
5. Train with DPO/ORPO/GRPO/PPO-style scripts as infrastructure allows. The provided executable RL pipeline is `grpo`.
6. Evaluate against held-out, safety, and adversarial suites.
7. Monitor reward hacking, verbosity drift, and tool-use regressions.

## Record Schemas

SFT record:

```json
{"id":"sft-001","source":"eval_failure","messages":[],"tool_trace_summary":[],"ideal_response":"...","capability":["debugging"],"privacy_checked":true,"license":"internal-permitted","use_for":["train"]}
```

Preference record:

```json
{"id":"pref-001","prompt":"...","chosen":"...","rejected":"...","rubric":"...","judge_model":"...","human_reviewed":false,"privacy_checked":true,"use_for":["train"]}
```

Training manifest:

```json
{"run_id":"train_001","pipeline_id":"sft","dataset_refs":[],"base_model":"...","method":"sft_lora","hyperparameters":{},"log_file":"logs/train_001.log","eval_run_id":"eval_...","rollback_target":"..."}
```

## Experience Logging

After each run, update:

- `experience/EXPERIMENT_LOG.md` with run id, hypothesis, metric value, best-before, decision, and log path.
- `experience/ERROR.md` for crashes, OOMs, parse errors, environment failures, or logic bugs.
- `experience/LEARNINGS.md` for reusable optimization or process lessons.
- `experience/RUN_SUMMARY.json` when a machine-readable run summary is useful.

```bash
bash "$SKILL_ROOT/scripts/hook-inject-errors.sh"
bash "$SKILL_ROOT/scripts/hook-inject-learnings.sh"
```

## Evaluation Gate

Every training run must hand off to **self-evaluation** before promotion:

```bash
python scripts/run_agent_evals.py \
  --candidate <trained-model-or-endpoint> \
  --baseline <previous-model-or-endpoint> \
  --suite .self-coaching/cases/eval_cases.jsonl \
  --out .self-coaching/reports/eval_runs/<run_id>/report.json
```

Record the eval report path in the training manifest. Promote only if target metrics improve and safety/tool-use regressions do not appear.

## Self-coaching loop

```text
mine failures -> hypothesize -> generate self-play tasks -> solve -> critique -> curate -> train or patch skills -> evaluate -> promote/rollback -> archive postmortem
```

Prefer cheap improvements first. Training should be gated by evidence, not by the mere availability of data.

## Common Pitfalls

1. **Training before eval exists.** Build or select the eval runner first.
2. **Wrong service path.** Pipeline scripts live under `self-tuning/pipelines/`, not `training/pipelines/`.
3. **Skipping mock validation.** Run `python -m self_coaching.demo` before live APIs.
4. **Pasting full logs.** Logs belong in `logs/*.log`; summarize key metrics and line ranges.
5. **Leaking secrets.** Keep `.env` values out of chat, memory, skills, and source control.
6. **No rollback.** Record the baseline model/config before training.

## Verification Checklist

- [ ] Data is privacy-checked, licensed, and deduplicated.
- [ ] Train/validation/test splits are separated by task family.
- [ ] Held-out eval data is not in training.
- [ ] `bash -n` passes for pipeline scripts.
- [ ] `run-pipeline.sh` points to `self-tuning/pipelines/`.
- [ ] Training manifest records lineage, log file, and rollback target.
- [ ] Candidate passes evaluation gates.
- [ ] Experience logs summarize outcomes without raw log dumps or secrets.
