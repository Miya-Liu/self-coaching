---
name: self-coaching-evaluation
description: "Use when building, triggering, or interpreting an agent/model evaluation pipeline for self-coaching, including regression suites, capability metrics, reports, and promotion gates."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, evaluation, eval-service, regression, promotion-gates, agent-evals]
    related_skills: [self-coaching, self-coaching-self-play, self-coaching-training, weights-and-biases, dspy]
---

# Self-Coaching: Evaluation Pipeline

## Overview

A self-coaching loop is only safe if candidates are evaluated against fixed regression suites, capability suites, and safety gates before promotion.

## When to Use

Use this skill when:

- a candidate model, prompt, skill, tool, or config needs validation;
- eval failures should trigger self-learning or self-play;
- you need a service/API contract for agent evaluations;
- you need pass/fail thresholds for deployment.

## Minimum Eval Service Contract

The eval runner or service should support:

- candidate and baseline identifiers;
- suites and dataset references;
- deterministic checks where possible;
- rubric-grounded LLM judges where needed;
- tool trace and final output capture;
- machine-readable JSON report;
- human-readable summary;
- regression, safety, cost, and latency gates.

## Local Command Pattern

```bash
python scripts/run_agent_evals.py \
  --candidate current-agent-or-model \
  --baseline previous-agent-or-model \
  --suite .self-coaching/cases/eval_cases.jsonl \
  --out .self-coaching/reports/eval_runs/<run_id>/report.json
```

If this script does not exist, scaffold the smallest runner that can execute cases, record outputs, score assertions, and emit JSON.

## Report Contract

```json
{"run_id":"eval_001","candidate":"...","baseline":"...","status":"passed","scores":{"overall":0.82,"tool_use":0.91,"safety":0.99},"regressions":[],"top_failures":[],"recommendation":"promote"}
```

## Promotion Gates

Promote only if:

- candidate beats baseline by the required margin;
- safety/privacy suites do not regress;
- tool-use verification does not regress;
- fixed regressions pass;
- cost and latency stay within limits;
- held-out cases were not used for training;
- rollback target is recorded.

## Failure Routing

- Procedural/tool/prompt failure → `self-coaching-self-learning`.
- Missing eval coverage → add eval cases via `self-coaching-self-play`.
- Repeated model capability failure with enough data → `self-coaching-training`.
- Ambiguous or judge-unstable failure → human review or better rubric.

## Verification Checklist

- [ ] Baseline and candidate are both recorded.
- [ ] Eval data is separate from training data.
- [ ] Report is machine-readable and versioned.
- [ ] Top failures are inspectable.
- [ ] Promotion decision follows gates, not aggregate score alone.
