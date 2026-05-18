---
name: self-coaching
description: Agent-agnostic skill. Coaches any capable agent through Loading Gate, Performance, Data Pool, Local Model, Deploy Gate, Trainer, LOGs, and Results (experience logs); git worktrees; user-authorized merge and model/data updates.
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
| Reusable workflow | Skill | "How to debug Hermes TUI slash commands." |
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
- `upstream_git_dir`: `upstream/autoresearch` (must become or already be a git repo)
- `experiment_worktree`: e.g. `worktrees/<experiment_id>` (path under skill root; **only** this tree is edited during the loop)
- `train_log_file`: e.g. `logs/<experiment_id>.log`

## Non-negotiable constraints

1. **Worktree boundary**: apply experiment edits and commits **only** inside `experiment_worktree` until the user approves merge. Do not change tracked files in `upstream/autoresearch` on `main` during the loop except via the merge step after approval.
2. **Training command**: use the **exact pattern** in **Run one training experiment (log to file)**. Redirect **all** stdout and stderr to `logs/…`; parse metrics from that file. For `training/pipelines` (SFT/GRPO), use `scripts/run-pipeline.sh` or the per-pipeline `run.sh` so output still goes to the given log path (`LOG_FILE`)—same discipline, different entrypoint.
3. Experiments may run autonomously within guardrails until stop conditions.
4. One clear hypothesis per iteration; small, attributable commits in the **experiment** branch.
5. **Merge**: `git merge` of the experiment branch into `main` in `upstream/autoresearch` **only after explicit user authorization**.
6. External deployment/promotion (artifacts, production pointers) also requires explicit approval (same or separate confirmation as merge, per user).

---

## One-time: git baseline in `upstream/autoresearch`

If `upstream/autoresearch` is not yet a git repository, initialize once (from skill root, paths illustrative):

```bash
cd upstream/autoresearch
git init
git add -A
git commit -m "vendor baseline"
git branch -M main
cd ../..
```

If it is already a repo, skip this block.

## Create the experiment worktree (fork for this session)

From **skill root** (the directory that contains `SKILL.md` and `upstream/`), with `EXPERIMENT_ID` set. Use an **absolute** worktree path so it resolves regardless of `git -C` behavior:

```bash
EXPERIMENT_ID="run-01"
# SKILL_ROOT: absolute path to this skill repo
SKILL_ROOT="$(pwd)"
EXPERIMENT_BRANCH="experiment/${EXPERIMENT_ID}"
WT_PATH="${SKILL_ROOT}/worktrees/${EXPERIMENT_ID}"

git -C upstream/autoresearch worktree add -b "${EXPERIMENT_BRANCH}" "${WT_PATH}"
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
- If `uv` / env must run from a specific cwd, only `cd` to **`WT_PATH`**, not to `upstream/autoresearch` on `main`.

**Dependency / data prep** (unchanged, run against upstream checkout if needed, typically once):

```bash
uv --directory upstream/autoresearch sync
uv --directory upstream/autoresearch run prepare.py
```

(Use the same venv/lock as upstream; the worktree shares the same working tree’s git metadata but the experiment files live in `WT_PATH`.)

## Training pipelines (SFT, GRPO, **AERL** trainer API)

For **LLM / agent** stages beyond the default vendored `train.py` loop, this pack includes `training/pipelines/` (same file bundle as **Layout** in `README.md`: **AERL** `registry.yaml` with `service.url`, `_lib.sh`, per-pipeline `pipeline.yaml` + `run.sh`):

- **Registry:** `training/pipelines/registry.yaml` lists pipeline ids (`sft`, `grpo`, …) and **AERL** `service.url` (default trainer base, typically `http://localhost:8004`).
- **Per pipeline:** `training/pipelines/<id>/pipeline.yaml` (HTTP + optional local entrypoints) and `training/pipelines/<id>/run.sh` (redirects **all** stdout/stderr to `LOG_FILE`).
- **Shared helpers:** `training/pipelines/_lib.sh` (sourced by runners; not invoked directly).
- **Service contract (env):** copy `training/services/example.env` to `training/services/.env` (ignored by git). Set `TRAINER_BASE_URL` / `TRAINER_API_KEY` for the trainer HTTP API; set `OPENAI_BASE_URL` / `OPENAI_API_KEY` for OpenAI-compatible **rollout** endpoints used by your agent loop (same “replace `base_url`” pattern as **AERL** and other OpenAI-compatible stacks).

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

git -C upstream/autoresearch checkout main
git -C upstream/autoresearch merge --no-ff "${EXPERIMENT_BRANCH}" -m "merge experiment ${EXPERIMENT_ID}"
git -C upstream/autoresearch worktree remove "${WT_PATH}"   # optional cleanup when finished
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

**Experience** is the name for this skill’s durable log set: what happened in experiments, what broke, and what the agent learned about training the model. It is separate from raw `logs/*.log` files (execution) and from the git repo under `upstream/` (code).

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
- merge to upstream/main: not requested | pending user auth | user authorized
```

---

## Hooks (optional)

If your **host** supports “run command before prompt” (or similar), see `references/hooks-setup.md` for three optional **command** injectors. They are **illustrative**; wire event names to your product.

1. **Experiment** — injects the standard **bash** training pattern (log file redirection).  
2. **Learnings** — injects a **tail** of `experience/LEARNINGS.md` when improving on stagnation.  
3. **Errors** — injects a **tail** of `experience/ERROR.md` when handling similar failures.  

Use short tails (e.g. last 80–120 lines) so context window stays safe. The skill is fully usable **without** hooks; `SKILL.md` alone is enough.
