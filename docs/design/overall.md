## Self-Evolution Loop Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          COACH CLOCK SERVICE (24×7)                             │
│                          modes/coach/service.py                                 │
│                                                                                 │
│  HTTP POST /coach/post ──┐     ClockScheduler (background thread)               │
│  WebSocket /coach/ws ────┤       modes/coach/scheduler.py                       │
│                          │       ┌──────────────────────────────┐               │
│                          ▼       │ Per-agent timer (interval_s) │               │
│                    ┌───────────┐ │ Per-agent lock (no overlap)  │               │
│                    │  trigger  │ │ Tick dispatch → thread pool  │               │
│                    │  .py      │◄┘                              │               │
│                    └─────┬─────┘                                                │
│                          │                                                      │
│           Registry (agents.clock.yaml)                                          │
│           → agent_id, coaching_root, eval suites, improvement pipeline          │
└──────────────────────────┼──────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      ONE EVOLUTION TICK (clock.py)                              │
│                      "E → P → T" autonomous cycle                               │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │ Phase 1: E-PATH (Evaluate + Learn)                                      │    │
│  │                                                                         │    │
│  │  task_stream ──► score each τ (trajectory_scorer rubric)                │    │
│  │                     │                                                   │    │
│  │        score ≥ τ_fail ──► Buffer B (good trajectories for training)     │    │
│  │        score < τ_fail ──► Support set Σ (failures to learn from)        │    │
│  │                                │                                        │    │
│  │              When |Σ| ≥ σ_min: │                                        │    │
│  │                                ▼                                        │    │
│  │             ┌────────────────────────────────┐                          │    │
│  │             │ learn_from_sigma()             │                          │    │
│  │             │  → client.learn(failure_event) │ ← Self-Learning service  │    │
│  │             └────────────────────────────────┘                          │    │
│  │                                │                                        │    │
│  │                                ▼                                        │    │
│  │             ┌────────────────────────────────┐                          │    │
│  │             │ augment_sigma_sparse() [C06]   │                          │    │
│  │             │  → self_questioning.generate_suite()  │ ← Self-Play service      │    │
│  │             │  (adversarial eval cases from  │                          │    │
│  │             │   failure patterns)            │                          │    │
│  │             └────────────────────────────────┘                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │ Phase 2: BUFFER FILL                                                    │    │
│  │                                                                         │    │
│  │  Process additional task stream → accumulate Buffer B rows              │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │ Phase 3: T-PATH (Tune + Promote)         triggered when idle            │    │
│  │                                                                         │    │
│  │  ┌───────────────────────────────────┐                                  │    │
│  │  │ fill_buffer_batch() [C07]         │                                  │    │
│  │  │  → self_questioning.generate_batch()     │  ← batch self-questioning               │    │
│  │  │  (fill tuning buffer to β size)   │                                  │    │
│  │  └───────────────────┬───────────────┘                                  │    │
│  │                      ▼                                                  │    │
│  │  ┌───────────────────────────────────┐                                  │    │
│  │  │ client.train()                    │                                  │    │
│  │  │  → train pipeline (SFT / GRPO)    │  ← Training service              │    │
│  │  │  → returns candidate_model_id     │                                  │    │
│  │  └───────────────────┬───────────────┘                                  │    │
│  │                      ▼                                                  │    │
│  │  ┌───────────────────────────────────┐                                  │    │
│  │  │ Holdout gate (AgentEvals)         │                                  │    │
│  │  │  → run candidate on holdout suite │  ← Eval service                  │    │
│  │  │  → compare vs baseline            │                                  │    │
│  │  │  → promote or reject              │                                  │    │
│  │  └───────────────────┬───────────────┘                                  │    │
│  │                      ▼                                                  │    │
│  │            promote: activate candidate version (generation++)           │    │
│  │            reject:  keep current version, log reasons                   │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Backend Routing (env-driven, swappable)

