# Coaching API integration (T2)

The **Coaching API** is the HTTP contract spine for pipeline stages: learn, self-play, eval, train. It is the primary HTTP front door for **coach mode** and optional remote execution in **self-coaching mode**.

## Contract

| Artifact | Path |
|----------|------|
| OpenAPI source of truth | `mock-services/contracts/openapi.yaml` |
| Compact JSON (CI sync) | `mock-services/contracts/mock_service_contract.json` |
| Reference server | `mock_self_coaching.py serve` |

## Endpoints (summary)

**In `openapi.yaml` today** (mock CI / T2 facade):

| Tag | Method | Path | Stage |
|-----|--------|------|-------|
| self-learning | POST | `/learning/events` | Sync event (mock + legacy) |
| self-play | POST | `/self-play/generate` | Self-play |
| evaluation | POST | `/eval/runs` | Eval |
| training | POST | `/training/runs` | Train |
| pipeline | POST | `/pipeline/run-all` | End-to-end mock |

**Spec only** — production learner + migration M2; not in `openapi.yaml` until M2.0-T02:

| Tag | Method | Path | Stage |
|-----|--------|------|-------|
| self-learning | POST | `/learning/evolve` | Targeted session review |
| self-learning | POST | `/learning/evolve/recent` | Auto-learn trailing window |
| self-learning | GET | `/learning/status/{job_id}` | Poll async review job |
| self-learning | GET | `/learn/sessions` | Discover candidate sessions |
| self-learning | POST | `/learning/optout` | Per-session learn opt-out |
| self-learning | GET | `/learning/health` | Learner readiness |

Source: [self-learning-review-agent-plan.md](../../project/self-learning-review-agent-plan.md) §4.

## Client transports

`mock-services/client.py`:

| Transport | Use |
|-----------|-----|
| `module` | In-process; default for self-coaching mode + local T3 |
| `http` | Remote T2; default for coach mode |
| `cli` | Subprocess to `mock_self_coaching.py` |

Orchestrator wiring: `ORCHESTRATOR_TRANSPORT=http`, `ORCHESTRATOR_BASE_URL`.

## Composite client

Delegate by capability:

- `evaluate` / `eval_report` → AgentEvals when `ORCHESTRATOR_EVAL_BACKEND=agentevals`
- `train` → AERL when `ORCHESTRATOR_TRAIN_BACKEND=aerl` (`TRAINER_BASE_URL`)
- `learn` / `self_play` → mock services or remote URLs (`MOCK_SELF_LEARNING_URL`, `MOCK_SELF_PLAY_URL`)

One `SelfCoachingClient` interface — see [integrations/README.md](README.md).

## Auth and ops

| Variable | Purpose |
|----------|---------|
| `MOCK_SERVICE_TOKEN` | Bearer on mutating routes (prod) |
| `MOCK_MAX_BODY_BYTES` | Request size cap |

Idempotency: `Idempotency-Key` header → `.self-coaching/idempotency/`.

## Mock vs production (migration phases)

| Mock today | Real backend (env-selected) | Migration phase |
|------------|----------------------------|-----------------|
| Deterministic eval | AgentEvals adapter | **M1 PASS** |
| Sync `POST /learning/events` | Evolve API (`/learning/evolve*`) | **M2** (planned) |
| Local self-play | Remote generator | **M3** |
| Dry-run train | AERL HTTP (`TRAINER_BASE_URL`) | **M4** |

Deploy guide: [deploy-overview.md#t2--coaching-api](../../guides/deploy-overview.md#t2--coaching-api).

## Related

- [pipelines.md](../pipelines.md) — stage semantics
- [aerl.md](aerl.md) — train backend
- [agentevals.md](agentevals.md) — eval backend
- [self-learning-review-agent-plan.md](../../project/self-learning-review-agent-plan.md) — M2 review agent API (DRAFT)
