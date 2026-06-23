# Mock services (T2 + M1.5 mock platform)

Local mocks for the evolution loop without real LLM, trainer, evaluator, or external APIs.

| Service | Port (default) | Module |
|---------|----------------|--------|
| **Coaching API** (learn / self-questioning / train) | 8765 | `mock_self_coaching.py` |
| **AgentEvals** (suites + async runs) | 8080 | `mock_agentevals.py` |
| **Agent registry** (version lineage) | 8768 (optional) | `mock_agent_registry.py` |
| **Self-learning** (classify + version drafts) | 8766 | `mock_self_learning.py` |
| **Self-questioning** (suite registration + curation) | 8767 | `mock_self_questioning.py` |

Design: [`docs/project/mock-platform-design.md`](../docs/project/mock-platform-design.md) · [`coaching_api.md`](../docs/design/integrations/coaching_api.md).

### Phase 0 quick start

```bash
bash scripts/mock-agentevals-smoke.sh
bash scripts/mock-stack-up.sh mock-services/demo-stack --with-coaching
```

When `MOCK_AGENTEVALS_URL` or `AGENTEVALS_BASE_URL` is set, `mock_self_coaching.py evaluate` delegates to mock AgentEvals.

`learn()` uses `MockSelfLearningEngine` in-process by default (classification + registry drafts). Set `MOCK_SELF_LEARNING_URL` to call the HTTP service on `:8766`.

`self_questioning()` uses `MockSelfQuestioningEngine` in-process (registers AgentEvals suites + runs `curate_data.py`). Set `MOCK_SELF_QUESTIONING_URL` for HTTP on `:8767`. Phase 2 endpoint: `POST /self-questioning/generate-suite`.

```bash
export AGENTEVALS_BASE_URL=http://127.0.0.1:8080
export ORCHESTRATOR_EVAL_BACKEND=agentevals
export AGENTEVALS_SUITE_ID=tool-use-canary
python -m services.orchestrator record-eval --coaching-root mock-services/demo-stack --agent-id example-agent
```

---

## Mock Coaching API (T2)

Local mock implementation of the **Coaching API** contract for testing the full evolution-engine loop. Shared by Self-coaching mode (optional) and Coach mode.

It provides three interface styles:

1. CLI: `python mock_self_coaching.py <command>`
2. Python module: import functions from `mock_self_coaching.py` or `plugin_mock.py`
3. HTTP mock service: `python mock_self_coaching.py serve --root <demo-root> --port 8765`

## Full Pipeline Smoke Test

From the repository root (or wherever the skill is installed — set `SKILL_ROOT` accordingly):

```bash
python "$SKILL_ROOT/mock-services/mock_self_coaching.py" run-all \
  --root "$SKILL_ROOT/mock-services/demo-run" \
  --capability tool_use \
  --pipeline sft
```

Or, when running from the repo root directly, the relative form is fine:

```bash
python mock-services/mock_self_coaching.py run-all \
  --root mock-services/demo-run \
  --capability tool_use \
  --pipeline sft
```

Expected artifacts:

```text
demo-run/
  experience/
    EXPERIMENT_LOG.md
    ERROR.md
    LEARNINGS.md
  .self-coaching/
    events/learning_events.jsonl
    cases/self_questioning_candidates.jsonl
    cases/eval_cases.jsonl
    curated/train.jsonl
    reports/eval_runs/<run_id>/report.json
    reports/eval_runs/<run_id>/summary.md
    manifests/training_run_manifest.json
    manifests/mock_pipeline_summary.json
    logs/<train_run_id>.log
```

## CLI Contract

```bash
python mock_self_coaching.py init --root <root>
python mock_self_coaching.py learn --root <root> --event "Agent forgot verification"
python mock_self_coaching.py self-questioning --root <root> --capability tool_use --n 4
python mock_self_coaching.py evaluate --root <root> --candidate mock-candidate-v1 --baseline mock-baseline-v0
python mock_self_coaching.py train --root <root> --pipeline sft
python mock_self_coaching.py run-all --root <root>
```

## HTTP Contract

Start the service:

```bash
python mock_self_coaching.py serve --root ./demo-run --port 8765
```

Endpoints:

- `GET /health`
- `POST /learning/events` with `{"event":"...","source":"http","capability":"tool_use"}`
- `POST /self-questioning/generate` with `{"capability":"tool_use","n":4}`
- `POST /eval/runs` with `{"candidate":"mock-candidate-v1","baseline":"mock-baseline-v0"}`
- `GET /eval/runs/{run_id}/report`
- `POST /training/runs` with `{"pipeline":"sft"}` (delegates to mock AERL when `MOCK_AERL_URL` / `TRAINER_BASE_URL` set)

### Mock AERL (`mock_aerl.py`, Phase 3)

```bash
python mock-services/mock_aerl.py serve --data-dir ./demo-stack --port 8004
export MOCK_AERL_URL=http://127.0.0.1:8004
export ORCHESTRATOR_TRAIN_BACKEND=aerl
```

- `POST /v1/training/runs` — async training (`queued` → `succeeded`, `candidate_model_id`)
- `GET /v1/training/runs/{id}` — poll run status
- `POST /v1/pipelines/{sft|grpo}/run` — argv endpoint for `run-pipeline.sh`

### Coach demo (Phase 4)

```bash
bash scripts/mock-coach-demo.sh
```

Full mock stack, two supervised agents (`modes/coach/agents.demo.yaml`), drop-triggered improvement runs, promote vs reject with registry activation.

### Production-readiness + facade run-all

```bash
bash scripts/mock-production-readiness.sh
bash scripts/mock-facade-run-all.sh
```

`production_readiness.py` checks pipeline phases, `validation.jsonl` / `holdout.jsonl`, and split hygiene.
- `POST /pipeline/run-all` with `{"capability":"tool_use","pipeline":"sft"}`

Formal contract (including auth and idempotency): `contracts/openapi.yaml`.

### HTTP hardening (mock)

| Env var | Purpose |
|---------|---------|
| `MOCK_SERVICE_TOKEN` | When set, all endpoints except `GET /health` require `Authorization: Bearer <token>`. Unset = auth disabled (local default). |
| `MOCK_MAX_BODY_BYTES` | Max POST body size (default 1 MiB). Oversized bodies return `413`. |

Mutating `POST` endpoints accept optional `Idempotency-Key`. Replays within ~24h return the cached response (stored under `.self-coaching/idempotency/`).

### Python client

```python
from client import HTTPClient, build_client

client = build_client("http", base_url="http://127.0.0.1:8765", api_key="your-token")
client.learn(event="...", headers={"X-Request-ID": "req-1"})  # Idempotency-Key auto on POST
```

`HTTPClient` reads `MOCK_SERVICE_TOKEN` from the environment when `api_key` is omitted.

## Design Notes

- Deterministic and stdlib-only.
- No real credentials, model calls, or training jobs.
- Produces the same artifact shapes expected by the self-coaching skills.
- Stores observable traces and summaries, not hidden private chain-of-thought.
- Intended for local pipeline validation and skill demos only.