```
                      CompositeClient (services/adapters/composite_client.py)
                      ┌─────────────────────────────────────────────────────┐
                      │  Wraps a base SelfCoachingClient (Module/CLI/HTTP)  │
                      │  Delegates specific methods to real backends:       │
                      │                                                     │
    .learn()  ────────┤───► ORCHESTRATOR_LEARN_BACKEND                      │
                      │       mock     → in-process mock_self_learning      │
                      │       http     → SelfLearningAdapter (HTTP)         │
                      │                                                     │
    .self_questioning() ─────┤───► ORCHESTRATOR_SELF_QUESTIONING_BACKEND                   │
                      │       mock     → MockSelfQuestioningEngine (in-process)    │
                      │       pipeline → SelfQuestioningPipelineEngine ──────────┐ │
                      │                                                   │ │
    .evaluate() ──────┤───► ORCHESTRATOR_EVAL_BACKEND                     │ │
                      │       mock     → in-process mock_agentevals       │ │
                      │       agentevals → AgentEvalsEvalAdapter (HTTP)   │ │
                      │                                                   │ │
    .train()  ────────┤───► ORCHESTRATOR_TRAIN_BACKEND                    │ │
                      │       mock     → in-process mock_aerl             │ │
                      │       aerl     → AERLTrainAdapter (HTTP)          │ │
                      │       cli      → CLITrainAdapter ─────────────┐   │ │
                      └───────────────────────────────────────────────┼───┼─┘
                                                                      │   │
                                                                      ▼   ▼
┌────────────────────────────────────┐    ┌──────────────────────────────────────┐
│ Real Self-Tuning (db_bridge)       │    │ Real Self-Play (Pipeline Service)    │
│                                    │    │                                      │
│ CLITrainTransport                  │    │ PipelineServiceClient                │
│   → INSERT row into Supabase       │    │   → POST /api/pipeline/submit        │
│     (areal_remote_commands table)  │    │   → GET  /api/pipeline/status/{id}   │
│   → Poll row status until terminal │    │   → wait_for_job() polling loop      │
│   → Parse stdout for checkpoint    │    │                                      │
│                                    │    │ PipelineHTTPBase                     │
│       ┌────────────────┐           │    │   → retry on 5xx (GET only)          │
│       │ Supabase DB    │           │    │   → explicit URL required            │
│       │ (shared queue) │           │    │                                      │
│       └───────┬────────┘           │    │ Pipeline Mapping                     │
│               │                    │    │   → build_batch_request()            │
│               ▼                    │    │   → map_batch_result() → proceed?    │
│  ┌──────────────────────────┐      │    └──────────────────────────────────────┘
│  │ AReaL GPU Host           │      │
│  │ run_shell_runner (tmux)  │      │               │
│  │   claims PENDING rows    │      │               ▼
│  │   executes in tmux       │      │    ┌──────────────────────────────┐
│  │   writes SUCCEEDED/FAILED│      │    │ 10.110.158.146:8001          │
│  │   + stdout_tail          │      │    │ 3-stage pipeline:            │
│  └──────────────────────────┘      │    │  Stage 1: generate tasks     │
└────────────────────────────────────┘    │  Stage 2: agent exploration  │
                                          │  Stage 3: import to Supabase │
                                          └──────────────────────────────┘
```

## Key Concepts & Data Stores

```
coaching_root/
├── .self-coaching/
│   ├── events/
│   │   └── learning_events.jsonl        ← failure observations from E-path
│   ├── cases/
│   │   ├── self_questioning_candidates.jsonl   ← generated eval cases (C06/C07)
│   │   └── eval_cases.jsonl             ← cases used for evaluation
│   ├── curated/
│   │   ├── train.jsonl                  ← curated training data
│   │   ├── validation.jsonl             ← dev split
│   │   ├── holdout.jsonl                ← held-out test split
│   │   └── staging.jsonl                ← pre-curation trajectories
│   ├── manifests/
│   │   └── training_run_manifest.json   ← last training run metadata
│   ├── loop/
│   │   ├── support.jsonl                ← Σ (support set: failed trajectories)
│   │   ├── buffer.jsonl                 ← B (buffer: successful trajectories)
│   │   ├── state.json                   ← generation, tasks_processed, counts
│   │   ├── e_path_last.json             ← last E-path result
│   │   └── clock_summary.md            ← human-readable tick summary
│   ├── coach/
│   │   ├── inbox/*.json                 ← inbound coach posts
│   │   ├── ticks/tick_log.jsonl         ← scheduler tick event log
│   │   └── last_response.json           ← last agent response
│   └── reports/eval_runs/{run_id}/
│       └── report.json                  ← eval gate report
└── experience/
    ├── EXPERIMENT_LOG.md                ← high-level progress journal
    ├── LEARNINGS.md                     ← accumulated learnings
    └── ERROR.md                         ← error patterns
```

## The Self-Evolution Loop (Conceptual Flow)

