# coach mode

**Status:** **roadmap M5 in progress** — supervision registry, **coach clock 24×7 service**, `mock-coach-demo.sh`, the **live `AgentCoachBridge`** (planner slice), **partial-action routing** (`learn`/`play`/`tune`), and **live subject driving** (`subject_chat_url` → `SubjectTaskSource`) shipped. Design: [coach_mode.md](../../docs/design/coach_mode.md). Task status: [progress.md](../../docs/project/progress.md).

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

### Coach brain selection (`COACH_BRIDGE`)

By default the service uses the deterministic `MockCoachAgentBridge` (CI-safe, rule-based). To delegate the tick decision to a **live coach agent** (OpenClaw / Hermes / any OpenAI-style `/chat/completions` endpoint), set:

```bash
export COACH_BRIDGE=agent                       # mock (default) | agent
export COACH_AGENT_URL=http://127.0.0.1:8000    # required for 'agent'
export COACH_AGENT_API_KEY=...                  # optional bearer token
export COACH_AGENT_MODEL=qwen3-8b               # optional model name
export COACH_AGENT_PATH=/chat/completions       # optional (default /chat/completions)
export COACH_AGENT_TIMEOUT_S=60                 # optional (default 60)

python modes/coach/service.py serve --registry modes/coach/agents.clock.yaml
```

The coach agent receives the loop state (generation, Σ, buffer B) plus the inbound post and returns a `ClockPlan` JSON: `{"action": "hold"|"learn"|"play"|"tune"|"full_tick", "reason": "...", "scenario_overrides": {}}`. On transport failure or unparseable output the bridge **fails safe to `hold`**. Every decision is audited under `{coaching_root}/.self-coaching/coach/audit/{agent_id}/`.

> **Phase 1.5 + 2 shipped:** `learn`/`play`/`tune` are distinct partial routes (E-path / C07 self-play / T-path). When `coach_clock.subject_chat_url` is set, the loop drives that live agent for real trajectories (`SubjectTaskSource`); when unset it uses fixture task streams (CI-safe). This enables both **cross-coaching** (subject ≠ coach) and **self-coaching** (subject = coach).
>
> **Operational notes:**
> - `subject_chat_url` may be a bare base (`http://host:8000` → `/chat/completions` appended) or a full endpoint (`http://host:8000/chat` → used as-is). The legacy `agent_chat_url` alias still parses.
> - If the subject is unreachable, the tick currently **fails with an error** (it does not fall back to `hold` like the coach brain does). Treat subject availability as a precondition.
> - The `coach-clock run` CLI uses **fixtures only** — live subject driving is wired through the coach service (`POST /coach/post` / scheduler), not the standalone CLI.

The service does not auto-load `.env`; export the variables (or `set -a; source your.env; set +a`) before launching.

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
| Agent bridge | Decide tick action on post: `mock` (rule-based) or `agent` (live coach via `COACH_AGENT_URL`) | `agent_bridge.py`, `agent_bridge_live.py` |
| Cron scheduler | `record-eval` / `check-drop` / `run` per agent | [coach_mode.md](../../docs/design/coach_mode.md) § Scheduler |
| LLM proxy (optional) | Trajectory capture only; scored eval on AgentEvals | (planned) |

```python
from modes.coach.registry import load_registry, default_registry_path

for agent in load_registry(default_registry_path()):
    print(agent.id, agent.coaching_root, agent.coach_clock)
```

Copy `agents.example.yaml` → `agents.yaml` and edit paths for your deployment.

Eval: **AgentEvals**. Deploy: production **agent API**. Train: **AERL** / **self-tuning**. Spec: [coach_mode.md](../../docs/design/coach_mode.md).
