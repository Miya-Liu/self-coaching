# Self-coaching deployment roadmap

This document is the execution plan for taking the repository from **skill demo + mock API** to a **deployable self-improving loop** aligned with [`pipeline.md`](../design/pipeline.md).

## Deploy targets (decision)

We ship three targets in order. Each has a clear audience and exit criterion.

| Target | What gets deployed | Audience | Status |
|--------|-------------------|----------|--------|
| **T1 — Skill pack** | Markdown skills + `scripts/` + `experience/` layout | Humans and agents following `SKILL.md` | **Active — ship now** |
| **T2 — Coaching API** | `mock_self_coaching.py serve` → later real eval/train adapters | Integrators calling `client.HTTPClient` | **Deferred**; mock ready when needed |
| **T3 — Self-improving pipeline** | `services/orchestrator` + metrics store + drop detector | Operators running closed-loop improvement | **Built (M1)**; optional until T2 adapters |

**Primary focus:** **T1 / M0** — skill pack install, doctor, and onboarding. See [`deploy-skill-pack.md`](../guides/deploy-skill-pack.md).

```text
[T1 skills]          agent reads SKILL.md, runs bash locally
[T2 coaching API]    HTTP/CLI/module  ← contract spine (OpenAPI)
[T3 orchestrator]    drop → run_dir → improve → gate → dry deploy
                              │
                              └── calls T2 via ModuleClient or HTTPClient
```

## Architecture spine

One orchestrator, many adapters — not nine separate integration projects.

| Layer | Repo path | Role |
|-------|-----------|------|
| Policy | `SKILL.md`, `self-coaching-*/` | How an agent should behave |
| Contract | `mock-services/contracts/openapi.yaml` | HTTP surface for learn / self-play / eval / train |
| Client | `mock-services/client.py` | Module, CLI, HTTP transports |
| Orchestrator | `services/orchestrator/` | `pipeline.md` loop, metrics, drop detection |
| Adapters (later) | `services/adapters/` (planned) | AgentEvals, AERL, trajectory DB |

## Milestones

### M0 — Baseline (skill pack deployable) ✓

- [x] CI: doctor, shellcheck, pytest, mock smoke `run-all`
- [x] `scripts/install-skill-pack.sh` + `docs/guides/deploy-skill-pack.md`
- [x] `SKILL_PACK_VERSION` + `project/changelog-skills.md`
- [x] Shell strictness on shipped scripts; `run-once.sh` python fallback
- [x] `preflight.sh` AERL_ROOT sanity; registry documents `TRAINER_BASE_URL`
- [x] `docs/guides/deploy-overview.md` — T1 as active target
- [x] Git tag `v0.2.0-skills` on release

**Exit:** `bash scripts/install-skill-pack.sh . --with-mock` succeeds on a clean machine with bash + python. Verified 2026-05-29 (Git Bash + Python; `jq` required for AERL pipelines).

**Next focus:** M2 + integration Phase 0–1 (see [`integration-plan.md`](integration-plan.md)).

### M1 — Orchestrator + dry loop (pipeline Phase 1) ✓

- [x] `EvalMetrics` schema + normalization from mock eval
- [x] `thresholds.json` + drop detector CLI
- [x] Improvement run directory layout + manifest
- [x] Orchestrator calling `client.build_client("module", ...)`
- [x] Dry-run deploy (`deploy_manifest.json` only)
- [x] pytest + CI for fake drop → improvement run

**Exit:** Synthetic or real eval drop creates `{run_dir}/` with `current_eval.json`, `candidate_eval.json`, `decision.json`, and `deploy_manifest.json`.

**Next focus:** M2 (deployable coaching API).

### M2 — Deployable coaching API

- [ ] Dockerfile / process model for `serve`
- [ ] sqlite persistence (runs, idempotency, events)
- [ ] Async `POST /training/runs` + poll (`202` + status GET)
- [ ] AERL train adapter (HTTP contract from `_lib.sh`)
- [ ] AgentEvals eval adapter → `EvalMetrics`
- [ ] `/metrics`, structured logs, rate limits

**Exit:** Staging URL with `MOCK_SERVICE_TOKEN`; real train/eval behind env flags.

### M3 — Real improvement value

- [ ] Trajectory ingest + redaction metadata
- [ ] Curation script (train/dev/holdout)
- [ ] Skill path v1 (git-tagged bundle in manifest)
- [ ] Holdout gates + `promote` step
- [ ] Eval failure → auto `learn()` event

**Exit:** Real drop → curated data → skill or train → promote/reject on holdout.

### M4 — Safe production rollout

- [ ] Canary deploy + rollback pointer
- [ ] Human approval in orchestrator
- [ ] Live metric watch + auto-rollback
- [ ] Version registry query by `agent_id`

## EvalMetrics contract

Single JSON shape for auto-eval, drop detection, and promotion gates. Stored as JSONL under a metrics directory (default: `{coaching_root}/.self-coaching/metrics/eval_metrics.jsonl`).

See `services/orchestrator/eval_metrics.py` for the schema and `normalize_from_mock_eval()` for the mock mapping.

## What we are not building yet

- Hosted “remote agent API” (agents push trajectories; they are not served from this repo)
- LLM proxy as trajectory store
- A second 24/7 service that only collects evals (scheduling ≠ drop detection)
- Full MLOps platform
- Postgres / multi-node until sqlite is insufficient

## Related docs

- [Documentation index](../README.md)
- [`integration-plan.md`](integration-plan.md) — production agent + AgentEvals integration (phases, testing)
- [`pipeline.md`](../design/pipeline.md) — product architecture and phases
- [`progress.md`](progress.md) — component status vs milestones
- [`deploy-overview.md`](../guides/deploy-overview.md) — how to deploy T1 / T2 / T3