```
              ┌──────────────────────────────────────────────┐
              │                                              │
              ▼                                              │
     ┌────────────────┐                                      │
     │ Process tasks  │  (trajectory scoring via rubric)     │
     └───────┬────────┘                                      │
             │                                               │
    ┌────────┴────────┐                                      │
    │                 │                                      │
 score < τ        score ≥ τ                                  │
    │                 │                                      │
    ▼                 ▼                                      │
┌────────┐      ┌─────────┐                                  │
│ Σ grows│      │ B grows │                                  │
└───┬────┘      └────┬────┘                                  │
    │                │                                       │
    │ |Σ| ≥ σ_min    │ idle window (or |B| ≥ β)              │
    ▼                ▼                                       │
┌──────────┐    ┌───────────┐                                │
│ E-path:  │    │ T-path:   │                                │
│ learn()  │    │ self_questioning │                                │
│ sparse   │    │   batch   │                                │
│ self-questioning│    │ train()   │                                │
│ (C06)    │    │ (C07)     │                                │
└──────────┘    └─────┬─────┘                                │
                      │                                      │
                      ▼                                      │
                ┌───────────┐                                │
                │ Holdout   │                                │
                │ gate eval │                                │
                └─────┬─────┘                                │
                      │                                      │
            ┌─────────┴─────────┐                            │
            │                   │                            │
         promote             reject                          │
            │                   │                            │
            ▼                   │                            │
   generation++ ────────────────┘────────────────────────────┘
   activate new model          (loop continues with current model)
```

## Summary of Key Abbreviations


| Symbol          | Meaning                                                                |
| --------------- | ---------------------------------------------------------------------- |
| τ (tau)         | A task from the task stream                                            |
| τ_fail          | Score threshold below which a task is considered a failure             |
| Σ (sigma)       | Support set — accumulated failure trajectories                         |
| σ_min           | Minimum failures before triggering E-path                              |
| σ_play          | How many sparse self-questioning cases to generate (C06)                      |
| B (beta/buffer) | Buffer of good trajectories for training                               |
| β               | Batch size threshold for T-path trigger                                |
| C06             | Sparse self-questioning (from failures → adversarial eval cases)              |
| C07             | Batch self-questioning (fill tuning buffer before training)                   |
| E-path          | Evolution path: observe failures → learn → generate targeted evals     |
| T-path          | Tuning path: fill buffer → train model → holdout gate → promote/reject |
| generation      | Monotonic counter incremented on each successful model promotion       |





Here's how the self-coaching **skills** relate to the **loop runtime**:

---

## How Skills Map to the Loop

The repo has two complementary layers:

1. **Runtime modules** — Python code that actually runs the loop (`loop_driver.py`, `e_path.py`, `t_path.py`, `clock.py`, adapters)
2. **Skill documents** (`SKILL.md`) — instructions for an AI agent (like Hermes) telling it *when* and *how* to invoke each phase, including the human/manual/policy-only paths

Think of the skills as the agent's "playbook" and the runtime modules as the "machinery."

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           SKILL PACK: self-coaching                                  │
│                           (SKILL.md — the umbrella)                                  │
│                                                                                     │
│   Defines: the full gated pipeline philosophy                                       │
│   Observe → Diagnose → Encode → Verify → Curate → Train → Promote                  │
│                                                                                     │
│   Three invocation modes:                                                           │
│     Mode 1: Policy reference (agent reasons about improvement, no code runs)        │
│     Mode 2: Mock validation (python -m self_coaching.demo)                          │
│     Mode 3: Real-API mode (env vars → real services)                                │
│                                                                                     │
│   Contains 4 atomic sub-skills:                                                     │
│                                                                                     │
│ ┌───────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌────────────────┐ │
│ │ self-learning     │ │ self-questioning        │ │ self-evaluation   │ │ self-tuning    │ │
│ │                   │ │                  │ │                   │ │                │ │
│ │ "cheapest path"   │ │ "challenge data" │ │ "gating + report"│ │ "most expensive"│ │
│ └────────┬──────────┘ └────────┬─────────┘ └────────┬─────────┘ └────────┬───────┘ │
└──────────┼──────────────────────┼──────────────────────┼──────────────────────┼──────┘
           │                      │                      │                      │
           ▼                      ▼                      ▼                      ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                     RUNTIME: Evolution Loop (clock tick)                              │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐     │
