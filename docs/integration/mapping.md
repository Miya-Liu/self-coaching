# AgentEvals → EvalMetrics mapping

Phase 0 deliverable for the [integration plan](../project/integration-plan.md). Confirmed against fixture `tests/fixtures/agentevals/run_detail_succeeded.json` until a live `GET /api/runs/{id}` capture replaces it.

## API surface (AgentEvals)

| Orchestrator need | AgentEvals endpoint | Notes |
|-------------------|----------------------|--------|
| Start eval | `POST /api/runs` | Body: `suite_id`, `agent_config`, optional `num_trials` |
| Poll / report | `GET /api/runs/{run_id}` | Terminal: `succeeded` \| `failed` |
| Suite pick | `GET /api/suites` | Set `AGENTEVALS_SUITE_ID` / `AGENTEVALS_SUITE_ID_HOLDOUT` |

## `RunDetail` → `EvalMetrics`

| `EvalMetrics` field | Source (priority order) |
|---------------------|-------------------------|
| `run_id` | `id` |
| `agent_id` | `agent_config.agent_id` or CLI `--agent-id` |
| `model_checkpoint_id` | `agent_config.version_id` or orchestrator `--candidate` |
| `skill_bundle_version` | CLI `--skill-bundle-version` (not on RunDetail) |
| `score` | `metrics.overall` → `metrics.pass_rate` → mean of numeric `metrics` values |
| `baseline_score` | CLI override; else prior canary row; else `score` |
| `task_scores` | All numeric `metrics` keys except reserved (`overall`, `pass_rate`, `safety`, `cost_usd`, `latency_p95_ms`) |
| `safety_pass_rate` | `metrics.safety` (default `1.0`) |
| `cost_per_task` | `metrics.cost_usd` / `num_trials` (or `1`) |
| `latency_p95_ms` | `metrics.latency_p95_ms` |
| `split` | CLI `--split` (`canary` \| `holdout`) |
| `raw` | Full `RunDetail` JSON |

## Mock-compatible report (adapter internal)

`services/adapters/eval_adapter.py` builds a report shaped like the mock coaching API so `normalize_from_mock_eval()` can be reused when `ORCHESTRATOR_EVAL_BACKEND=agentevals` and the adapter sets `_eval_backend: agentevals` on the summary. Prefer `normalize_from_agentevals()` in the orchestrator when the backend flag is `agentevals`.

## Configuration IDs (staging — fill when services are up)

| Variable | Purpose | Example |
|----------|---------|---------|
| `AGENT_ID` | Production agent UUID | `550e8400-e29b-41d4-a716-446655440000` |
| `AGENTEVALS_SUITE_ID` | Canary / `record-eval` | from `GET /api/suites` |
| `AGENTEVALS_SUITE_ID_HOLDOUT` | Candidate gate in `run` | separate suite |
| `--candidate` / `--baseline` | Maps to `agent_config.version_id` / `baseline_version_id` | version ids, not mock strings |

## Smoke checklist

```bash
# AgentEvals (when :8080 is up)
curl -s http://localhost:8080/health
curl -s http://localhost:8080/api/suites
bash scripts/export-integration-snapshots.sh

# Capture fixture: GET /api/runs/{id} after status succeeded →
#   tests/fixtures/agentevals/run_detail_succeeded.json
```
