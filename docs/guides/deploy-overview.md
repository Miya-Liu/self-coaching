# Production deployment guide

Design: [architecture.md](../design/architecture.md) · [self_coaching_mode.md](../design/self_coaching_mode.md) · [coach_mode.md](../design/coach_mode.md).

## Active deploy target: **T1 — Self-coaching pack** (Self-coaching mode)

This repository ships and supports **Self-coaching mode** as a portable skill pack (markdown + Bash). T2 (Coaching API) and T3 (evolution engine) are optional add-ons for automation and coach mode — mock T2 is complete; production M2 deploy is deferred. See [roadmap.md](../project/roadmap.md).

**Canonical T1 guide:** [`deploy-skill-pack.md`](deploy-skill-pack.md)

```bash
bash scripts/install-skill-pack.sh . --with-mock
```

---

## Deployment modes

| Mode | Executor | Subject | Primary deploy |
|------|----------|---------|----------------|
| **Self-coaching mode** | Host agent | Same host agent | **T1** |
| **Coach mode** | Coach service / scheduler | External registered agents | **T2 + T3** |

Both modes share the **evolution engine**, pipeline stages, adapters (AgentEvals, agent API, AERL), and artifact contracts. Only executor, subject, and coaching-root layout differ.

---

## Deploy targets (T1 / T2 / T3)

