---
name: self-coaching
description: "Agent-agnostic skill. Coaches any capable agent through Loading Gate, Performance, Data Pool, Local Model, Deploy Gate, Trainer, LOGs, and Results (experience logs); git worktrees; user-authorized merge and model/data updates."
version: 0.3.1
author: Self-Coaching Skill Pack
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, agent-evolution, evaluation, training, evolution-loop, gated-pipeline]
    related_skills: [self-learning, self-play, self-evaluation, self-tuning]
required_commands:
  - name: python3
    minimum_version: "3.10"
    required_for: all-modes
    rationale: "Mock loop runner; demo + completeness audit."
  - name: bash
    required_for: install-and-mock
    rationale: "install-skill-pack.sh and mock-self-coaching-demo.sh wrappers. PowerShell wrapper available on Windows."
  - name: git
    required_for: all-modes
    rationale: "Worktree-based experiment isolation per umbrella §10."
required_environment_variables:
  - name: AGENT_API_TOKEN
    required_for: real-api-mode
    optional: true
    rationale: "Bearer auth for AgentEvals + self-learning + self-play + AERL. Unset → mock mode."
  - name: AGENTEVALS_BASE_URL
    required_for: real-api-mode
    optional: true
    rationale: "Real AgentEvals service base URL. Unset → in-process MockAgentEvalsEngine."
  - name: SELF_LEARNING_BASE_URL
    required_for: real-api-mode
    optional: true
    rationale: "Real self-learning service. Unset → ModuleClient mock."
  - name: SELF_PLAY_BASE_URL
    required_for: real-api-mode
    optional: true
    rationale: "Real self-play service. Distinct endpoints for generate-suite (sparse) vs generate (batch)."
  - name: AERL_BASE_URL
    required_for: real-api-mode
    optional: true
    rationale: "Real AERL training service. Synchronous train + holdout."
  - name: LOOP_HOLDOUT_TIMEOUT_S
    required_for: real-api-mode
    optional: true
    rationale: "Holdout poll budget. Default 5s for mock, set 300s for real."
---

# Self Coaching
## Overview

Self-coaching is a disciplined improvement loop for autonomous agents. It turns experience into durable capability by deciding what should be remembered, what should become a skill, what should become an evaluation, what should become curated training data, and what should become a code/tool/model change.

This skill supports three related modes:

1. **Self-learning** — learn from previous experience: bugs resolved, user preferences, tool quirks, environment conventions, workflows, and skill extensions.
2. **Self-playing** — generate, replay, mutate, and critique challenging requests to create evaluation cases and training trajectories.
3. **Self-training** — use curated data to fine-tune or reinforce models via SFT/RL pipelines, with evaluation gates before deployment.

Self-coaching is not uncontrolled self-modification. It is a gated pipeline: observe → diagnose → encode → evaluate → curate → train → deploy only if metrics improve.

## When to Use

Use this skill when:

- An agent repeatedly fails, hesitates, or needs user steering on similar tasks.
- The user corrects the agent and the correction should persist.
- A bug was hard to resolve and the root cause/procedure should be reusable.
- A skill was extended, created, patched, or found stale.
- An evaluation identifies low-performance categories or regressions.
- The agent needs to generate harder synthetic tasks or adversarial self-play cases.
- You are building an autoresearch-style loop: propose tasks, solve them, critique them, curate trajectories, train, evaluate, repeat.
- You need a safe process for turning agent experience into memory, skills, tests, eval datasets, SFT data, or RL preference data.

Do **not** use this skill for:

- One-off task notes that will be stale within days.
- Saving raw transcripts without filtering or consent.
- Training on secrets, private data, credentials, or copyrighted/proprietary content without permission.
- Blindly creating memories or skills after every task.
- Deploying a newly trained model without evaluation and rollback.

## Validating the Loop on Mocks

Before reasoning about the loop on a real agent, validate
that the gated pipeline works end-to-end on mock services.
This is the single command:

```bash
python -m self_coaching.demo
```

Requires `pip install -e .` from the repo clone for
`python -m self_coaching.demo` (the installer runs this with
`--hermes --with-mock`). The mock harness itself is always
installed at `$SKILL_ROOT/mock-services/` by
`bash scripts/install-skill-pack.sh --hermes`. See
`docs/guides/install-as-hermes-skill.md`.

The runner spins up an isolated demo state at
`mock-services/demo-loop/`, runs `scenarios/full_loop.json`
through the E-path (self-learning) and T-path (self-play +
training + holdout) phases, then audits via
`tools/loop_completeness.py`.

**Expected on success:**

- exit code 0
- `mock-services/demo-loop/.self-coaching/loop/completeness_report.json`
with `status: "PASS"` covering matrix rows C01–C18
- `mock-services/demo-loop/.self-coaching/loop/demo_summary.md`
with a one-paragraph human summary
- registry version bump in `mock-services/demo-loop/agents/demo-agent/meta.json`

If completeness_report.json status != PASS, do NOT proceed to
real-API mode. Failing rows tell you exactly which gate broke.
See `docs/project/self-coaching-demo-pipeline-plan.md` §7 (Completeness Matrix) for
what each Cnn check means.

