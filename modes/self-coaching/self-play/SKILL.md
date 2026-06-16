---
name: self-play
description: "Use when generating, replaying, mutating, critiquing, and curating challenging agent tasks or trajectories for evals, SFT data, or preference/RL data."
version: 0.3.1
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, self-play, data-curation, synthetic-data, trajectories, evaluation, pipeline-service]
    related_skills: [self-coaching, self-learning, self-evaluation, self-tuning, subagent-driven-development]
required_environment_variables:
  - name: ORCHESTRATOR_SELFPLAY_BACKEND
    required_for: pipeline-self-play
    optional: true
    rationale: "mock (default) | pipeline. Selects in-process mock vs Self-Questioning Pipeline Service."
  - name: PIPELINE_SERVICE_URL
    required_for: pipeline-self-play
    optional: true
    rationale: "Pipeline service base URL (e.g. http://host:8001). Alias: SELF_QUESTIONING_URL."
  - name: MOCK_SELF_PLAY_URL
    required_for: mock-http-self-play
    optional: true
    rationale: "HTTP mock on :8767 — generate-suite (sparse) vs generate (batch). Unset → in-process MockSelfPlayEngine."
  - name: PIPELINE_DRY_RUN
    required_for: pipeline-self-play
    optional: true
    rationale: "Set 1 for safe connectivity smoke — no GPU/LLM work."
  - name: PIPELINE_POLL_INTERVAL_S
    required_for: pipeline-self-play
    optional: true
    rationale: "Job status poll interval. Default 5."
  - name: PIPELINE_POLL_TIMEOUT_S
    required_for: pipeline-self-play
    optional: true
    rationale: "Max wait for pipeline job completion. Default 3600."
---

# Self-Coaching: Self-Play and Data Curation

## Overview

Self-play creates challenging tasks and trajectories from observed weaknesses. It should generate evaluation and training candidates, not automatically train on them.

In this repository the self-play **module** is wired into the coaching loop in two places (sparse E-path and batch T-path). It can run against:

| Backend | When | What you get locally |
|---------|------|----------------------|
| **mock** (default) | Local dev, CI | Cases/trajectories in `.self-coaching/` + `proceed` via `status` |
| **mock-http** | Split-stack smoke | Same as mock via `MOCK_SELF_PLAY_URL` |
| **pipeline** | Staging/production | Remote job on Self-Questioning Pipeline Service; **`proceed: true/false` only** — data stays in remote Supabase |

A real self-play loop has five separable jobs: generate tasks, solve them, critique outputs, refine ideal trajectories, and curate/split records. Keep these roles separate when possible so the same model is not inventing, solving, judging, and approving its own data without checks.

**Implementation reference:** `docs/project/self-play-pipeline-implementation.md` · API: `services/SELF_QUESTIONING_SERVICE_API.md`

## Runtime module — how the coaching loop uses self-play

The evolution loop does **not** call self-play on every tick. It triggers self-play only when thresholds are met:

| ID | Path | Trigger | Module call | Purpose |
|----|------|---------|-------------|---------|
| **C06** | E-path (sparse) | `0 < \|Σ\| ≤ σ_play` after eval failures | `generate_suite` | Failure-conditioned adversarial variants **before** `learn()` |
| **C07** | T-path (batch) | Buffer `\|B\| < β` while idle | `generate_batch` | Top up tuning buffer **before** `train()` |

Code paths:

- C06 → `modes/self-coaching/e_path.py` → `self_play_factory.run_suite_self_play()`
- C07 → `modes/self-coaching/t_path.py` → `self_play_factory.run_batch_self_play()`
- Orchestrator collect → `client.self_play(n=…)` → pipeline adapter when `ORCHESTRATOR_SELFPLAY_BACKEND=pipeline`

Factory resolution (`modes/self-coaching/self_play_factory.py`):

1. Explicit `self_play_engine` injection (tests/coach clock)
2. `ORCHESTRATOR_SELFPLAY_BACKEND=pipeline` → `SelfPlayPipelineEngine`
3. `MOCK_SELF_PLAY_URL` / `SELF_PLAY_BASE_URL` → HTTP mock
4. Else → in-process `MockSelfPlayEngine`

### Proceed signal (what the agent should check)

After self-play completes, the loop needs to know whether to **advance** to the next step (`learn`, `train`, etc.). Check:

```python
result.get("proceed") is True
# or: from services.adapters import pipeline_job_succeeded
```

**Mock backend** — success when `status` is `generated` (batch) or `registered` (sparse). Local trajectories are written to `.self-coaching/curated/staging.jsonl` and merged into Σ or B.

**Pipeline backend** — success when all pipeline stages succeed:

```json
{
  "status": "generated",
  "proceed": true,
  "pipeline_service": true,
  "job_id": "a1b2c3…",
  "stage_results": { "1": true, "2": true, "3": true },
  "count": 4
}
```

On failure (`proceed: false`):

- **E-path:** loop returns `status: held` — **skip learn** for this tick
- **T-path:** loop returns `held: true` — **skip train** for this tick

Pipeline jobs do **not** mirror rows into local `staging.jsonl`. Generated data remains in the pipeline host's Supabase (`query_bank`). Do not wait for local case files when `pipeline_service: true`.

