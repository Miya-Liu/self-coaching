---
name: self-coaching-self-learning
description: "Use when converting an agent's prior experience, user corrections, resolved bugs, tool failures, or skill changes into durable memory, skill patches, tests, eval cases, or reusable runbooks."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, self-learning, memory, skills, bug-postmortem, agent-improvement]
    related_skills: [self-coaching, hermes-agent-skill-authoring, systematic-debugging, test-driven-development]
---

# Self-Coaching: Self-Learning

## Overview

Self-learning turns real agent experience into compact durable improvements. It is the cheapest and safest self-coaching path: prefer memory, skill patches, tests, and eval cases before model training.

## When to Use

Use this skill after:

- user corrections or preference updates;
- repeated clarification on similar tasks;
- hard bug fixes or non-obvious root causes;
- tool/API/environment quirks;
- stale, missing, or extended skill instructions;
- low-performance eval cases that reveal procedural failures.

Do not use it to save temporary task state, PR numbers, issue numbers, raw logs, or anything likely stale within a week.

## Decision Table

| Observation | Durable artifact |
|---|---|
| Stable user preference | Memory |
| Stable environment convention | Memory |
| Reusable workflow | New skill or skill patch |
| Existing skill missing pitfall/step | Skill patch |
| Code defect | Fix + regression test |
| Weak behavior to prevent | Eval case |
| Repeated manual operation | Tool/plugin/MCP candidate |
| Model capability gap after instruction/tool fixes | Training-data candidate |

## Procedure

1. Write a one-paragraph postmortem: symptom, false starts, root cause, fix, verification.
2. Classify the lesson using the decision table.
3. Choose the smallest durable artifact.
4. Save only compact stable facts to memory.
5. Patch existing skills before creating new ones.
6. Add tests/evals for behavior that must not regress.
7. If the lesson is training-worthy, hand it to `self-coaching-self-play` or `self-coaching-training` only after privacy review.

## Verification Checklist

- [ ] The lesson is stable, not task-local.
- [ ] The chosen artifact is the smallest sufficient one.
- [ ] Memory entries are compact and declarative.
- [ ] Skills include triggers, steps, pitfalls, and verification.
- [ ] Bug fixes have tests or eval cases.
- [ ] No secrets, private data, or stale identifiers were saved.
