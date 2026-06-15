# coach mode

**Status:** **roadmap M5 in progress** — supervision registry, **coach clock 24×7 service**, and `mock-coach-demo.sh` shipped; production `agent_chat_url` bridge and LLM proxy still open. Design: [coach_mode.md](../../docs/design/coach_mode.md). Task status: [progress.md](../../docs/project/progress.md).

**Local demo (no external services):** `bash scripts/mock-coach-demo.sh` — uses `agents.demo.yaml`.

**Autonomous clock (one evolution tick):** `python modes/coach/clock.py run --root <coaching-root>` — E-path → sparse/batch self-play → T-path; smoke: `python scripts/clock_loop_smoke.py`.

**Coach clock service (24×7):** after registering agents, accept inbound posts over HTTP or WebSocket; each post triggers agent clock setup → evolution tick:

```bash
python modes/coach/service.py serve \
  --registry modes/coach/agents.clock.yaml \
  --bind 127.0.0.1:8768

# optional WebSocket (pip install -e ".[coach]")
python modes/coach/service.py serve --registry modes/coach/agents.clock.yaml \
  --bind 127.0.0.1:8768 --ws-port 8769
```

```bash
curl -s -X POST http://127.0.0.1:8768/coach/post \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"clock-demo-agent","event":"session_complete","payload":{"action":"full_tick"}}'
```

Coach mode runs the shared **evolution engine** (`services/orchestrator/`) to supervise **external agents**. It does **not** duplicate submodules — it invokes the same **self-learning**, **self-play**, **self-evaluation**, and **self-tuning** pipelines via `SelfCoachingClient` and adapters.

| Component | Purpose | Repo path |
|-----------|---------|-----------|
| Supervision registry | Per-agent id, coaching root, eval schedule, `coach_clock` | `agents.example.yaml`, `registry.py` |
| Coach clock service | 24×7 HTTP `POST /coach/post` + optional WebSocket | `service.py`, `ws_server.py`, `trigger.py` |
| Evolution tick | One autonomous E→P→T cycle | `clock.py` |
| Agent bridge | Ask supervised agent to set up clock on post (mock or `agent_chat_url`) | `agent_bridge.py` |
| Cron scheduler | `record-eval` / `check-drop` / `run` per agent | [coach_mode.md](../../docs/design/coach_mode.md) § Scheduler |
| LLM proxy (optional) | Trajectory capture only; scored eval on AgentEvals | (planned) |

```python
from modes.coach.registry import load_registry, default_registry_path

for agent in load_registry(default_registry_path()):
    print(agent.id, agent.coaching_root, agent.coach_clock)
```

Copy `agents.example.yaml` → `agents.yaml` and edit paths for your deployment.

Eval: **AgentEvals**. Deploy: production **agent API**. Train: **AERL** / **self-tuning**. Spec: [coach_mode.md](../../docs/design/coach_mode.md).
