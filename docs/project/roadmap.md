# Self-coaching deployment roadmap

Execution plan from **skill demo + Coaching API mock** to a **deployable evolution platform**. Design: [`architecture.md`](../design/architecture.md), [`pipelines.md`](../design/pipelines.md).

## Deployment modes

| Mode | Executor | Subject | Primary deploy |
|------|----------|---------|----------------|
| **Self-coaching mode** | Host agent | Host agent | **T1** |
| **Coach mode** | Coach service / scheduler | External agents | **T2 + T3** |

Both modes share the **evolution engine**, pipeline stages, and adapters. See [architecture.md](../design/architecture.md).

## Deploy targets (artifacts)

We ship three deploy targets in order. Each has a clear audience and exit criterion.

| Target | What gets deployed | Mode | Status |
|--------|-------------------|------|--------|
| **T1 — Self-coaching pack** | Markdown skills + `scripts/` + `experience/` layout | Self-coaching | **Active — ship now** |
| **T2 — Coaching API** | `mock_self_coaching.py serve` → real eval/train adapters | Coach (+ self-coaching optional) | **Deferred**; mock ready |
| **T3 — Evolution engine** | `services/orchestrator/` + metrics + drop detector | Coach (+ self-coaching optional) | **Built (M1)** |

**Primary focus:** **T1 / M0** — Self-coaching mode install. See [`deploy-skill-pack.md`](../guides/deploy-skill-pack.md).

```text
[T1 self-coaching pack]      Self-coaching mode — host reads modes/self-coaching/SKILL.md
[T2 Coaching API]    HTTP/CLI/module — contract spine (OpenAPI)
[T3 evolution engine] record-eval → check-drop → run → gate → deploy
                              │
                              └─ calls T2 via ModuleClient or HTTPClient
```

## Architecture spine

One evolution engine, one `SelfCoachingClient`, many adapters.

| Layer | Repo path | Role |
|-------|-----------|------|
| Policy | `modes/self-coaching/SKILL.md` + submodules | How an executor agent should behave |
| Contract | `mock-services/contracts/openapi.yaml` | T2 HTTP: learn / self-play / eval / train |
| Client | `mock-services/client.py` | Module, CLI, HTTP transports |
| Evolution engine | `services/orchestrator/` | T3: [pipelines.md](../design/pipelines.md) loop |
| Adapters | `services/adapters/` | AgentEvals, production agent API, AERL |
| Coach shell | `modes/coach/` | Supervision registry, optional LLM proxy (M5) |

## Milestones

### M0 — Baseline (skill pack deployable) ✓

- [x] CI: doctor, shellcheck, pytest, mock smoke `run-all`
- [x] `scripts/install-skill-pack.sh` + `docs/guides/deploy-skill-pack.md`
- [x] `modes/self-coaching/SKILL_PACK_VERSION` + `project/changelog-skills.md`
- [x] Shell strictness on shipped scripts; `run-once.sh` python fallback
- [x] `preflight.sh` AERL_ROOT sanity; registry documents `TRAINER_BASE_URL`
- [x] `docs/guides/deploy-overview.md` — T1 as active target
- [x] Git tag `v0.2.0-skills` on release

**Exit:** `bash scripts/install-skill-pack.sh . --with-mock` succeeds on a clean machine with bash + python.

**Next focus:** M2 + integration Phase 0–1 (see [`integration-plan.md`](integration-plan.md)).

### M1 — Evolution engine + dry loop (pipeline Phase 1) ✓

- [x] `EvalMetrics` schema + normalization from mock eval
- [x] `thresholds.json` + drop detector CLI
- [x] Improvement run directory layout + manifest
- [x] Evolution engine calling `client.build_client("module", ...)`
- [x] Dry-run deploy (`deploy_manifest.json` only)
- [x] pytest + CI for fake drop → improvement run

**Exit:** Synthetic or real eval drop creates `{run_dir}/` with `current_eval.json`, `candidate_eval.json`, `decision.json`, and `deploy_manifest.json`.

**Next focus:** M2 (deployable Coaching API) + Coach mode adapters.

### M2 — Deployable Coaching API

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
- [ ] Human approval in evolution engine
- [ ] Live metric watch + auto-rollback
- [ ] Version registry query by `agent_id`

**Exit:** Staging subject agent promoted and rolled back via production agent API.

### M5 — Coach mode shell

- [ ] Supervision registry (`modes/coach/agents.yaml` schema + loader)
- [ ] Per-agent coaching root convention documented and validated
- [ ] Scheduler examples (cron/systemd) for multi-agent `record-eval` / `check-drop` / `run`
- [ ] Optional LLM proxy spike (trajectory capture only; eval remains AgentEvals)

**Exit:** Two or more external agents supervised from one coach deployment with isolated coaching roots.

## EvalMetrics contract

Single JSON shape for auto-eval, drop detection, and promotion gates. Stored as JSONL under `{coaching_root}/.self-coaching/metrics/eval_metrics.jsonl`.

See `services/orchestrator/eval_metrics.py` for the schema and `normalize_from_mock_eval()` for the mock mapping.

## What we are not building yet

- Hosted “remote agent API” (subject agents push trajectories; they are not served from this repo)
- A second 24/7 service that only collects evals (scheduling ≠ drop detection)
- Full MLOps platform
- Postgres / multi-node until sqlite is insufficient
- LLM proxy as a **replacement** for AgentEvals (proxy is observation-only; see M5)

## Related docs

- [design/README.md](../design/README.md) — design index
- [self_coaching_mode.md](../design/self_coaching_mode.md) · [coach_mode.md](../design/coach_mode.md)
- [integration-plan.md](integration-plan.md) — adapter implementation
- [pipelines.md](../design/pipelines.md) — evolution engine
- [progress.md](progress.md) — component status
- [deploy-overview.md](../guides/deploy-overview.md) — T1 / T2 / T3 how-to
