# self-coaching

A **portable, agent-agnostic skill set** for coaching any LLM or coding **agent** that can follow markdown skills and run Bash. Root `SKILL.md` is the full **orchestration** policy: a gated loop from observation through memory/skills/evals, self-play data, **Experience** logs, optional **AERL** SFT/GRPO-style training, and **user-authorized** merge or promotion. The same contract is the repo layout + `SKILL.md`; it is not tied to a single product.

This repository **decomposes** that policy into **atomic step skills** (separate folders with their own `SKILL.md`) so a host can load the umbrella policy or only the phase you are executing. See **`DESCRIPTION.md`** for the index: `self-coaching-self-learning`, `self-coaching-self-play`, `self-coaching-evaluation`, `self-coaching-training`.

**Install** the tree wherever your environment expects skills (project-local `skills/self-coaching`, a shared `tools/` tree, or a path your stack documents — see [Installation paths](#installation-paths)). Wire your **agent** to load root `SKILL.md` for the full loop, or load a subfolder skill when working in one phase only.

The default **target git tree** for the vendored trainer loop is `upstream/autoresearch/` (from [karpathy/autoresearch](https://github.com/karpathy/autoresearch)). The same workflow applies to other ML repos you attach.

**Upstream:** [github.com/Miya-Liu/self-coaching](https://github.com/Miya-Liu/self-coaching) (`main`).

## Workflow

```mermaid
sequenceDiagram
    autonumber
    participant U as Human
    participant A as Agent
    participant G as Loading Gate
    participant B as Performance
    participant C as Data Pool
    participant M as Local Model
    participant D as Deploy Gate
    participant T as Trainer<br/>(worktree + optional AERL)
    participant X as Results

    U->>A: Enable/Trigger self-coaching
    A->>G: Ensure Opening Gate
    G->>B: Review performance
    B->>G: Needs improvement
    G->>C: Load training data
    C->>G: Clean data
    G->>M: Load training model
    M->>G: Model checkpoint
    G->>A: Experiment Ready
    
    A->>D: Create experiment/<id> + worktree
    loop Experiment iterations
        A->>T: Edit code in worktree only
        T->>T: Run training (worktree train.py or AERL pipelines -> logs)
        T->>A: Experimental results, failures, errors
        alt No meaningful improvement
            A->>D: Resolve Error / Next Improvements
            D->>T: Update
        else Improvement found
            A->>D: Keep best branch state
        end
        D->>A: Improved version of local model
    end
    
    A->>U: Request authorization
    U->>A: Decision
    alt Approve
        A->>M: Replace local model
        A->>C: Update data
    else Decline
        A->>M: Keep current version
    end
```

**How this maps in the default pack**

| Concept | Typical implementation |
|---------|-------------------------|
| **Loading Gate** | Dependencies, `prepare.py`, cache readiness, configured checkpoint paths (see `SKILL.md`). |
| **Performance** | Primary metric from `logs/<id>.log` (e.g. `val_bpb`) vs best; guardrails. |
| **Data Pool** | Training/val data (e.g. under `~/.cache/autoresearch/`) plus anything you curate — **including** dialogue-derived or **self-play** artifacts you point the pipeline at. |
| **Local Model** | Admin-chosen baseline: which checkpoint / which size variant (full vs smaller) before the run; see `SKILL.md` **Local Model configuration**. |
| **Deploy Gate** | Isolation (`experiment/<id>` + `worktrees/...`) and **human approval** before replacing the integrated line or promoted weights. |
| **Trainer** | Default: `uv run train.py` in the worktree (`scripts/run-once.sh`). Optional: **AERL** SFT/GRPO via `self-coaching-training/pipelines/` and `scripts/run-pipeline.sh` (HTTP or `PIPELINE_MODE=local` + `AERL_ROOT`; see `SKILL.md`). |
| **Trainer feedback** | Trainer returns experimental outcomes, failures, and errors to the agent; full raw run output still lands in `logs/<id>.log` (autoresearch or **AERL** run). |
| **Results** | Agent-resolved outcomes written to `experience/` (experiment log, errors, learnings); other durable artifacts per root `SKILL.md` (memory, skills, eval cases, curated data). |

The experiment loop runs autonomously inside the **Deploy Gate** boundary; **Replace local model** / **Update data** after approval are the only steps that change the canonical line the way your org defines it (merge, checkpoint swap, dataset refresh).

**Data Pool** includes data the agent gathered in prior user interactions and/or data produced in **self-play**, as long as your `prepare` / dataloader paths are wired to those sources.

**Local Model** is configured by admins (which checkpoint, main vs smaller model, device, etc.); the skill treats that configuration as fixed for a run unless policy says otherwise.

## What this skill set is for

- **Orchestrate** the agent on *how* to learn from tasks, generate stress data, evaluate, run training, and record outcomes — without flooding context with full `train` logs.
- **Focus the model** when training: architecture, `train.py` (or equivalent), metrics like `val_bpb` — i.e. the model the agent is training in that repo.
- **Experience** = durable logs under `experience/` (`EXPERIMENT_LOG.md`, `ERROR.md`, `LEARNINGS.md`).
- **Atomic skills** under `self-coaching-*` for phase-specific execution (see `DESCRIPTION.md`).

## Layout (current repository)

| Path | Role |
|------|------|
| `SKILL.md` | Full procedure: git, worktree, training redirect, merge gate, **Experience**, self-learning / self-play / eval / training playbooks. |
| `DESCRIPTION.md` | Short index of atomic skills and when to load each. |
| `docs/RUNBOOK.md` | Quick setup |
| `docs/ARCHITECTURE.md` | Structure and control boundaries |
| `upstream/autoresearch/` | Vendored repo to train |
| `experience/` | **Experience** templates and optional `RUN_SUMMARY.json` |
| `self-coaching-self-learning/` | Phase skill: durable memory, skills, tests, eval cases from real experience |
| `self-coaching-self-play/` | Phase skill: generate and curate challenging tasks and trajectories |
| `self-coaching-evaluation/` | Phase skill: evaluation services and promotion gates |
| `self-coaching-training/` | Phase skill: SFT/RL training discipline; **`pipelines/`** (SFT/GRPO for **AERL**: `registry.yaml`, `_lib.sh`, per-pipeline `pipeline.yaml` + `run.sh`) and **`services/`** (`example.env`; copy to `.env`, gitignored) |
| `scripts/` | `preflight.sh`, `run-once.sh`, `run-pipeline.sh`, `init-experience.sh`, hook helpers, `activator.sh` |
| `logs/` / `worktrees/` | Created at runtime (see `.gitignore`) |
| `references/hooks-setup.md` | Hook wiring (optional; map events to your host) |

## Installation paths

Use **one** of these (or your own); only the path in hook commands and docs needs to be consistent.

| Where | Example |
|--------|---------|
| Project-local | `my-repo/skills/self-coaching/` (clone or copy this repo root) |
| User global | `~/skills/self-coaching/` or `~/.config/self-coaching/skill/` |
| Cursor (if you use it) | `~/.cursor/skills/self-coaching/` or `.cursor/skills/self-coaching/` |
| Other IDEs / agents | Follow that product's "skills" or "rules" directory; set hook `command` to **absolute** paths if relative paths are unreliable. |

Hooks in `references/hooks-setup.md` are **illustrative** (JSON + shell); adapt event names to your product.

## Quick start

1. Clone or copy this repository, for example: `git clone git@github.com:Miya-Liu/self-coaching.git` (HTTPS: `https://github.com/Miya-Liu/self-coaching.git`).
2. Place it on disk where your **agent** is configured to read it (see [Installation paths](#installation-paths)).
3. Run `bash scripts/init-experience.sh`.
4. Read `DESCRIPTION.md`, then `docs/RUNBOOK.md`, then root `SKILL.md`. Load a `self-coaching-*/SKILL.md` when executing only one phase.
5. Add hooks from `references/hooks-setup.md` if you want.

For **AERL** pipelines, configure env from `self-coaching-training/services/example.env`, then from repo root either use `scripts/run-pipeline.sh` or invoke `self-coaching-training/pipelines/<id>/run.sh` with `LOG_FILE` set (see `docs/RUNBOOK.md` and `SKILL.md`).

## Scope

- Training runs are automated within guardrails; **merge to upstream `main`** and **external promotion** require explicit user approval.
