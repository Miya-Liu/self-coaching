---
name: self-coaching-self-play
description: "Use when generating, replaying, mutating, critiquing, and curating challenging agent tasks or trajectories for evals, SFT data, or preference/RL data."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, self-play, data-curation, synthetic-data, trajectories, evaluation]
    related_skills: [self-coaching, self-coaching-self-learning, self-coaching-evaluation, subagent-driven-development]
---

# Self-Coaching: Self-Play and Data Curation

## Overview

Self-play creates challenging tasks and trajectories from observed weaknesses. It should generate evaluation and training candidates, not automatically train on them.

## When to Use

Use this skill when:

- eval failures cluster around a capability;
- real user tasks exposed repeated weaknesses;
- you need hard negative examples or adversarial variants;
- you need solver/critic/refiner trajectories for SFT or preference data.

## Roles

Separate roles when possible:

1. Task generator — creates realistic tasks with hidden pitfalls.
2. Solver — attempts the task under normal constraints.
3. Critic/evaluator — scores against a rubric.
4. Refiner — writes ideal answer or corrected trajectory.
5. Curator — filters for novelty, safety, provenance, and split assignment.

## Procedure

1. Pick a target capability and source failure cluster.
2. Generate task variants with success criteria and rubrics.
3. Run solver agents without leaking ideal answers.
4. Score outputs using deterministic checks where possible; use rubric-grounded judges otherwise.
5. Keep only high-signal examples with clear expected behavior.
6. Redact secrets/PII and record provenance.
7. Split by task family: train, validation, held-out eval. Never train on held-out eval cases.
8. Hand fixed eval cases to `self-coaching-evaluation`; hand training examples to `self-coaching-training`.

## JSONL Case Contract

Each case should include at least:

```json
{"id":"case-001","source":"self_play","capability":["tool_use"],"user_request":"...","context":"...","constraints":[],"rubric":{"must":[],"fail":[]},"ideal_response":"...","labels":{"difficulty":"medium","privacy_checked":true,"use_for":["eval"]}}
```

## Common Pitfalls

- Training on exact eval cases.
- Letting the same model generate, solve, judge, and curate without checks.
- Keeping verbose transcripts with weak signal.
- Rewarding fluent style instead of verified task success.
- Forgetting license, consent, and redaction metadata.

## Verification Checklist

- [ ] Each case has capability, rubric, and success/failure criteria.
- [ ] Privacy and provenance metadata are present.
- [ ] Train/validation/eval splits are separated by task family.
- [ ] Judge-only labels have spot checks or second-judge agreement.
- [ ] Eval answers were not leaked into solver prompts.
