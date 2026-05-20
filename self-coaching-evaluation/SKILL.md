---
name: self-coaching-evaluation
description: "Use when building, triggering, or interpreting an agent/model evaluation pipeline for self-coaching, including regression suites, capability metrics, reports, failure routing, and promotion gates."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, evaluation, eval-service, regression, promotion-gates, agent-evals]
    related_skills: [self-coaching, self-coaching-self-learning, self-coaching-self-play, self-coaching-training, weights-and-biases, dspy]
---

# Self-Coaching: Evaluation Pipeline

## Overview

A self-coaching loop is only safe if candidates are evaluated against fixed regression suites, capability suites, and safety gates before promotion.

This skill defines the evaluation contract. The current folder contains executable training helpers plus a deterministic stdlib-only mock service harness under `mock-services/` (see `mock-services/README.md` for the CLI/HTTP contracts and the `run-all` smoke test). Until a project-specific runner exists, scaffold the smallest local runner that executes JSONL cases, records outputs, scores deterministic checks, emits a JSON report, and routes failures back into self-learning or self-play.

## When to Use

Use this skill when:

- a candidate model, prompt, skill, tool, pipeline, or config needs validation;
- eval failures should trigger self-learning or self-play;
- you need a service/API contract for agent evaluations;
- you need pass/fail thresholds for deployment;
- a training run finished and must be compared with the baseline before promotion.

## Minimum Eval Service Contract

The eval runner or service should support:

- candidate and baseline identifiers;
- suites and dataset references;
- deterministic checks where possible;
- rubric-grounded LLM judges where needed;
- tool trace and final output capture;
- machine-readable JSON report;
- human-readable summary;
- regression, safety, cost, and latency gates;
- failure export for self-learning and self-play.

## Recommended Project Layout

If no project layout exists, use:

```text
.self-coaching/
  cases/
    eval_cases.jsonl
    self_play_candidates.jsonl
  curated/
    train.jsonl
    validation.jsonl
    test.jsonl
  reports/
    eval_runs/<run_id>/report.json
    eval_runs/<run_id>/summary.md
  postmortems/
  manifests/
```

Keep eval cases and train cases separate by task family. Do not train on `eval_cases.jsonl`.

## Local Command Pattern

```bash
python scripts/run_agent_evals.py \
  --candidate current-agent-or-model \
  --baseline previous-agent-or-model \
  --suite .self-coaching/cases/eval_cases.jsonl \
  --out .self-coaching/reports/eval_runs/<run_id>/report.json
```

If this script does not exist, create a minimal runner with this behavior:

1. Read JSONL cases.
2. For each case, run the candidate under a fixed budget.
3. Capture final answer, tool-call summaries, cost, latency, and errors.
4. Run deterministic assertions first.
5. Use rubric-grounded judge only for cases that cannot be scored deterministically.
6. Emit `report.json` and `summary.md`.
7. Return non-zero if promotion gates fail.

## Report Contract

```json
{"run_id":"eval_001","candidate":"...","baseline":"...","status":"passed","scores":{"overall":0.82,"tool_use":0.91,"safety":0.99},"regressions":[],"top_failures":[{"case_id":"case-001","reason":"missed verification","route":"self-learning"}],"cost":{"tokens":0,"usd":0.0},"latency":{"p50_s":0.0,"p95_s":0.0},"recommendation":"promote"}
```

## Promotion Gates

Promote only if:

- candidate beats baseline by the required margin on the target capability;
- safety/privacy suites do not regress;
- tool-use verification does not regress;
- fixed regressions pass;
- cost and latency stay within limits;
- held-out cases were not used for training;
- the report includes top failures and route labels;
- rollback target is recorded.

Do not promote on aggregate score alone. Inspect per-capability regressions and top failures.

## Failure Routing

For each top failure, assign a route:

| Failure type | Route |
|---|---|
| Forgot a known procedure, tool verification, or project convention | `self-coaching-self-learning` |
| Missing or weak eval coverage | `self-coaching-self-play` |
| Repeated model capability failure despite skills/tools/prompts | `self-coaching-training` |
| Ambiguous task or unstable judge | Human review / rubric rewrite |
| Safety or privacy failure | Block promotion and create fixed regression case |

Append concise failure summaries to `experience/ERROR.md` or `experience/LEARNINGS.md` when the finding is reusable. Do not paste full eval logs into experience files.

## Evaluating Training Pipelines

When `self-coaching-training` runs SFT/GRPO through the provided pipeline scripts, evaluate the candidate before any promotion:

```bash
# Example shape; adapt candidate identifier and suite to the project.
python scripts/run_agent_evals.py \
  --candidate <trained-model-or-endpoint> \
  --baseline <previous-model-or-endpoint> \
  --suite .self-coaching/cases/eval_cases.jsonl \
  --out .self-coaching/reports/eval_runs/<run_id>/report.json
```

Record the resulting `eval_run_id` in the training manifest and `experience/EXPERIMENT_LOG.md`.

## Common Pitfalls

1. **Evaluating on training data.** Keep fixed eval families separate from training and validation.
2. **Using only LLM judges.** Prefer deterministic checks and use judges with rubrics plus spot checks.
3. **Skipping failure routing.** Every top failure should become learning, self-play, training input, or human-review debt.
4. **Ignoring costs.** A candidate that is slightly better but much slower or costlier may not be promotable.
5. **No rollback target.** A pass without rollback still is not operationally safe.

## Verification Checklist

- [ ] Baseline and candidate are both recorded.
- [ ] Eval data is separate from training data.
- [ ] Report is machine-readable and versioned.
- [ ] Top failures are inspectable and routed.
- [ ] Deterministic checks run before judge scoring where possible.
- [ ] Promotion decision follows gates, not aggregate score alone.
- [ ] Training manifests reference the eval report before promotion.