### Agent decision guide

| Situation | Action |
|-----------|--------|
| `proceed: true` after C06 | Continue E-path → call **self-learning** (`learn`) on current Σ |
| `proceed: false` after C06 | **Hold** — do not learn; inspect `job_id`, `error`, pipeline logs |
| `proceed: true` after C07 (pipeline) | Continue loop policy (eval/train per orchestrator); buffer may still be empty locally |
| `proceed: true` after C07 (mock) | Buffer rows appended from `staging.jsonl` → eligible for **self-tuning** when `\|B\| ≥ β` |
| `proceed: false` after C07 | **Hold** — do not train; retry or escalate |

### Configuration (pipeline backend)

```bash
# Minimal live profile — copy scenarios/demo.pipeline.env.example
export LOOP_SERVICE_MODE=live
export ORCHESTRATOR_SELFPLAY_BACKEND=pipeline
export PIPELINE_SERVICE_URL=http://10.110.158.146:8001
export PIPELINE_POLL_INTERVAL_S=5
export PIPELINE_POLL_TIMEOUT_S=3600

# Safe smoke (no real GPU/LLM):
export PIPELINE_DRY_RUN=1
python scripts/pipeline_self_play_smoke.py
```

| Variable | Role |
|----------|------|
| `ORCHESTRATOR_SELFPLAY_BACKEND` | `mock` (default) or `pipeline` |
| `PIPELINE_SERVICE_URL` | Pipeline API base (`/api/pipeline/submit`, `/status/{job_id}`) |
| `PIPELINE_BATCH_TRAIN_EVAL_FLAG` | C07 data source: default `train` |
| `PIPELINE_TRAIN_EVAL_FLAG` | C06 data source: default `eval` |
| `PIPELINE_DRY_RUN=1` | Submit dry-run jobs only |

In `LOOP_SERVICE_MODE=live`, if `PIPELINE_SERVICE_URL` is set and backend is unset, backend auto-infers to `pipeline`.

### C06 prerequisite (pipeline only)

Mock sparse self-play seeds from a **local failure trajectory** (`user_query`, `trajectory`, `eval_score`). The pipeline reads **eval messages from Supabase** on the pipeline host (stage 1). Before non-dry production runs, ensure eval failures are ingested into that store.

### Smoke and health

```bash
# Adapter + batch + suite (dry_run)
PIPELINE_DRY_RUN=1 python scripts/pipeline_self_play_smoke.py

# HTTP contract probes (opt-in)
PIPELINE_INTEGRATION_TESTS=1 pytest tests/integration/test_pipeline_service_availability.py -v

# Coach clock with pipeline env loaded
python modes/coach/clock.py run --root <coaching-root> --json
# Expect: batch_self_play_proceed: true
```

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

- `experience/ERROR.md` and `experience/LEARNINGS.md` created by `self-learning/SKILL.md`;
- eval failure reports from **self-evaluation**;
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
8. **Route.** Fixed cases go to `self-evaluation/`; training examples go to `self-tuning/`.

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

- To evaluation: append fixed, privacy-checked cases to `.self-coaching/cases/eval_cases.jsonl` and load **self-evaluation**.
- To training: append curated demonstrations to `.self-coaching/curated/train.jsonl` or preference records to the training pool, then load `self-tuning/SKILL.md`. *(Mock backend only for pipeline-sourced data — pipeline rows stay remote until a future export path exists.)*
- To self-learning: if self-play reveals a missing procedure, patch the relevant skill instead of making only training data.
- **After C06 with `proceed: true`:** hand off to **self-learning** on the support set Σ.
- **After C07 with `proceed: true` (mock):** buffer B may be ready for **self-tuning** when size ≥ β.
- **After any `proceed: false`:** do not advance the gated next step; record `job_id` / `error` in the loop audit (`e_path_last.json` or `t_path_last.json`).

## Common Pitfalls

1. **Training on exact eval cases.** Keep held-out eval cases separate forever.
2. **Letting one model self-approve.** Separate generator/solver/judge when possible and spot-check judge-only labels.
3. **Keeping verbose transcripts.** Store compact observable traces and final answers.
4. **Rewarding fluency.** Rubrics must score verified success, not style.
5. **Skipping provenance.** Every record needs source, privacy, license, and split labels.
6. **Expecting local JSONL from pipeline backend.** Use `proceed` only; data is remote unless backend is mock.
7. **Advancing after failed pipeline job.** Always gate on `proceed` before learn or train.

## Verification Checklist

- [ ] Each case has capability, hidden pitfall, rubric, and success/failure criteria.
- [ ] Privacy, license, and provenance metadata are present.
- [ ] Solver did not receive ideal answers.
- [ ] Train/validation/eval splits are separated by task family.
- [ ] Judge-only labels have spot checks or second-judge agreement.
- [ ] Evaluation cases were not copied into training data.
- [ ] Training handoff records contain observable behavior, not private hidden chain-of-thought.
- [ ] **Loop:** checked `proceed` (or mock `status`) before calling learn or train.
- [ ] **Pipeline:** if `pipeline_service: true`, did not assume local `staging.jsonl` was populated.
- [ ] **C06 pipeline:** upstream eval messages exist in pipeline Supabase before non-dry runs.