│  │  E-PATH                                                                     │     │
│  │                                                                             │     │
│  │   scoring.py          →  Classifies each task: Σ (failure) or B (success)   │     │
│  │   ┌──────────┐                                                              │     │
│  │   │self-     │  e_path.py learn_from_sigma()                                │     │
│  │   │learning  │  → client.learn(failure_event)                               │     │
│  │   │  SKILL   │  Turns failures into durable artifacts:                      │     │
│  │   │          │    memory, skill patches, experience log entries              │     │
│  │   └──────────┘                                                              │     │
│  │   ┌──────────┐                                                              │     │
│  │   │self-questioning │  e_path.py augment_sigma_sparse() [C06]                      │     │
│  │   │  SKILL   │  → self_questioning_factory.run_suite_self_questioning()                   │     │
│  │   │          │  Generates adversarial eval cases from failure patterns       │     │
│  │   └──────────┘                                                              │     │
│  └─────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐     │
│  │  T-PATH                                                                     │     │
│  │                                                                             │     │
│  │   ┌──────────┐                                                              │     │
│  │   │self-questioning │  t_path.py fill_buffer_batch() [C07]                         │     │
│  │   │  SKILL   │  → self_questioning_factory.run_batch_self_questioning()                   │     │
│  │   │          │  Fills tuning buffer B to batch size β                       │     │
│  │   └──────────┘                                                              │     │
│  │   ┌──────────┐                                                              │     │
│  │   │self-     │  t_path.py → client.train(pipeline, dataset, base_model)     │     │
│  │   │tuning    │  Routes to: mock | AERLTrainAdapter | CLITrainAdapter        │     │
│  │   │  SKILL   │  Returns candidate_model_id                                  │     │
│  │   └──────────┘                                                              │     │
│  │   ┌──────────┐                                                              │     │
│  │   │self-     │  t_path.py → holdout gate (AgentEvals eval)                  │     │
│  │   │evaluation│  Compares candidate vs baseline on holdout suite             │     │
│  │   │  SKILL   │  → promote (generation++) or reject                          │     │
│  │   └──────────┘                                                              │     │
│  └─────────────────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

## Each Skill's Role in the Loop

| Skill | Loop Phase | What the Runtime Does | What the Skill Document Adds |
|-------|-----------|----------------------|------------------------------|
| **self-learning** | E-path (`learn_from_sigma`) | Calls `client.learn()` with a failure event string | Teaches the agent *when* to create memory, skill patches, experience entries vs. just log. Decision table, procedure, pitfalls. |
| **self-questioning** | E-path (C06) + T-path (C07) | Calls `generate_suite` (sparse) or `generate_batch` (batch) | Teaches the agent *how* to design tasks, what roles exist (generator/solver/critic/refiner/curator), schemas, curation gates, `proceed` signal handling. |
| **self-evaluation** | T-path (holdout gate) + E-path (failure routing) | Calls AgentEvals to run candidate on holdout suite, compare vs baseline | Defines eval case schema, promotion gate thresholds, failure routing table (`self-learning` / `self-questioning` / `self-tuning` / `human-review` / `block-and-add-regression`). |
| **self-tuning** | T-path (train) | Calls `client.train()` → CLI adapter or HTTP adapter | Explains backend selection (`mock`/`aerl`/`cli`), AReaL host requirements, stdout marker contract, preflight, smoke tests, when training is appropriate vs. cheaper fixes. |

## The Skill Hierarchy (Cheap → Expensive)

The umbrella `self-coaching` skill explicitly enforces a priority ordering — try cheaper interventions first:

```
1. Memory           ← self-learning   (cheapest: just store a fact)
2. Skill patch      ← self-learning   (fix a procedure)
3. New skill        ← self-learning   (new reusable procedure)
4. Eval case        ← self-evaluation (regression coverage)
5. Self-play tasks  ← self-questioning       (synthetic challenge data)
6. Tool/plugin      ← (external)      (new capability)
7. Training data    ← self-questioning       (curated trajectories)
8. Model training   ← self-tuning     (MOST expensive; only when above fails)
```

The loop runtime enforces this implicitly: the E-path (learn + sparse self-questioning) fires more frequently and cheaply than the T-path (batch self-questioning + train + gate), which only fires during idle windows after buffers are full.

## Skill as Agent Instruction vs. Loop as Automation

The key insight is **dual use**:

- **An autonomous agent reading `SKILL.md`** can apply the methodology manually — classifying observations, patching skills, writing eval cases — without the clock loop running at all (Mode 1: policy reference).
- **The clock scheduler** runs the same methodology as automated code — scoring tasks, triggering E-path/T-path, calling real services — without needing an agent to "read" the skill (Modes 2 & 3).

Both paths produce the same artifacts in `.self-coaching/` and both respect the same gating philosophy. The skills are the *what and why*; the runtime modules are the *how and when*.

```
┌─────────────────────────────────┐     ┌─────────────────────────────────┐
│  Agent (Hermes/LLM) reads SKILL │     │  Clock scheduler runs runtime   │
│  → reasons about improvement    │     │  → ticks every interval_s       │
│  → manually creates artifacts   │     │  → automatically creates same   │
│  → respects same gates          │     │    artifacts via code            │
│                                 │     │                                 │
│  Mode 1: pure policy            │     │  Mode 2/3: automated loop       │
└─────────────────────────────────┘     └─────────────────────────────────┘
              │                                        │
              └────────── Same artifacts ──────────────┘
                     .self-coaching/
                     experience/
                     agents/<id>/meta.json
```