For HTTP-transport validation (real-service-shaped):

```bash
python -m self_coaching.demo --with-http
```

This stands up four mock services on configurable ports and
exercises the same loop with network I/O instead of in-process
calls. Same exit conditions, same artifacts.

## Invocation Contract

> **Terminology:** **Invocation modes** (below) are how you *use this skill pack* (read policy vs run mock demo vs real APIs). They are **not** [loop execution modes](../../docs/design/self_coaching_mode.md#loop-execution-modes) (autonomous / scheduler / manual — who runs the coach loop). See [design glossary](../../docs/design/README.md#glossary).

A calling agent can use this skill in three **invocation** modes. Pick the
mode based on what you have available; you can always
"upgrade" from a lower mode to a higher one without
re-loading the skill.

### Mode 1 — Policy reference (read-only)

**Use when:** reasoning about agent improvement during a
session, deciding whether an experience should become a
memory / skill / eval case / training row, applying the
gated pipeline mentally without executing anything.

**Setup:** none. Just load `SKILL.md`.

**External services:** none.

**Env vars:** none.

**Success criterion:** the agent applies the methodology
(Observe → Diagnose → Encode → Verify → Curate → Train)
to its decision and produces an artifact (memory, skill
patch, test, eval case, or curated row) that follows
the discipline in §4 of this skill.

### Mode 2 — Mock validation (deterministic)

**Use when:** validating that this skill is installed
correctly, reproducing the demo loop, establishing a
baseline before real-API migration, or running the loop
in CI on a host with no external network access.

**Setup:**

```bash
python -m self_coaching.demo
```

Requires `pip install -e .` from the repository clone.

**External services:** none (in-process mocks). Optionally
`--with-http` spins up four mock HTTP services on
localhost.

**Env vars:** optional `MOCK_AGENTEVALS_PORT`,
`MOCK_SELF_LEARNING_PORT`, `MOCK_SELF_PLAY_PORT`,
`MOCK_AERL_PORT` to override default ports when running
`--with-http`. None required.

**Success criterion:** exit code 0;
`mock-services/demo-loop/.self-coaching/loop/completeness_report.json`
has `status: "PASS"`; all 18 C-rows (C01-C18) recorded;
registry version bump visible in
`agents/demo-agent/meta.json`.

**Failure modes:** if `completeness_report.json` status
is FAIL, the failing C-row identifies which gate broke.
See `docs/project/self-coaching-demo-pipeline-plan.md` §7
for what each Cnn check means. **Do not proceed to Mode 3
until Mode 2 passes.**

### Mode 3 — Real-API mode (post-migration)

**Use when:** running the loop against real production
services for staging or production deployments. Requires
the staged migration in `docs/project/integration-plan.md`
to be complete (or at least the M1+M2 phases for E-path,
all of M1-M4 for full E+T loop).

**Setup:**

```bash
export AGENT_API_TOKEN="<your-token>"
export AGENTEVALS_BASE_URL="<https://agentevals.example.com>"
export SELF_LEARNING_BASE_URL="<https://self-learning.example.com>"
export SELF_PLAY_BASE_URL="<https://self-play.example.com>"
export AERL_BASE_URL="<https://aerl.example.com>"
export LOOP_HOLDOUT_TIMEOUT_S=300

python -m self_coaching.demo
```

(Same runner; behavior switches based on which `*_BASE_URL`
env vars are set. Any unset URL falls back to its mock.)

**External services:** AgentEvals, self-learning,
self-play, AERL (any subset; unset services fall back
to mocks for graceful partial migration).

**Env vars:** see Setup. `AGENT_API_TOKEN` required when
any real BASE_URL is set. `LOOP_HOLDOUT_TIMEOUT_S` default
300s for real services (5s is too tight — see W3 in the
migration plan).

**Success criterion:** same as Mode 2 — exit 0 and
`completeness_report.json` status PASS — but now backed by
real services. C18 semantic gate compares real
candidate_eval.score vs current_eval.score from the real
AgentEvals run.

**Failure modes:** if a real service is unreachable or
returns a malformed response, the integration mapper in
`integration/mapping.md` should surface a clear error
(reject unknown fields, do not silently drop). Do not
treat a Mode 3 failure as a Mode 2 regression — the mocks
are still the baseline of correctness.

### Mode-selection decision tree

```
Need to reason about a single experience?       → Mode 1
Verifying install / reproducing demo / CI?      → Mode 2
Promoting against real metrics on staging?      → Mode 3
Migrating from mock to real one module at a time → Mode 3
   (with partial BASE_URL coverage)
```

## Self-Coaching Loop

### 1. Observe

Capture improvement signals from:

- User corrections: "remember this", "don't do that", "we prefer X".
- Repeated clarification questions.
- Tool failures, command errors, or environment-specific quirks.
- Bugs resolved after several failed attempts.
- Long tasks that required non-obvious workflows.
- Evaluation failures or low-scoring benchmark examples.
- Subagent critiques, code reviews, or postmortems.
- Skill load failures, stale instructions, or missing pitfalls.

Ask:

- What exactly went wrong or slowed the agent down?
- Was the issue knowledge, procedure, tool access, reasoning, prompt design, memory, or model capability?
- Is the lesson stable enough to persist?
- Can this lesson be verified later?

### 2. Diagnose and Classify

Classify the signal into one or more durable artifacts:

| Signal | Best artifact | Example |
|---|---|---|
| Stable user preference | Memory | "User prefers concise terminal-friendly answers." |
| Stable environment fact | Memory | "This Windows host runs terminal commands through git-bash, not PowerShell." |
| Reusable workflow | Self-coaching | "How to debug Hermes TUI slash commands." |
| Missing steps in an existing workflow | Skill patch | Add pitfall or verification step. |
| Code defect | Bug fix + regression test | Tool fails on Windows path handling. |
| Weak agent behavior | Eval case | Agent forgets to verify file writes. |
| Repeated manual operation | Tool/plugin/MCP | Add command to query a service instead of manual curl. |
| Model weakness | Training example | Failed trajectory plus corrected solution. |
| Ambiguous task pattern | Self-play task family | Generate variations to stress the behavior. |

If the artifact would be stale in a week, do not save it as memory. Use session search or task notes instead.

### 3. Encode the Smallest Durable Improvement

Choose the smallest sufficient change:

1. **Memory** for stable facts and preferences.
2. **Skill patch** before creating a new skill if an existing skill mostly fits.
3. **New skill** for a reusable, named procedure with triggers, steps, pitfalls, and verification.
4. **Test/eval** for behavior that should not regress.
5. **Tool/plugin** when repeated manual actions should become executable capability.
6. **Training data** only after examples are curated, de-duplicated, and privacy-checked.
7. **Model training** only when prompt/skill/tool/test changes are insufficient or the goal is model capability improvement.

### 4. Verify

Before considering the improvement successful:

- Re-run the failed task or a minimal reproduction.
- Add or update a regression test if code changed.
- Add an eval case if behavior changed.
- Validate the skill loads and has actionable instructions.
- Check that the new memory is compact and durable.
- Compare before/after metrics if an evaluation pipeline exists.

### 5. Curate

Good self-coaching depends on high-quality data. Curate aggressively:

- Keep examples with clear task, context, tools used, failure mode, correction, and ideal response.
- Remove secrets, credentials, PII, and irrelevant logs.
- Normalize paths, hostnames, and user-specific details unless they are the point of the example.
- Deduplicate near-identical examples.
- Label examples by capability: planning, tool use, coding, debugging, eval repair, instruction following, safety, memory use, etc.
- Include negative examples only when paired with an explanation and preferred behavior.
- Prefer small high-signal examples over huge transcripts.

### 6. Train or Improve Policy

Training is optional. Many improvements should remain as memory, skills, tools, tests, or prompts.

If training is appropriate, route curated data into:

- **SFT**: demonstrations of ideal behavior, corrected trajectories, tool-use traces, debugging workflows.
- **Preference/RL data**: chosen/rejected responses, reward labels, rubric scores, evaluator critiques.
- **Process supervision**: intermediate reasoning or action-step labels when available and safe.
- **Tool-use tuning**: examples of when to call tools, how to verify, and when to ask clarification.

Use evaluation gates before promotion:

1. Baseline model on fixed eval set.
2. Train candidate model.
3. Evaluate candidate on held-out tasks and regression suite.
4. Compare against baseline and previous production model.
5. Deploy only if improvements exceed thresholds without safety regressions.
6. Keep rollback path.

## Self-Learning Playbook

Use this after real tasks.

### Post-Task Reflection Questions

- Did the user correct a stable preference or convention?
- Did I discover an environment quirk that will matter again?
- Did I solve a bug with a non-obvious root cause?
- Did I use a sequence of 5+ tool calls that should become a repeatable workflow?
- Did an existing skill lack a step, command, or pitfall?
- Did I fail because I lacked a tool or API workflow?
- Would a future agent benefit from an eval case based on this task?

### Artifact Decision Rules

- **Save memory** when the fact is durable, compact, and specific.
- **Patch a skill** when the process exists but was incomplete or stale.
- **Create a skill** when the process is reusable, multi-step, and not covered by existing skills.
- **Create an eval** when failure should be measurable and prevented from recurring.
- **Create training data** when the task demonstrates a generalizable capability gap.
- **Do nothing durable** when the lesson is temporary, obvious, or too context-specific.

### Memory Guidelines

Good memory:

- "User prefers simple terminal-renderable responses without attachment tags."
- "Project X uses scripts/run_tests.sh for tests; direct pytest diverges from CI."

Bad memory:

- "Fixed issue #123 today."
- "Opened PR #456."
- "Remember the temporary path from this one run."

## Self-Playing Playbook

Self-play creates challenge data. It should be tied to observed weaknesses or target capabilities.

### Sources for Self-Play Tasks

- Failed eval cases.
- User tasks that took many turns or required corrections.
- Bug postmortems.
- Stale or missing skill instructions.
- Areas where tool use was inefficient or unverified.
- Regression categories from production incidents.

### Self-Play Roles

A useful self-play setup often separates roles:

1. **Task generator** — creates challenging but realistic tasks.
2. **Solver agent** — attempts the task under normal constraints.
3. **Critic/evaluator** — scores the solution against a rubric.
4. **Refiner** — writes the ideal solution or corrected trajectory.
5. **Curator** — filters for safety, quality, novelty, and train/eval suitability.

These can be subagents, separate Hermes profiles, or external services.

### Task Generation Template

For each task family, store:

- Capability targeted.
- Required tools or environment.
- Hidden pitfalls.
- Success criteria.
- Rubric.
- Minimal reproducible setup.
- Expected high-quality solution outline.
- Safety/privacy constraints.

Example self-play prompt skeleton:

```text
Generate 10 realistic tasks that stress <capability> for an autonomous coding agent.
Each task must include:
- user request
- setup/context
- hidden pitfall
- success criteria
- scoring rubric
- expected artifacts
Avoid secrets, real credentials, or private data.
Prefer tasks that require verification, not just explanation.
```

### Self-Play Data Schema

Use a structured record format such as JSONL:

```json
{
  "id": "tool-verification-001",
  "source": "self_play",
  "capability": ["tool_use", "verification"],
  "user_request": "Create a config file and confirm it is valid YAML.",
  "context": "Agent has file and terminal tools.",
  "constraints": ["Do not claim success without verification."],
  "rubric": {
    "must": ["writes file", "validates syntax", "reports path"],
    "fail": ["claims success without verification"]
  },
  "trajectory": [],
  "ideal_response": "...",
  "labels": {
    "difficulty": "medium",
    "use_for": ["eval", "sft"],
    "privacy_checked": true
  }
}
```

## Agent Evaluation Pipeline

A self-coaching agent needs a solid evaluation pipeline or service it can trigger/access.

### Minimum Evaluation Service Contract

The evaluation service should support:

- Submitting a candidate agent/model/config.
- Running fixed regression suites.
- Running capability-specific benchmark suites.
- Running self-play generated tasks after curation.
- Capturing tool traces and final outputs.
- Scoring with deterministic checks where possible.
- Scoring with LLM judges only when rubric-grounded.
- Comparing candidate vs baseline.
- Returning machine-readable results.
- Publishing a human-readable report.

### Suggested Evaluation API Shape

If building an internal service, expose operations like:

```text
POST /eval/runs
  candidate: model/provider/config/agent_version
  suites: [regression, tool_use, coding, debugging, memory, safety]
  dataset_refs: [...]
  budget: max_tasks/max_tokens/max_time

GET /eval/runs/{run_id}
GET /eval/runs/{run_id}/report
GET /eval/runs/{run_id}/failures
POST /eval/runs/{run_id}/promote-if-passing
```

### Evaluation Result Schema

```json
{
  "run_id": "eval_2026_...",
  "candidate": "model-or-agent-version",
  "baseline": "previous-version",
  "status": "passed",
  "scores": {
    "overall": 0.82,
    "tool_use": 0.91,
    "debugging": 0.74,
    "safety": 0.99
  },
  "regressions": [],
  "top_failures": [
    {"case_id": "debug-017", "reason": "missed root cause", "artifact": "..."}
  ],
  "recommendation": "promote | do_not_promote | needs_review"
}
```

### Evaluation Gates

Do not promote a change if:

- Safety/privacy score regresses.
- Tool-use verification score regresses significantly.
- The candidate improves self-play tasks but fails fixed regressions.
- The improvement is only visible to the same judge model used to generate training labels.
- The dataset has contamination from the eval set.

## Self-Training Pipeline

Use training only after data is curated and evaluation is ready.

### SFT Pipeline

1. Collect candidate trajectories from real tasks and self-play.
2. Remove secrets, PII, and low-quality examples.
3. Convert to chat/tool-call format expected by the target trainer.
4. Split into train/validation/test by task family, not random transcript chunking.
5. Train with conservative hyperparameters.
6. Evaluate against held-out and regression suites.
7. Inspect failures manually before deployment.
8. Version dataset, model, config, and eval report together.

### RL / Preference Pipeline

1. Generate multiple candidate solutions for the same task.
2. Score with rubric-based evaluator and/or human review.
3. Store chosen/rejected pairs or scalar rewards.
4. Filter out ambiguous or judge-unstable examples.
5. Train with DPO/ORPO/GRPO/PPO-style scripts depending on infrastructure.
6. Evaluate on fixed suites and adversarial/self-play suites.
7. Monitor for reward hacking and style overfitting.

### Autoresearch-Style Loop

A practical loop, inspired by automated research systems:

```text
while improvement_budget_remaining:
  1. Mine failures from evals and prior sessions.
  2. Propose hypotheses for why failures occurred.
  3. Generate self-play tasks targeting those hypotheses.
  4. Solve tasks with current agent/model.
  5. Critique and score trajectories.
  6. Curate high-signal examples.
  7. Update skills/tools/prompts/tests or train candidate model.
  8. Run evaluation service.
  9. Promote only if candidate beats baseline and passes safety gates.
  10. Archive artifacts and write a short postmortem.
```

Prefer cheap improvements first: skills, tests, prompts, and tools often outperform model training for agent-specific failures.

## Data Curation Rules

### Keep

- Clear examples with reproducible context.
- Tasks that stress known weak capabilities.
- Corrected trajectories where the final behavior is better than the original.
- Tool-use traces that demonstrate verification.
- Failures with unambiguous root cause.
- Rubric-scored examples with stable labels.

### Reject

- Examples containing secrets, credentials, private messages, or proprietary code without permission.
- Huge transcripts with no clear learning signal.
- Ambiguous tasks where multiple answers are equally valid.
- Duplicates or near-duplicates.
- Examples that reward verbosity over correctness.
- Data generated by the same evaluator with no independent validation.
- Cases where the preferred answer violates user instructions or safety policy.

### Label

Recommended labels:

- `source`: real_task, self_play, eval_failure, user_correction, bug_postmortem
- `capability`: planning, coding, debugging, tool_use, memory, skill_use, eval_repair, safety, communication
- `artifact_target`: memory, skill, test, eval, sft, preference, tool, code
- `difficulty`: easy, medium, hard, adversarial
- `privacy_checked`: true/false
- `human_reviewed`: true/false
- `use_for`: eval, train, validation, reference_only

## Operational Workflow

When applying this skill in a real project, prefer an explicit artifact layout and reproducible commands over informal notes.

### Suggested Artifact Layout

Use the target repository's existing conventions if present. If none exist, start with:

```text
.self-coaching/
  cases/
    eval_cases.jsonl              # fixed or candidate eval cases
    self_play_cases.jsonl         # generated tasks before curation
  curated/
    train.jsonl                   # SFT/preference training split
    validation.jsonl              # validation split
    test.jsonl                    # held-out split, never train on this
  reports/
    eval_runs/<run_id>/report.json
    eval_runs/<run_id>/summary.md
  postmortems/
    <date>-<slug>.md
  manifests/
    dataset_manifest.json
    training_run_manifest.json
```

Keep project-local artifacts in the project, not in agent memory. Use memory only for compact durable facts and preferences.

### Concrete Hermes-Oriented Actions

Use these action patterns:

- Stable preference or environment fact → save compact memory.
- Missing or stale procedure → patch the relevant skill immediately.
- New reusable workflow → create a skill with triggers, steps, pitfalls, and verification.
- Agent behavior failure → write an eval case under `.self-coaching/cases/`.
- Training-worthy trajectory → write a curated JSONL record under `.self-coaching/curated/` after privacy review.
- Model/config candidate → trigger the eval service or local eval script before promotion.

Example local eval command shape:

```bash
python scripts/run_agent_evals.py \
  --candidate current-agent-or-model \
  --baseline previous-agent-or-model \
  --suite .self-coaching/cases/eval_cases.jsonl \
  --out .self-coaching/reports/eval_runs/<run_id>/report.json
```

If no eval runner exists yet, create a minimal one before training: it should execute cases, record tool traces/final outputs, score deterministic assertions, and emit a JSON report with pass/fail status.

### Training Data Record Contracts

SFT records should include observable behavior and final answers, not hidden private chain-of-thought. Prefer action traces, tool-call summaries, critiques, and concise rationales.

Minimum SFT-style record:

```json
{
  "id": "sft-001",
  "source": "eval_failure",
  "messages": [],
  "tool_trace_summary": [],
  "ideal_response": "...",
  "capability": ["debugging", "tool_use"],
  "privacy_checked": true,
  "license": "internal-permitted",
  "use_for": ["train"]
}
```

Minimum preference/RL record:

```json
{
  "id": "pref-001",
  "prompt": "...",
  "chosen": "...",
  "rejected": "...",
  "rubric": "...",
  "judge_model": "...",
  "human_reviewed": false,
  "privacy_checked": true,
  "use_for": ["train"]
}
```

### Evaluation and Promotion Gates

Before promoting a trained model, prompt, skill, or tool change:

- Candidate must beat baseline on target capability.
- Candidate must not regress fixed safety/privacy/tool-verification suites.
- Candidate must pass held-out tasks not generated from the same examples used for training.
- Judge-only improvements require spot checks or a second judge.
- Eval cases must be kept separate from training data.
- The run must produce a versioned report and rollback target.

## Safety and Governance

Self-coaching can amplify mistakes if unmanaged. Apply these controls:

- Keep memory compact and user-approved when sensitive.
- Never train on secrets or credentials.
- Separate training sets from evaluation sets.
- Maintain fixed regression suites that are not generated by the current candidate model.
- Use human review for high-impact behavioral changes.
- Version all datasets, prompts, skills, models, and eval reports.
- Preserve rollback paths for model/config/tool changes.
- Record why an artifact was created, not just what changed.
- Periodically prune stale skills and low-quality examples.

## Common Pitfalls

1. **Saving everything as memory.** Memory is for durable facts, not task logs. Use skills, evals, datasets, or session search for other artifacts.

2. **Creating duplicate skills.** Search existing skills first. Patch an existing skill if it already owns the workflow.

3. **Training before evaluating.** A training loop without a stable eval service is just expensive guesswork.

4. **Using self-play data as both train and test.** This causes contamination. Hold out task families and maintain fixed regression suites.

5. **Rewarding style instead of capability.** Make rubrics objective and task-specific. Avoid judges that only prefer fluent answers.

6. **Ignoring tool verification.** Agent evals should check whether claimed side effects actually happened.

7. **Forgetting privacy.** Logs and transcripts often contain sensitive information. Redact before curation.

8. **Deploying on aggregate score only.** Inspect regressions by capability. A higher average can hide safety or reliability failures.

9. **Overfitting to one model/provider.** Skills and tools should improve agent behavior across models when possible.

10. **No rollback.** Every promoted model/config/tool/skill change needs a way back.

## Verification Checklist

Before ending a self-coaching cycle, verify:

- [ ] The observed issue is clearly described.
- [ ] The root cause is classified: memory, skill, tool, code, eval, data, or model.
- [ ] The smallest durable improvement was chosen.
- [ ] Any memory saved is compact, stable, and non-transient.
- [ ] Any skill created or patched has triggers, steps, pitfalls, and verification.
- [ ] Any eval case has a rubric and expected outcome.
- [ ] Any curated data is deduplicated and privacy-checked.
- [ ] Training/validation/eval splits are separated.
- [ ] Candidate changes were compared against baseline.
- [ ] Safety and regression gates passed.
- [ ] Artifacts are versioned and rollback is possible.

## One-Shot Recipes

### Turn a User Correction into Durable Learning

1. Identify whether it is a stable preference or task-specific correction.
2. If stable, save concise memory.
3. If procedural, patch or create a skill.
4. If it reveals wrong behavior, add an eval case.
5. Confirm the next response follows the corrected behavior.

### Turn a Hard Bug Fix into Reusable Knowledge

1. Write a short postmortem: symptom, false leads, root cause, fix, verification.
2. Add or update a regression test.
3. Patch the relevant debugging or project skill with the non-obvious lesson.
4. If the bug pattern is general, create an eval case.
5. Do not save issue numbers, PR numbers, or stale artifacts as memory.

### Turn Eval Failures into Self-Play Data

1. Cluster failures by capability and root cause.
2. Generate task variants that stress the failing capability.
3. Run solver agents on the variants.
4. Score with rubric and collect traces.
5. Keep only high-signal, privacy-safe examples.
6. Split some into eval, some into train, and some into validation.

### Decide Whether to Train

Train only if all are true:

- The failure appears across many tasks or cannot be solved cleanly with skills/tools/prompts.
- There is enough high-quality curated data.
- An evaluation pipeline can compare candidate vs baseline.
- Safety and regression checks exist.
- Deployment and rollback are defined.

Otherwise, prefer a skill, tool, prompt, test, or memory update.


## Tooling: Git and Bash (required)

The agent **must** use Bash for:

- Creating and managing worktrees, branches, and merges (`git` commands below).
- Running training with **shell redirection** so output goes to a file, e.g.  
  `(cd "<worktree-path>" && uv run train.py) > "logs/<run-id>.log" 2>&1`  
- Inspecting results with `Read` on the log file (prefer `offset` / small ranges), not streaming unbounded output into the model context.

## Runtime inputs

Collect once per session (or per experiment branch):

- `goal`: optimization objective
- `experiment_id`: short id (e.g. `20250424-01`) for branch and paths
- `metric_name` (default: `val_bpb`), `direction` (default: `lower`)
- `time_budget` / `max_iterations` / guardrails: as in **Strict guardrails**
- `trainer_git_dir` / `AUTORESEARCH_ROOT`: absolute path to your autoresearch (or compatible) clone — must be a git repo
- `experiment_worktree`: e.g. `worktrees/<experiment_id>` (path under skill root; **only** this tree is edited during the loop)
- `train_log_file`: e.g. `logs/<experiment_id>.log`

## Non-negotiable constraints

1. **Worktree boundary**: apply experiment edits and commits **only** inside `experiment_worktree` until the user approves merge. Do not change tracked files in the trainer repo on `main` during the loop except via the merge step after approval.
2. **Training command**: use the **exact pattern** in **Run one training experiment (log to file)**. Redirect **all** stdout and stderr to `logs/…`; parse metrics from that file. For `self-tuning/pipelines` (SFT/GRPO), use `scripts/run-pipeline.sh` or the per-pipeline `run.sh` so output still goes to the given log path (`LOG_FILE`)—same discipline, different entrypoint.
3. Experiments may run autonomously within guardrails until stop conditions.
4. One clear hypothesis per iteration; small, attributable commits in the **experiment** branch.
5. **Merge**: `git merge` of the experiment branch into `main` in the trainer repo (`AUTORESEARCH_ROOT`) **only after explicit user authorization**.
6. External deployment/promotion (artifacts, production pointers) also requires explicit approval (same or separate confirmation as merge, per user).

---

## One-time: trainer repo (`AUTORESEARCH_ROOT`)

Clone [karpathy/autoresearch](https://github.com/karpathy/autoresearch) **outside** this skill pack (see `upstream/README.md`). Export an absolute path:

```bash
export AUTORESEARCH_ROOT="${AUTORESEARCH_ROOT:-$HOME/src/autoresearch}"
```

If that directory is not yet a git repository, initialize once:

```bash
cd "${AUTORESEARCH_ROOT}"
git init
git add -A
git commit -m "baseline"
git branch -M main
```

If it is already a repo, skip this block.

## Create the experiment worktree (fork for this session)

From **skill root** (directory containing `SKILL.md`), with `EXPERIMENT_ID` and `AUTORESEARCH_ROOT` set. Use an **absolute** worktree path under the skill root:

```bash
EXPERIMENT_ID="run-01"
SKILL_ROOT="$(pwd)"
AUTORESEARCH_ROOT="${AUTORESEARCH_ROOT:?set AUTORESEARCH_ROOT to your autoresearch clone}"
EXPERIMENT_BRANCH="experiment/${EXPERIMENT_ID}"
WT_PATH="${SKILL_ROOT}/worktrees/${EXPERIMENT_ID}"

git -C "${AUTORESEARCH_ROOT}" worktree add -b "${EXPERIMENT_BRANCH}" "${WT_PATH}"
```

- All subsequent training edits use files under `"${WT_PATH}/"` (e.g. `train.py` in that worktree).
- The worktree at `worktrees/<experiment_id>/` is the only tree the agent should modify for this experiment.

## Run one training experiment (log to file)

Always capture full process output in a file (default layout):

```bash
# From skill root; set EXPERIMENT_ID to match the worktree you created
EXPERIMENT_ID="run-01"
SKILL_ROOT="$(pwd)"
WT_PATH="${SKILL_ROOT}/worktrees/${EXPERIMENT_ID}"
LOG_FILE="${SKILL_ROOT}/logs/${EXPERIMENT_ID}.log"

mkdir -p logs
( cd "${WT_PATH}" && uv run train.py ) > "${LOG_FILE}" 2>&1
```

- Parse `metric_name` and `peak_vram_mb` (or equivalent) from `"${LOG_FILE}"` with `Read`, not from raw terminal flood.
- If `uv` / env must run from a specific cwd, only `cd` to **`WT_PATH`**, not to the trainer repo on `main`.

**Dependency / data prep** (run against `AUTORESEARCH_ROOT`, typically once):

```bash
AUTORESEARCH_ROOT="${AUTORESEARCH_ROOT:?set AUTORESEARCH_ROOT}"
uv --directory "${AUTORESEARCH_ROOT}" sync
uv --directory "${AUTORESEARCH_ROOT}" run prepare.py
```

(The worktree shares the trainer repo’s git metadata; experiment files live in `WT_PATH`.)

## Training pipelines (SFT, GRPO, **AERL** trainer API)

For **LLM / agent** stages beyond the default vendored `train.py` loop, this pack includes `self-tuning/pipelines/` (same file bundle as **Layout** in `README.md`: **AERL** `registry.yaml` with `service.url`, `_lib.sh`, per-pipeline `pipeline.yaml` + `run.sh`):

- **Registry:** `self-tuning/pipelines/registry.yaml` lists pipeline ids (`sft`, `grpo`, …) and **AERL** `service.url` (default trainer base, typically `http://localhost:8004`).
- **Per pipeline:** `self-tuning/pipelines/<id>/pipeline.yaml` (HTTP + optional local entrypoints) and `self-tuning/pipelines/<id>/run.sh` (redirects **all** stdout/stderr to `LOG_FILE`).
- **Shared helpers:** `self-tuning/pipelines/_lib.sh` (sourced by runners; not invoked directly).
- **Service contract (env):** copy `self-tuning/services/example.env` to `self-tuning/services/.env` (ignored by git). Set `TRAINER_BASE_URL` / `TRAINER_API_KEY` for the trainer HTTP API; set `OPENAI_BASE_URL` / `OPENAI_API_KEY` for OpenAI-compatible **rollout** endpoints used by your agent loop (same “replace `base_url`” pattern as **AERL** and other OpenAI-compatible stacks).

**Default (HTTP trainer):** `run.sh` issues `POST {TRAINER_BASE_URL}/v1/pipelines/<id>/run` with JSON `{"argv":[…]}` (see each `pipeline.yaml`). Ensure your trainer implements that contract or adapt `_lib.sh`.

**Local AERL trainer tree (optional):** `export PIPELINE_MODE=local` (or `aerl`) and `export AERL_ROOT=/path/to/AERL` after your **AERL** trainer layout is installed; then the same `run.sh` paths execute the `examples/math/…` entrypoints inside `AERL_ROOT`.

```bash
bash scripts/run-pipeline.sh grpo logs/<experiment_id>-grpo.log scheduler.type=local
bash scripts/run-pipeline.sh sft logs/<experiment_id>-sft.log
```

Use the **same log redirection discipline** as **Run one training experiment**: parse metrics from `logs/…` with `Read` in small ranges; do not paste full training transcripts into chat. If an experiment branch needs **forked YAML or launchers**, keep those files under the active **`experiment_worktree`** (or a path your policy allows) and pass their paths through `argv` / trainer config consistently.

## Stage-gated workflow (strict)

For each iteration:

1. Propose one experiment (hypothesis, files/lines, risk).
2. Edit **only** under `experiment_worktree` (e.g. `worktrees/<id>/train.py`).
3. Commit in the **experiment** branch if your workflow uses commits (recommended for auditable diffs).
4. Run training using **Run one training experiment** (redirect to `logs/<experiment_id>.log`).
5. Parse metrics from the log file; decide keep / discard vs best.
6. Append a row to `experience/EXPERIMENT_LOG.md` for every completed attempt (outcomes and key metrics).
7. Stop when **Stop conditions** hit.

**After** the user explicitly authorizes integrating the branch:

```bash
# From skill root; EXPERIMENT_ID and branch must match what you created
EXPERIMENT_ID="run-01"
SKILL_ROOT="$(pwd)"
EXPERIMENT_BRANCH="experiment/${EXPERIMENT_ID}"
WT_PATH="${SKILL_ROOT}/worktrees/${EXPERIMENT_ID}"

git -C "${AUTORESEARCH_ROOT}" checkout main
git -C "${AUTORESEARCH_ROOT}" merge --no-ff "${EXPERIMENT_BRANCH}" -m "merge experiment ${EXPERIMENT_ID}"
git -C "${AUTORESEARCH_ROOT}" worktree remove "${WT_PATH}"   # optional cleanup when finished
```

Do not run the merge block without user approval.

### Stop conditions

- `max_iterations` or `time_budget` reached  
- Unparseable metrics from the log (after one clarification attempt)  
- Repeated infrastructure failures  
- User asks to stop  

### Strict guardrails

- **VRAM / risk**: keep conservative caps unless user opts out.  
- **Keep threshold**: e.g. for `val_bpb`, only keep clear wins (e.g. ≥ 0.0010) unless user overrides.  
- **Stagnation**: if there is no meaningful improvement across iterations, consult **experience/LEARNINGS.md** and prior **experience/EXPERIMENT_LOG.md** before proposing the next change.

---

## Experience (persistent logs)

**Experience** is the name for this skill’s durable log set: what happened in experiments, what broke, and what the agent learned about training the model. It is separate from raw `logs/*.log` files (execution) and from the trainer git repo (`AUTORESEARCH_ROOT`).

Write to these paths under the skill root (bootstrap with `bash scripts/init-experience.sh` if needed):

| File | Use |
|------|-----|
| `experience/EXPERIMENT_LOG.md` | Outcomes: each run (metrics, keep/discard, brief notes). **Primary experiment results log.** |
| `experience/ERROR.md` | Bugs, crashes, OOMs, tool failures, stack traces, **during execution**. |
| `experience/LEARNINGS.md` | Optimisation-related insights (hyperparameters, training dynamics, what worked/didn’t) when you refine how you run or tune the model — not raw stderr dumps. |

Optional machine-readable state: `experience/RUN_SUMMARY.json` (if you use it).

Do **not** log secrets, API keys, or full unbounded raw transcripts. Prefer pointers: “see `logs/<id>.log` lines N–M”.

**When metrics are flat or regressing**: add or refresh entries in `experience/LEARNINGS.md` with hypotheses; use hooks (see `references/hooks-setup.md`) so prior learnings and error patterns can be re-injected into context when needed.

`FEATURE_REQUESTS` is not used by this skill.

---

## Optional: `results.tsv` (machine-readable)

If used, keep at skill root; schema example:

```tsv
commit	val_bpb	memory_gb	status	description
```

---

## Decision template

```markdown
### Experiment proposal
- experiment_id:
- hypothesis:
- worktree: worktrees/…
- planned change:
- risk:

### Result (from log file, not full paste)
- log file:
- primary metric:
- delta vs best:

### Recommendation
- keep | discard
- experience/EXPERIMENT_LOG.md updated: yes | no
- experience/LEARNINGS.md (if optimization insight): yes | no
- experience/ERROR.md (if failure): yes | no
- merge to trainer main: not requested | pending user auth | user authorized
```

---

## Hooks (optional)

If your **host** supports “run command before prompt” (or similar), see `references/hooks-setup.md` for three optional **command** injectors. They are **illustrative**; wire event names to your product.

1. **Experiment** — injects the standard **bash** training pattern (log file redirection).  
2. **Learnings** — injects a **tail** of `experience/LEARNINGS.md` when improving on stagnation.  
3. **Errors** — injects a **tail** of `experience/ERROR.md` when handling similar failures.  

Use short tails (e.g. last 80–120 lines) so context window stays safe. The skill is fully usable **without** hooks; `SKILL.md` alone is enough.
