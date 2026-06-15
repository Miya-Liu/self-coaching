# self-coaching mode

The **host agent** is both **executor** and **subject**: it loads `modes/self-coaching/`, runs experiments locally, and evolves itself using the gated loop in root `README.md` (Loading Gate → Deploy Gate → Experience).

Overview: [architecture.md](architecture.md). Naming: [README.md](README.md#canonical-naming).

## Purpose in this mode

Coach the agent on *how* to learn from real work: encode durable memory and skills (**self-learning**), generate stress data (**self-play**), measure performance (**self-evaluation**), tune when needed (**self-tuning**), and merge only after human approval. Full train logs stay on disk (`logs/`), not in context.

## Submodules

| Submodule | Path | When to load |
|-----------|------|--------------|
| **self-learning** | `self-learning/SKILL.md` | Corrections, bugs, preferences → memory/skills/eval cases |
| **self-play** | `self-play/SKILL.md` | Generate or curate tasks and trajectories |
| **self-evaluation** | `self-evaluation/SKILL.md` | Run evals, interpret reports, promotion gates |
| **self-tuning** | `self-tuning/SKILL.md` | AERL SFT/GRPO after curation and eval discipline |

Load umbrella `modes/self-coaching/SKILL.md` first. Pipeline order and evolution-engine automation: [pipelines.md](pipelines.md).

## Deploy profile

| Aspect | Typical setup |
|--------|----------------|
| Primary target | T1 — `modes/self-coaching/` (+ repo `scripts/` when cloned whole) |
| Coaching root | Repo or project root (`experience/`, `.self-coaching/`) |
| Observation | Hooks, user corrections, local logs, optional orchestrator |
| Deploy improvements | Merge into host repo; user approval in session |
| Config template | `configs/self-coaching.example.yaml` |
| Host adapters | `modes/self-coaching/adapters/` |

## How it runs

The host agent is the **coach capability** for itself: it observes experience, runs a **self-evolution tick**, and routes to **hold**, **self-learning**, **self-play**, or **self-tuning** according to gates in [pipelines.md](pipelines.md) and the demo loop spec ([self-coaching-demo-pipeline-plan.md](../project/self-coaching-demo-pipeline-plan.md) §3).

**Naming (do not conflate):**

| Term | Meaning |
|------|---------|
| **Loop execution mode** (this section) | *When* the host runs the evolution cycle — autonomous, scheduler, or manual |
| **SKILL invocation mode** | *How* the skill pack is used — policy reference vs mock validation vs real API ([`SKILL.md`](../../modes/self-coaching/SKILL.md) § Invocation Contract) |
| **Self-learning API trigger** | *Which HTTP endpoint* fires the review agent — evolve, evolve/recent, loop E-path ([self-learning-review-agent-plan.md](../project/self-learning-review-agent-plan.md) §3.1) |

### Loop execution modes

Three ways to drive the same gated loop. All modes share one **self-evolution tick** (below); they differ only in **who starts each tick** and **cadence**.

```text
                    +------------------ self-evolution tick ------------------+
                    |  Observe → gate check → route (hold | E | P | T)          |
                    +---------------------------+-------------------------------+
                                                |
          +------------------+------------------+------------------+
          |                  |                  |                  |
    +-----v-----+      +-------v-------+   +------v------+
    | Autonomous |      |  Scheduler    |   |   Manual    |
    | host agent |      | cron / idle   |   | user / admin|
    | 24×7 loop  |      | window        |   | on demand   |
    +------------+      +---------------+   +-------------+
```

#### 1. Autonomous

The **host agent** owns the loop: it runs continuously (background daemon or long-lived session) and **self-arranges** evolution without an external cron.

| Aspect | Behavior |
|--------|----------|
| Driver | Host agent with `modes/self-coaching/SKILL.md` loaded; optional background worker on the host platform (e.g. Hermes Dream-style fork) |
| Cadence | Event-driven between ticks; polls observation surfaces when idle (session tail, Σ, metrics, eval reports) |
| After each tick | Agent decides: **hold** (thresholds not met), **self-learning** (E-path), **self-play** (sparse suite or buffer fill), **self-tuning** (T-path) |
| Idle semantics | Uses host idle signals (no active user turn, low queue depth) — same role as `F.idle()` in the demo loop |
| Feasibility | Requires budget caps (token/time per tick), mutex rules when E and T overlap ([demo plan](../project/self-coaching-demo-pipeline-plan.md) §3.5), and platform support for background runs |

**Typical routing (same gates as demo loop):**

- `|Σ| ≥ σ_min` → self-learning (and optional sparse self-play when `0 < |Σ| ≤ σ_play`)
- `F.idle()` and `|B| < β` → batch self-play to fill tuning buffer
- `F.idle()` and `|B| ≥ β` → self-tuning + holdout gate before promote
- Else → **hold**

#### 2. Scheduler

The loop runs on a **fixed schedule** or during an **idle time window**. An external **cron service** (or systemd timer, k8s CronJob) invokes the evolution entry point; the host agent does **not** need to run 24×7.

| Aspect | Behavior |
|--------|----------|
| Driver | Cron / timer calling loop driver or evolution engine CLI |
| Cadence | Fixed interval (e.g. nightly eval + improve) or idle window (e.g. weekends, `LOOP_IDLE_AFTER` tasks in demo) |
| After each invocation | Same routing as autonomous — one tick per fire |
| Self-learning | Often `POST /learning/evolve/recent` on daily cron; E-path on scheduled `check-drop` |
| Coach mode | Default pattern today — [coach_mode.md](coach_mode.md) § Scheduler |

**Example (self-coaching host, coaching root at repo):**

```bash
# Nightly: record eval, improve only on drop
python -m services.orchestrator record-eval --coaching-root . --agent-id my-host ...
python -m services.orchestrator check-drop --metrics-dir ./.self-coaching/metrics \
  || python -m services.orchestrator run --coaching-root . --run-dir ./runs/... --agent-id my-host
```

**Demo analogue:** `loop_driver.run_tasks()` over a fixture task stream = **one scheduler tick** (batch of tasks + E/T paths), not a 24×7 autonomous host.

#### 3. Manual

An **admin or user** explicitly requests coaching or evolution. No background loop unless someone triggers it.

| Aspect | Behavior |
|--------|----------|
| Driver | Human intent — chat (“coach this”, “evolve from yesterday”), CLI, or HTTP |
| Cadence | On demand |
| Entry surfaces | Load umbrella or submodule skill; `python -m self_coaching.demo`; `curl POST /learning/evolve`; orchestrator `run` with documented reason |
| Scope | May run a **single stage** (self-learning only) or a **full tick** (observe → route) depending on the ask |
| SKILL fit | Single-experience reasoning → SKILL **Mode 1** (policy); full loop validation → **Mode 2/3** (mock or real API) |

Manual does not bypass gates: deploy and holdout rules still apply when self-tuning is requested.

### Self-evolution tick (shared)

Every execution mode runs the same logical tick (implemented by host reasoning, `loop_driver.py`, or `services/orchestrator/run`):

```text
1. Observe     trajectories, Σ, sessions, eval metrics, learning events
2. Gate        σ_min, σ_play, |B| vs β, F.idle(), drop detector (orchestrator)
3. Route       hold | self-learning (E) | self-play (sparse / batch) | self-tuning (T)
4. Record      generation bump, registry draft, metrics, experience artifacts
5. Sleep       until next event (autonomous), next cron (scheduler), or user (manual)
```

| Route | Submodule | Demo trigger | Production surface |
|-------|-----------|--------------|-------------------|
| **Hold** | — | Thresholds not met | No API call; wait |
| **Self-learning** | `self-learning/` | `\|Σ\| ≥ σ_min` | `learn()` / `POST /learning/evolve*` |
| **Self-play** | `self-play/` | Sparse Σ or `\|B\| < β` idle | `generate-suite` / `generate` |
| **Self-tuning** | `self-tuning/` + eval gate | `F.idle()` ∧ `\|B\| ≥ β` | `train()` / `POST /training/runs` + holdout |

E-path takes precedence over T-path on the same tick when both could fire ([demo plan](../project/self-coaching-demo-pipeline-plan.md) §3.5).

### Execution mode comparison

| | Autonomous | Scheduler | Manual |
|---|------------|-----------|--------|
| **Who triggers** | Host agent | Cron / idle window service | User / admin |
| **Host must run 24×7** | Yes (or equivalent background worker) | No | No |
| **Typical production** | Always-on coding agents, Hermes background review | Nightly improve, coach M5 | Ad-hoc “learn from this session” |
| **Self-learning API** | Agent calls when Σ or sessions warrant | `evolve/recent` on cron; E-path on drop | `evolve` with `session_ids` |
| **Risk controls** | Per-tick budget, opt-out, mutex on `g` | Rate limits per cron slot | Explicit user consent per request |

### Configuration (proposed)

| Variable | Values | Used by |
|----------|--------|---------|
| `LOOP_EXECUTION_MODE` | `autonomous` \| `scheduler` \| `manual` | Documents intent; manual = no auto driver |
| `LOOP_SCHEDULE_CRON` | cron expression | Scheduler — external cron should read equivalent |
| `LOOP_IDLE_AFTER` | integer (tasks) | Scheduler idle window + autonomous `F.idle()` demo shim |
| `LOOP_SIGMA_MIN`, `LOOP_SIGMA_PLAY`, `LOOP_BATCH_SIZE` | thresholds | All modes — same as [demo.env.example](../../scenarios/demo.env.example) |

`LOOP_EXECUTION_MODE` does not replace `LOOP_SERVICE_MODE` (mock vs live backends) or `LOOP_LEARN_MODE` (sync vs evolve API).

### Policy-driven loop (worktree experiments)

Follow `SKILL.md`: worktree experiments (`AUTORESEARCH_ROOT`), redirect training to `logs/`, write **Experience**, request authorization before merge. Applies in all execution modes when self-tuning promotes a candidate.

### Hooks (optional)

`references/hooks-setup.md` — experiment command pattern, error/learnings tail. Not required by `SKILL.md`. Observation input for autonomous and manual ticks.

### Evolution engine (optional automation)

Semi-automated eval and improve-on-drop — natural fit for **scheduler**; also callable from **manual** ops:

```bash
python -m services.orchestrator record-eval --coaching-root . --agent-id my-host ...
python -m services.orchestrator check-drop --metrics-dir ./.self-coaching/metrics
python -m services.orchestrator run --coaching-root . --run-dir ./runs/... --agent-id my-host
```

`ORCHESTRATOR_TRANSPORT=module` (default); `ORCHESTRATOR_EVAL_BACKEND=mock` or `agentevals`.

## Worktree experiment model

- Integration line: trainer repo `main` (`AUTORESEARCH_ROOT`).
- Experiment line: `worktrees/<id>/`, branch `experiment/<id>`.
- Summaries: `experience/`; full logs: `logs/<id>.log`.

## Guides

- [deploy-skill-pack.md](../guides/deploy-skill-pack.md)
- [runbook.md](../guides/runbook.md)

## Related

- [coach_mode.md](coach_mode.md) — external supervision
- [evaluators.md](evaluators.md) — metrics when automating