| If you need… | Deploy | Mode | Start here |
|--------------|--------|------|------------|
| Installable skills and local experiment workflow | **T1 — Self-coaching pack** ✓ **active** | Self-coaching | [deploy-skill-pack.md](deploy-skill-pack.md) |
| Stable HTTP API for learn / eval / train | **T2 — Coaching API** | Coach (also self-coaching optional) | [Coaching API](#t2--coaching-api) |
| Automated improve-on-eval-drop with gates | **T3 — Evolution engine** | Coach (also self-coaching optional) | [Evolution engine](#t3--evolution-engine) |

Adopt T2/T3 when you need HTTP integration or coach-mode supervision; T1 remains valid without them.

---

## T1 — Self-coaching pack (Self-coaching mode)

**Artifacts:** `modes/self-coaching/` (or full repo clone). Version: `modes/self-coaching/SKILL_PACK_VERSION`.

**Runtime:** None required (Bash + optional Python for mock dry-run).

**One-command install:** `bash scripts/install-skill-pack.sh [root] [--with-mock]`

**Coaching root:** Project or skill install directory (`experience/` + `.self-coaching/` after init).

**Secrets:** Never commit `modes/self-coaching/self-tuning/services/.env`.

**Upgrade (Hermes Agent):** `git pull` in your clone → `bash scripts/update-skill-pack.sh --hermes [--dry-run]`. Installed copy records `installed_sha` in `~/.hermes/skills/self-coaching/SKILL_PACK_VERSION`. See [install-as-hermes-skill.md](install-as-hermes-skill.md).

**Upgrade (repo clone / pack copy / Cursor):** Pull or replace the tree → compare `modes/self-coaching/SKILL_PACK_VERSION` → re-copy `modes/self-coaching/` or re-run `bash scripts/install-skill-pack.sh <root>`. See [deploy-skill-pack.md#upgrade](deploy-skill-pack.md#upgrade) and [changelog-skills.md](../project/changelog-skills.md).

---

## T2 — Coaching API

**Status:** T2 has a complete mock implementation (facade + split services) suitable for demos and CI — see [mock-platform-design.md](../project/mock-platform-design.md). Production T2 (M2: Docker, sqlite, async training, real adapters) is deferred.

HTTP **contract spine** for pipeline stages (learn, self-play, eval, train). Used as the coach-mode front door; self-coaching mode can call it when pipelines run remotely.

**Artifacts:** Python process `mock_self_coaching.py serve` (mock) or real adapters behind the same OpenAPI contract.

**Runtime:** One long-lived HTTP listener per environment.

**Minimal local run**

```bash
export MOCK_SERVICE_TOKEN="change-me"   # optional locally; required in prod
python mock-services/mock_self_coaching.py serve \
  --host 127.0.0.1 --port 8765 --root /var/lib/self-coaching/data
```

**Client**

```python
from client import build_client
c = build_client("http", base_url="http://127.0.0.1:8765", api_key="change-me")
c.learn(event="verification missed", capability="tool_use")
```

**Environment**

| Variable | Purpose |
|----------|---------|
| `MOCK_SERVICE_TOKEN` | When set, requires `Authorization: Bearer ${MOCK_SERVICE_TOKEN}` (except `GET /health`) |
| `MOCK_MAX_BODY_BYTES` | Max POST body (default 1 MiB) |

**Production (M2, planned):** container image, sqlite volume, async training endpoints, AERL/AgentEvals adapters — see [roadmap.md](../project/roadmap.md) M2.

---

## T3 — Evolution engine

Automated loop: `record-eval` → `check-drop` → `run` (learn / self-play / train / candidate eval / deploy gate).

**Artifacts:** `services/orchestrator/` CLI + per-run directories under a coaching root.

**Runtime:** Cron, systemd timer, or manual invocation after eval metrics are recorded.

**Coaching root:** Directory containing `experience/` and `.self-coaching/` (same layout as mock `run-all`). In coach mode, **one root per supervised agent**.

### Record metrics

After an eval (mock or AgentEvals), append normalized `EvalMetrics`:

```bash
python -m services.orchestrator record-eval \
  --coaching-root ./mock-services/demo-run \
  --agent-id prod-agent-1 \
  --candidate mock-candidate-v1 \
  --baseline mock-baseline-v0
```

### Check for a performance drop

```bash
python -m services.orchestrator check-drop \
  --metrics-dir ./mock-services/demo-run/.self-coaching/metrics
```

Exit code `1` means a drop was detected (suitable for cron triggering).

### Run improvement (dry deploy)

```bash
python -m services.orchestrator run \
  --coaching-root ./mock-services/demo-run \
  --run-dir ./runs/improvement-$(date +%Y%m%d-%H%M%S) \
  --agent-id prod-agent-1 \
  --force-trigger          # optional: skip drop check for demos
```

**Run directory outputs**

| File | Meaning |
|------|---------|
| `improvement_run_manifest.json` | Run id, path choice, versions |
| `current_eval.json` | `EvalMetrics` at trigger time |
| `candidate_eval.json` | `EvalMetrics` after improvement |
| `decision.json` | promote / reject / dry_run_only |
| `deploy_manifest.json` | Dry-run deploy record (no live traffic change) |

**Transport:** Default `module` (in-process mock). For T2 HTTP:

```bash
export ORCHESTRATOR_TRANSPORT=http
export ORCHESTRATOR_BASE_URL=http://127.0.0.1:8765
export MOCK_SERVICE_TOKEN=change-me
export ORCHESTRATOR_EVAL_BACKEND=agentevals   # coach mode typical
```

**Production (M3–M4, planned):** real curation, holdout gates, canary deploy — see [roadmap.md](../project/roadmap.md).

---

## Coach mode

Supervise **external agents**: periodic evaluation (AgentEvals), drop detection, improvement runs, and platform deploy (production agent API).

### Layout (multi-agent)

```text
/var/lib/coach/
  agents/<agent_id>/          # coaching root per subject
    experience/
    .self-coaching/
      metrics/eval_metrics.jsonl
  runs/<improvement_run_id>/  # orchestrator output
```

### Scheduler (today)

Per agent, on cron or interval:

```bash
ROOT=/var/lib/coach/agents/support-bot-prod
AGENT_ID=support-bot-prod

python -m services.orchestrator record-eval \
  --coaching-root "$ROOT" --agent-id "$AGENT_ID" \
  --candidate <version_id> --baseline <version_id>

python -m services.orchestrator check-drop \
  --metrics-dir "$ROOT/.self-coaching/metrics" \
  || python -m services.orchestrator run \
       --coaching-root "$ROOT" \
       --run-dir /var/lib/coach/runs/$(date +%Y%m%d-%H%M%S) \
       --agent-id "$AGENT_ID"
```

Set `ORCHESTRATOR_EVAL_BACKEND=agentevals`, `AGENTEVALS_*`, and `AGENT_API_*` per [integration-plan.md](../project/integration-plan.md).

### Planned coach shell (M5)

| Component | Purpose | Path |
|-----------|---------|------|
| Supervision registry | External agent id, model, eval schedule, coaching root | `modes/coach/` (planned) |
| LLM proxy | Optional trajectory capture for supervised agents | `modes/coach/proxy/` (planned) |

The LLM proxy is an **observation adapter** only — scored evaluation stays on AgentEvals.

---

## Environment matrix

| Concern | T1 (self-coaching) | T2 | T3 |
|---------|------------|----|----|
| Python | 3.11+ for mocks/tests | 3.11+ server | 3.11+ evolution engine |
| Network | None | Inbound HTTP | Optional HTTP to T2; AgentEvals / agent API in coach mode |
| Persistent disk | `experience/`, `logs/` | Coaching root volume | Coaching root + `runs/` |
| Auth | N/A | Bearer token | Inherits T2 if HTTP |

---

## Health checks

| Target | Check |
|--------|--------|
| T2 | `GET /health` → 200 |
| T3 | `check-drop` exit 0 when healthy; last line in `eval_metrics.jsonl` parseable |

---

## See also

- [design/README.md](../design/README.md) — design index
- [pipelines.md](../design/pipelines.md) — evolution engine
- [evaluators.md](../design/evaluators.md) — metrics and gates
- [integrations/](../design/integrations/) — external adapters
- [roadmap.md](../project/roadmap.md) — milestones M0–M5
- [integration-plan.md](../project/integration-plan.md) — implementation plan
