# AgentEvals integration

**AgentEvals** is the primary **benchmark evaluator** for coach mode and optional skill-mode automation. It supplies async suite runs whose metrics normalize to `EvalMetrics` for drop detection and promotion gates.

Design context: [evaluators.md](../evaluators.md). Field mapping table: [integration/mapping.md](../../integration/mapping.md). Implementation plan: [integration-plan.md](../../project/integration-plan.md) Phase 1.

## Role

| Use | Split | When |
|-----|-------|------|
| Canary monitoring | `canary` | `record-eval`, scheduled coach runs |
| Promotion gate | `holdout` | `run` → `candidate_eval.json` |

**Not replaced by:** LLM proxy (observation only), production agent smoke endpoints, or training metrics.

## API surface

| Evolution engine need | AgentEvals endpoint |
|-----------------------|---------------------|
| Start eval | `POST /api/runs` — `suite_id`, `agent_config`, `num_trials` |
| Poll / report | `GET /api/runs/{run_id}` — `queued` → `running` → `succeeded` \| `failed` |
| Suite selection | `GET /api/suites` |

**Mock (Phase 0):** `mock-services/mock_agentevals.py serve` implements the above plus mock-only `POST /api/suites` for customised suite registration. See [`mock-platform-design.md`](../../project/mock-platform-design.md).

## Adapter contract

Implement same semantics as `SelfCoachingClient.evaluate()` and `eval_report()`:

| Mock Coaching API | AgentEvals |
|-------------------|------------|
| `POST /eval/runs` | `POST /api/runs` |
| Poll + `GET /eval/runs/{id}/report` | `GET /api/runs/{id}` when complete |

Normalizer: `normalize_from_agentevals()` in `services/orchestrator/eval_metrics.py`.

## Identity in eval runs

Pass production lineage in `RunCreate.agent_config` (opaque dict):

- `agent_id` — supervised subject
- `version_id` — candidate or baseline checkpoint

Orchestrator flags `--candidate` / `--baseline` map to these fields (not mock strings like `mock-baseline-v0`).

## `RunDetail` → `EvalMetrics` (summary)

| `EvalMetrics` | Source (typical) |
|---------------|------------------|
| `score` | `metrics.overall` → `metrics.pass_rate` → mean of task scores |
| `task_scores` | Per-slice keys in `metrics` |
| `safety_pass_rate` | `metrics.safety` |
| `cost_per_task` | `metrics.cost_usd` / trial count |
| `latency_p95_ms` | `metrics.latency_p95_ms` |
| `raw` | Full `RunDetail` JSON |

Full priority order: [integration/mapping.md](../../integration/mapping.md).

## Configuration

| Variable | Purpose |
|----------|---------|
| `ORCHESTRATOR_EVAL_BACKEND` | Set `agentevals` |
| `AGENTEVALS_BASE_URL` | e.g. `http://localhost:8080` |
| `AGENTEVALS_SUITE_ID` | Canary suite |
| `AGENTEVALS_SUITE_ID_HOLDOUT` | Holdout suite for `run` |
| `AGENTEVALS_POLL_INTERVAL_S` | Poll loop |
| `AGENTEVALS_TIMEOUT_S` | Max wait |

## Code

| Path | Role |
|------|------|
| `services/adapters/agentevals_client.py` | HTTP client |
| `services/adapters/eval_adapter.py` | `evaluate`, `eval_report` |
| `tests/fixtures/agentevals/` | Fixture `RunDetail` |

## Smoke

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/api/suites
bash scripts/export-integration-snapshots.sh
```

Snapshot target: `docs/integration/api-snapshots/agentevals-openapi.json`.
