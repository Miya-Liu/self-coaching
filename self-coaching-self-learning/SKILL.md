---
name: self-coaching-self-learning
description: "Use when converting an agent's prior experience, user corrections, resolved bugs, tool failures, or skill changes into durable memory, skill patches, tests, eval cases, reusable runbooks, or experience-log entries."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, self-learning, memory, skills, bug-postmortem, agent-improvement, experience]
    related_skills: [self-coaching, hermes-agent-skill-authoring, systematic-debugging, test-driven-development]
---

# Self-Coaching: Self-Learning

## Overview

Self-learning turns real agent experience into compact durable improvements. It is the cheapest and safest self-coaching path: prefer memory, skill patches, tests, eval cases, and experience logs before model training.

This atomic skill now has an executable workflow around the shared `self-coaching/experience/` files and `self-coaching/scripts/` helpers. Use those files for project-local learning records; use Hermes memory only for compact facts that should persist across sessions.

## When to Use

Use this skill after:

- user corrections or preference updates;
- repeated clarification on similar tasks;
- hard bug fixes or non-obvious root causes;
- tool/API/environment quirks;
- stale, missing, or extended skill instructions;
- training/eval failures that reveal procedural failures;
- low-performance eval cases that should become regression coverage.

Do not use it to save temporary task state, PR numbers, issue numbers, raw logs, or anything likely stale within a week.

## Executable Workflow

The category-level scripts live under:

```text
C:/Users/liumy26/.hermes/skills/self-coaching/scripts/
```

Use them from Bash/git-bash. On Windows Hermes terminal also uses Bash, so POSIX syntax is expected.

### Step 0: Initialize an Experience Workspace

For a target project or experiment root:

```bash
bash C:/Users/liumy26/.hermes/skills/self-coaching/scripts/init-experience.sh <project-root>
```

This creates, without overwriting existing files:

```text
<project-root>/experience/EXPERIMENT_LOG.md
<project-root>/experience/ERROR.md
<project-root>/experience/LEARNINGS.md
<project-root>/logs/
<project-root>/worktrees/
```

If no project root is provided, the script initializes `./experience`, `./logs`, and `./worktrees` in the current directory.

### Step 1: Capture the Event

Append only concise summaries, not raw transcripts or full logs:

- `experience/ERROR.md` — crashes, OOMs, parse failures, tool failures, integration errors.
- `experience/LEARNINGS.md` — reusable training/optimization/process lessons.
- `experience/EXPERIMENT_LOG.md` — run outcomes, metrics, decisions, and log-file references.

Use this incident block for `ERROR.md`:

```markdown
## <date> <short-title>
- category: crash | oom | parse_error | env | logic_bug | other
- symptom:
- command/log: logs/<run-id>.log lines <start>-<end>
- root_cause:
- fix_or_workaround:
- verification:
- durable_artifact: memory | skill_patch | test | eval_case | training_candidate | none
```

Use this learning block for `LEARNINGS.md`:

```markdown
## <date> <short-title>
- category: optimization | process | metric | stability | best_practice
- context:
- observation:
- reusable_lesson:
- evidence:
- next_artifact: skill_patch | eval_case | self_play_task | training_manifest | none
```

### Step 2: Inject Prior Experience When Useful

When debugging a similar error:

```bash
ERROR_TAIL_LINES=120 bash C:/Users/liumy26/.hermes/skills/self-coaching/scripts/hook-inject-errors.sh
```

When optimization has stalled or training strategy is being changed:

```bash
LEARNINGS_TAIL_LINES=120 bash C:/Users/liumy26/.hermes/skills/self-coaching/scripts/hook-inject-learnings.sh
```

These hooks print bounded tails of the experience files so an agent can reuse prior context without flooding the prompt.

### Step 3: Route to a Durable Artifact

Use the decision table below. If the correct artifact is outside this skill, hand off to the corresponding atomic skill.

## Decision Table

| Observation | Durable artifact | Next action |
|---|---|---|
| Stable user preference | Memory | Save compact declarative memory. |
| Stable environment convention | Memory | Save compact environment fact. |
| Reusable workflow | Skill or skill patch | Patch existing skill before creating a new one. |
| Existing skill missing pitfall/step | Skill patch | Patch immediately and verify load. |
| Code defect | Fix + regression test | Use TDD/systematic debugging. |
| Weak behavior to prevent | Eval case | Route to `self-coaching-evaluation`. |
| Need harder variants | Self-play task family | Route to `self-coaching-self-play`. |
| Repeated manual operation | Tool/plugin/MCP candidate | Create executable tool only if repeated. |
| Model capability gap after instruction/tool fixes | Training-data candidate | Route to `self-coaching-training` after privacy review. |

## Procedure

1. Initialize or locate the project experience workspace.
2. Write a one-paragraph postmortem: symptom, false starts, root cause, fix, verification.
3. Record only a summary and log references in `experience/ERROR.md`, `LEARNINGS.md`, or `EXPERIMENT_LOG.md`.
4. Classify the lesson using the decision table.
5. Choose the smallest durable artifact.
6. Save only compact stable facts to memory.
7. Patch existing skills before creating new ones.
8. Add tests/evals for behavior that must not regress.
9. If the lesson is training-worthy, hand it to `self-coaching-self-play` or `self-coaching-training` only after privacy review.

## Common Pitfalls

1. **Using experience files as memory.** Experience files are project-local logs; memory is for compact facts that should survive across all sessions.
2. **Dumping raw logs.** Store logs in `logs/` and reference path/line ranges from experience files.
3. **Skipping classification.** A bug may need a test or eval, not a memory.
4. **Creating duplicate skills.** Search existing skills first and patch when possible.
5. **Saving secrets.** Redact credentials, private data, and proprietary content before writing any durable artifact.

## Verification Checklist

- [ ] `init-experience.sh` has created or preserved the target experience files.
- [ ] The lesson is stable, not task-local.
- [ ] The chosen artifact is the smallest sufficient one.
- [ ] Memory entries, if any, are compact and declarative.
- [ ] Skills include triggers, steps, pitfalls, and verification.
- [ ] Bug fixes have tests or eval cases.
- [ ] Raw logs are stored under `logs/`, not pasted into experience files.
- [ ] No secrets, private data, or stale identifiers were saved.
