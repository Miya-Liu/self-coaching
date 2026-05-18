---
name: self-coaching-training
description: "Use when routing curated self-coaching data into SFT, LoRA, preference, or RL training runs, with manifests, split hygiene, evaluation gates, and rollback."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, sft, rl, preference-training, lora, dataset-curation, model-training]
    related_skills: [self-coaching, self-coaching-self-play, self-coaching-evaluation, huggingface-hub, weights-and-biases]
---

# Self-Coaching: Training

## Overview

Training is the most expensive self-coaching path. Use it only when skills, prompts, tools, and eval fixes are insufficient or when the explicit goal is model improvement.

## When to Use

Use training when:

- the weakness repeats across many tasks;
- curated examples are high-quality and privacy-checked;
- an eval pipeline can compare candidate vs baseline;
- deployment, canary, and rollback are defined.

Do not train when fewer examples, clearer instructions, a skill patch, or a tool would solve the problem.

## SFT Procedure

1. Collect curated demonstrations from real tasks and self-play.
2. Redact secrets and verify license/consent.
3. Convert to target chat/tool-call format.
4. Split by task family, not random transcript chunks.
5. Train conservatively: SFT or LoRA first.
6. Evaluate against fixed regression and held-out suites.
7. Inspect top failures manually.
8. Version dataset, config, model, and eval report together.

## Preference / RL Procedure

1. Generate multiple candidate solutions for each task.
2. Score with rubrics, human review, or multiple judges.
3. Store chosen/rejected pairs or scalar rewards.
4. Drop ambiguous and judge-unstable examples.
5. Train with DPO/ORPO/GRPO/PPO-style scripts as infrastructure allows.
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
{"run_id":"train_001","dataset_refs":[],"base_model":"...","method":"sft_lora","hyperparameters":{},"eval_run_id":"eval_...","rollback_target":"..."}
```

## Autoresearch-Style Loop

```text
mine failures -> hypothesize -> generate self-play tasks -> solve -> critique -> curate -> train or patch skills -> evaluate -> promote/rollback -> archive postmortem
```

Prefer cheap improvements first. Training should be gated by evidence, not by the mere availability of data.

## Verification Checklist

- [ ] Data is privacy-checked, licensed, and deduplicated.
- [ ] Train/validation/test splits are separated by task family.
- [ ] Held-out eval data is not in training.
- [ ] Training manifest records lineage.
- [ ] Candidate passes evaluation gates.
- [ ] Rollback target exists.
