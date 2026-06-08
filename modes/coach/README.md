# coach mode

**Status:** supervision registry + mock coach demo (Phase 4); scheduler and proxy still planned — [roadmap.md](../../docs/project/roadmap.md).

**Local demo (no external services):** `bash scripts/mock-coach-demo.sh` — uses `agents.demo.yaml`.

Coach mode runs the shared **evolution engine** (`services/orchestrator/`) to supervise **external agents**. It does **not** duplicate submodules — it invokes the same **self-learning**, **self-play**, **self-evaluation**, and **self-tuning** pipelines via `SelfCoachingClient` and adapters.

| Component | Purpose | Repo path |
|-----------|---------|-----------|
| Supervision registry | Per-agent id, model, eval schedule, coaching root, improvement policy | `agents.example.yaml`, `registry.py` |
| Scheduler | Cron/systemd → `record-eval` / `check-drop` / `run` per agent | (examples in [coach_mode.md](../../docs/design/coach_mode.md)) |
| LLM proxy (optional) | Trajectory capture only; scored eval on AgentEvals | (planned) |

```python
from modes.coach.registry import load_registry, default_registry_path

for agent in load_registry(default_registry_path()):
    print(agent.id, agent.coaching_root)
```

Copy `agents.example.yaml` → `agents.yaml` and edit paths for your deployment.

Eval: **AgentEvals**. Deploy: production **agent API**. Train: **AERL** / **self-tuning**. Spec: [coach_mode.md](../../docs/design/coach_mode.md).
