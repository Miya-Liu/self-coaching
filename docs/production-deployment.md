# Production deployment guide

## Active deploy target: **T1 — Skill pack**

This repository is currently shipped and supported as a **portable skill pack** (markdown + Bash). T2 (HTTP API) and T3 (orchestrator) are optional add-ons — see [roadmap.md](roadmap.md).

**Canonical T1 guide:** [`deploy-t1-skill-pack.md`](deploy-t1-skill-pack.md)

```bash
bash scripts/install-skill-pack.sh . --with-mock
```

---

## All deploy targets

| If you need… | Deploy | Start here |
|--------------|--------|------------|
| Agents to follow coaching **policy** (skills, experience logs, manual training) | **T1 — Skill pack** ✓ **active** | [deploy-t1-skill-pack.md](deploy-t1-skill-pack.md) |
| A **stable HTTP API** for learn / eval / train from your agent platform | **T2 — Coaching API** | [Coaching API](#t2--coaching-api) |
| **Automatic** improve-on-eval-drop with artifacts and gates | **T3 — Pipeline** | [Self-improving pipeline](#t3--self-improving-pipeline) |

Adopt T2/T3 when you outgrow file-based skills; T1 remains valid without them.

---

## T1 — Skill pack (summary)

**Artifacts:** Clone/copy repo → agent skill path. Version: `SKILL_PACK_VERSION`.

**Runtime:** None required (Bash + optional Python for mock dry-run).

**One-command install:** `bash scripts/install-skill-pack.sh [root] [--with-mock]`

**Secrets:** Never commit `self-coaching-training/services/.env`.

**Upgrade:** Pull tree → compare `SKILL_PACK_VERSION` → re-run install script; see [CHANGELOG-skills.md](CHANGELOG-skills.md).

---

## T2 — Coaching API

**Artifacts:** Python process `mock_self_coaching.py serve` (mock) or a future real implementation behind the same OpenAPI contract.

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
| `MOCK_SERVICE_TOKEN` | When set, requires `Authorization: Bearer <token>` (except `GET /health`) |
| `MOCK_MAX_BODY_BYTES` | Max POST body (default 1 MiB) |

**Production (M2, planned):** container image, sqlite volume, async training endpoints, AERL/AgentEvals adapters — see [`roadmap.md`](roadmap.md) M2.

---

## T3 — Self-improving pipeline

**Artifacts:** Orchestrator CLI + per-run directories under a coaching root.

**Runtime:** Cron, systemd timer, or manual invocation after eval metrics are recorded.

**Coaching root:** Directory containing `experience/` and `.self-coaching/` (same layout as mock `run-all`).

### Record production metrics

After an eval (mock or real), append normalized metrics:

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

**Transport:** Default `module` (in-process mock). For a remote API:

```bash
export ORCHESTRATOR_TRANSPORT=http
export ORCHESTRATOR_BASE_URL=http://127.0.0.1:8765
export MOCK_SERVICE_TOKEN=change-me
```

**Production (M3–M4, planned):** real curation, holdout gates, canary deploy script — see [`roadmap.md`](roadmap.md).

---

## Environment matrix

| Concern | T1 | T2 | T3 |
|---------|----|----|-----|
| Python | 3.11+ for mocks/tests | 3.11+ server | 3.11+ orchestrator |
| Network | None | Inbound HTTP | Optional HTTP to T2 |
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

- [`roadmap.md`](roadmap.md) — milestones M0–M4
- [`progress.md`](progress.md) — component status table
- [`pipeline.md`](pipeline.md) — full loop design
