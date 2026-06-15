# Deploy T2 / T3 (optional)

T1 skill pack is the default — [deploy-skill-pack.md](deploy-skill-pack.md). This guide covers **Coaching API (T2)** and **evolution engine (T3)** for coach mode or automated loops.

Design: [architecture.md](../design/architecture.md) · Coach mode: [coach_mode.md](../design/coach_mode.md).

## Deploy targets

| Target | Role | Status |
|--------|------|--------|
| **T1** | Skill pack | **Active** — [deploy-skill-pack.md](deploy-skill-pack.md) |
| **T2** | HTTP API (learn / play / eval / train) | Mock complete; production M2 deferred |
| **T3** | `record-eval` → `check-drop` → `run` | M1 done (dry deploy) |

## T2 — Coaching API

```bash
export MOCK_SERVICE_TOKEN="change-me"   # optional locally
python mock-services/mock_self_coaching.py serve \
  --host 127.0.0.1 --port 8765 --root /var/lib/self-coaching/data
```

```python
from client import build_client
c = build_client("http", base_url="http://127.0.0.1:8765", api_key="change-me")
c.learn(event="verification missed", capability="tool_use")
```

Contract: `mock-services/contracts/openapi.yaml`. Mock design: [mock-platform-design.md](../project/mock-platform-design.md).

## T3 — Evolution engine

```bash
python -m services.orchestrator record-eval \
  --coaching-root ./mock-services/demo-run --agent-id prod-agent-1

python -m services.orchestrator check-drop \
  --metrics-dir ./mock-services/demo-run/.self-coaching/metrics

python -m services.orchestrator run \
  --coaching-root ./mock-services/demo-run \
  --run-dir ./runs/improvement-$(date +%Y%m%d-%H%M%S) \
  --agent-id prod-agent-1 --force-trigger
```

Run dir outputs: `current_eval.json`, `candidate_eval.json`, `decision.json`, `deploy_manifest.json`.

HTTP transport to T2:

```bash
export ORCHESTRATOR_TRANSPORT=http
export ORCHESTRATOR_BASE_URL=http://127.0.0.1:8765
export ORCHESTRATOR_EVAL_BACKEND=agentevals   # coach mode typical
```

## Coach mode

Supervise external agents — one coaching root per agent. Full layout, clock service, and cron examples: **[coach_mode.md](../design/coach_mode.md)**.

## Environment matrix

| Concern | T1 | T2 | T3 |
|---------|----|----|-----|
| Python | optional | 3.11+ server | 3.11+ CLI |
| Network | none | inbound HTTP | optional HTTP + AgentEvals |
| Auth | N/A | Bearer token | inherits T2 if HTTP |

## See also

- [roadmap.md](../project/roadmap.md) · [integration-plan.md](../project/integration-plan.md)
- [pipelines.md](../design/pipelines.md) · [evaluators.md](../design/evaluators.md)
