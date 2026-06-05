# coach mode (planned shell)

**Status:** design reference — implementation in M5 ([roadmap.md](../../docs/project/roadmap.md)).

Coach mode runs the shared **evolution engine** (`services/orchestrator/`) to supervise **external agents**. It does **not** duplicate submodules — it invokes the same **self-learning**, **self-play**, **self-evaluation**, and **self-tuning** pipelines via `SelfCoachingClient` and adapters.

| Component | Purpose |
|-----------|---------|
| Supervision registry | Per-agent id, model, eval schedule, coaching root, improvement policy |
| Scheduler | Cron/systemd → `record-eval` / `check-drop` / `run` per agent |
| LLM proxy (optional) | Trajectory capture only; scored eval on AgentEvals |

Eval: **AgentEvals**. Deploy: production **agent API**. Train: **AERL** / **self-tuning**. Spec: [coach_mode.md](../../docs/design/coach_mode.md).
