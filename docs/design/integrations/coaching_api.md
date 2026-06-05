# Coaching API integration (T2)

The **Coaching API** is the HTTP contract spine for pipeline stages: learn, self-play, eval, train. It is the primary HTTP front door for **coach mode** and optional remote execution in **skill mode**.

## Contract

| Artifact | Path |
|----------|------|
| OpenAPI source of truth | `mock-services/contracts/openapi.yaml` |
| Compact JSON (CI sync) | `mock-services/contracts/mock_service_contract.json` |
| Reference server | `mock_self_coaching.py serve` |

## Endpoints (summary)

| Tag | Method | Path | Stage |
|-----|--------|------|-------|
| self-learning | POST | `/learning/events` | self-learning submodule |
| self-play | POST | `/self-play/generate` | Self-play |
| evaluation | POST | `/eval/runs` | Eval |
| training | POST | `/training/runs` | Train |
| pipeline | POST | `/pipeline/run-all` | End-to-end mock |

## Client transports

`mock-services/client.py`:

| Transport | Use |
|-----------|-----|
| `module` | In-process; default for skill mode + local T3 |
| `http` | Remote T2; default for coach mode |
| `cli` | Subprocess to `mock_self_coaching.py` |

Orchestrator wiring: `ORCHESTRATOR_TRANSPORT=http`, `ORCHESTRATOR_BASE_URL`.

## Composite client (planned / partial)

Delegate by capability:

- `evaluate` / `eval_report` → AgentEvals when `ORCHESTRATOR_EVAL_BACKEND=agentevals`
- `learn` / `self_play` / `train` → mock or AERL until adapters complete

One `SelfCoachingClient` interface — see [integrations/README.md](README.md).

## Auth and ops

| Variable | Purpose |
|----------|---------|
| `MOCK_SERVICE_TOKEN` | Bearer on mutating routes (prod) |
| `MOCK_MAX_BODY_BYTES` | Request size cap |

Idempotency: `Idempotency-Key` header → `.self-coaching/idempotency/`.

## Mock vs production (M2)

| Mock today | Real backend (env-selected) |
|------------|----------------------------|
| Deterministic eval | AgentEvals adapter |
| Dry-run train | AERL HTTP (`TRAINER_BASE_URL`) |
| Local self-play | Remote generator (M3) |

Deploy guide: [deploy-overview.md#t2--coaching-api](../../guides/deploy-overview.md#t2--coaching-api).

## Related

- [pipelines.md](../pipelines.md) — stage semantics
- [aerl.md](aerl.md) — train backend
- [agentevals.md](agentevals.md) — eval backend
