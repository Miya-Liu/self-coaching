---
name: self-coaching
description: Agent-agnostic skill. Coaches any capable agent through Loading Gate, Performance, Data Pool, Local Model, Deploy Gate, Trainer, LOGs, and Results (experience logs); git worktrees; user-authorized merge and model/data updates.
---

# Self Coaching

## Intent

**Portability:** This package is a **portable agent skill**. Any system that can supply this folder to an **LLM agent** (API, IDE, or CLI) and allow **Bash** + file tools may use it. It is not specific to a single editor or “skills” store—only `SKILL.md` and the file layout below need to be visible to the model.

This skill **coaches the agent** to train and improve a **git-backed codebase**—especially the **model** (weights, architecture, and training loop in the repo the agent is working in). The default target here is the vendored trainer under `upstream/autoresearch/`; the same pattern applies if you point the skill at another repository.

The agent runs training experiments **automatically** while isolating edits in a **git worktree** branched from that repo. It uses **git-related Bash** (`git`, `git worktree`, `git merge`, etc.) as below. **Do not merge back into upstream `main` until the user explicitly authorizes it.**

- Mode: `git worktree` + `stage-gated merge`
- Safety profile: `strict` (edits only inside the active experiment worktree during the loop)
- **Experience** (persistent logs): `experience/EXPERIMENT_LOG.md`, `experience/ERROR.md`, `experience/LEARNINGS.md` (see **Experience**)
- All training stdout/stderr: redirect to **log files** under `logs/` (never paste full training output into chat)

## Pipeline concepts (see `README.md` diagram)

These names match the **sequence diagram** in `README.md` and `docs/ARCHITECTURE.md`.

- **Loading Gate** — Preconditions before the first experiment: `uv` env, data/tokenizer cache (e.g. `uv run prepare.py`), and any **admin-configured** checkpoint or model entry point. The agent does not start the training loop until this gate is satisfied.
- **Performance** — Current model quality vs the goal, using the primary `metric_name` from `logs/<id>.log` and the keep/discard rules in **Strict guardrails**.
- **Data Pool** — All data the training pipeline is allowed to use: default prepared cache, **plus** any additional sources you wire in (e.g. exports from **user–agent dialogue**, or **self-play**–generated data). Keep paths and provenance explicit in `experience/LEARNINGS.md` when you add new sources.
- **Local Model** — **Admin-configured** starting point: which weights/checkpoint, and often which size variant (e.g. full model vs a smaller one for fast iteration). The agent reads this from your project’s config or environment; the skill does not override admin policy.
- **Deploy Gate** — Isolation and promotion: work on `experiment/<id>` only in `worktrees/<id>/`; **no** replace of the integrated `main` line, and no **Replace local model** / **Update data** on the canonical path, until the **Human** approves.
- **LOGs** — `logs/<id>.log` (full `train` output).
- **Results** — Durable record in `experience/` (outcomes, errors, optimization learnings), not raw log paste.

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
2. **Training command**: use the **exact pattern** in **Run one training experiment (log to file)**. Redirect **all** stdout and stderr to `logs/…`; parse metrics from that file.
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
