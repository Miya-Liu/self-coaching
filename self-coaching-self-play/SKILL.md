---
name: self-coaching-self-play
description: "Use when generating, replaying, mutating, critiquing, and curating challenging agent tasks or trajectories for evals, SFT data, or preference/RL data."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, self-play, data-curation, synthetic-data, trajectories, evaluation]
    related_skills: [self-coaching, self-coaching-self-learning, self-coaching-evaluation, self-coaching-training, subagent-driven-development]
---

# Self-Coaching: Self-Play and Data Curation

## Overview

Self-play creates challenging tasks and trajectories from observed weaknesses. It should generate evaluation and training candidates, not automatically train on them.

A real self-play loop has five separable jobs: generate tasks, solve them, critique outputs, refine ideal trajectories, and curate/split records. Keep these roles separate when possible so the same model is not inventing, solving, judging, and approving its own data without checks.

## When to Use

Use this skill when:

- eval failures cluster around a capability;
- real user tasks exposed repeated weaknesses;
- experience logs contain recurring errors or stalled learning;
- you need hard negative examples or adversarial variants;
- you need solver/critic/refiner trajectories for SFT or preference data.

Do not use self-play to fabricate evidence of improvement. Self-play creates candidates; evaluation and curation decide whether candidates are useful.

## Inputs and Outputs

Inputs can come from:

- `experience/ERROR.md` and `experience/LEARNINGS.md` created by `self-coaching-self-learning`;
- eval failure reports from `self-coaching-evaluation`;
- user-corrected transcripts, after privacy review;
- known capability targets such as tool verification, debugging, planning, memory use, skill use, and safety.

Outputs should be JSONL records assigned to one of three destinations:

```text
.self-coaching/cases/self_play_candidates.jsonl  # generated, not trusted yet
.self-coaching/cases/eval_cases.jsonl           # held-out fixed eval cases
.self-coaching/curated/train.jsonl              # training split
.self-coaching/curated/validation.jsonl         # validation split
```

If the project already has a dataset layout, use it. Otherwise create the `.self-coaching/` layout above.

## Roles

Separate roles when possible:

1. **Task generator** — creates realistic tasks with hidden pitfalls and success criteria.
2. **Solver** — attempts the task under normal constraints without seeing ideal answers.
3. **Critic/evaluator** — scores against a rubric and records concrete failures.
4. **Refiner** — writes ideal answer or corrected trajectory.
5. **Curator** — filters for novelty, safety, provenance, and split assignment.

For Hermes, these roles can be separate subagents. Pass only the necessary context to each role; do not leak the ideal answer to the solver.

## Step-by-Step Procedure

1. **Choose capability and source.** Start from a concrete failure cluster, e.g. "claims file write success without reading back".
2. **Generate candidate tasks.** Each task needs a user request, setup/context, hidden pitfall, constraints, expected artifacts, and rubric.
3. **Run solver attempts.** Use normal agent constraints and tools. Require verifiable side effects when the task has side effects.
4. **Critique.** Prefer deterministic checks. Use LLM judges only with a rubric and spot checks.
5. **Refine.** Write the ideal final answer or corrected trajectory. Store observable actions/tool summaries, not hidden private chain-of-thought.
6. **Curate.** Redact secrets, deduplicate, label capability/difficulty/source, and reject ambiguous examples.
7. **Split by task family.** Do not randomly split near-duplicates. Keep held-out eval families out of training.
8. **Route.** Fixed cases go to `self-coaching-evaluation`; training examples go to `self-coaching-training`.

## Generator Prompt Template

```text
Generate <N> realistic autonomous-agent tasks targeting <capability>.
Source weakness: <failure cluster or experience-log summary>.
Each task must include:
- id
- user_request
- setup/context
- hidden_pitfall
- constraints
- expected_artifacts
- rubric.must
- rubric.fail
- deterministic_checks if possible
- privacy/license constraints
Avoid secrets, real credentials, and private data. Prefer tasks requiring verification.
Return JSONL records only.
```

## JSONL Case Contract

Each case should include at least:

```json
{"id":"case-001","source":"self_play","capability":["tool_use"],"user_request":"...","context":"...","constraints":[],"hidden_pitfall":"...","expected_artifacts":[],"rubric":{"must":[],"fail":[]},"deterministic_checks":[],"ideal_response":"...","labels":{"difficulty":"medium","privacy_checked":true,"provenance":"generated_from_eval_failure","use_for":["eval"]}}
```

Trajectory records for training should add observable messages/tool summaries:

```json
{"id":"traj-001","case_id":"case-001","source":"self_play_solver","messages":[],"tool_trace_summary":[],"critique":{"score":0.0,"failures":[]},"ideal_response":"...","labels":{"privacy_checked":true,"use_for":["train"]}}
```

## Curation Gates

Reject a case or trajectory if:

- it contains secrets, private data, or unclear license status;
- the rubric is subjective without observable success criteria;
- the ideal answer depends on hidden facts not available to the solver;
- it is a near-duplicate of an existing case in the same split;
- it rewards verbosity or style instead of task success;
- the judge and generator are the same model and no spot check was done.

## Handoff Rules

- To evaluation: append fixed, privacy-checked cases to `.self-coaching/cases/eval_cases.jsonl` and load `self-coaching-evaluation`.
- To training: append curated demonstrations to `.self-coaching/curated/train.jsonl` or preference records to the training pool, then load `self-coaching-training`.
- To self-learning: if self-play reveals a missing procedure, patch the relevant skill instead of making only training data.

## Common Pitfalls

1. **Training on exact eval cases.** Keep held-out eval cases separate forever.
2. **Letting one model self-approve.** Separate generator/solver/judge when possible and spot-check judge-only labels.
3. **Keeping verbose transcripts.** Store compact observable traces and final answers.
4. **Rewarding fluency.** Rubrics must score verified success, not style.
5. **Skipping provenance.** Every record needs source, privacy, license, and split labels.

## Verification Checklist

- [ ] Each case has capability, hidden pitfall, rubric, and success/failure criteria.
- [ ] Privacy, license, and provenance metadata are present.
- [ ] Solver did not receive ideal answers.
- [ ] Train/validation/eval splits are separated by task family.
- [ ] Judge-only labels have spot checks or second-judge agreement.
- [ ] Evaluation cases were not copied into training data.
- [ ] Training handoff records contain observable behavior, not private hidden chain-of-thought.
