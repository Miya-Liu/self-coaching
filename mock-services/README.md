# Mock Self-Coaching Services

This folder contains local mock interfaces for testing the full self-coaching loop without a real LLM, trainer, evaluator, or external API.

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
    cases/self_play_candidates.jsonl
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
python mock_self_coaching.py self-play --root <root> --capability tool_use --n 4
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
- `POST /self-play/generate` with `{"capability":"tool_use","n":4}`
- `POST /eval/runs` with `{"candidate":"mock-candidate-v1","baseline":"mock-baseline-v0"}`
- `GET /eval/runs/{run_id}/report`
- `POST /training/runs` with `{"pipeline":"sft"}`
- `POST /pipeline/run-all` with `{"capability":"tool_use","pipeline":"sft"}`

## Design Notes

- Deterministic and stdlib-only.
- No real credentials, model calls, or training jobs.
- Produces the same artifact shapes expected by the self-coaching skills.
- Stores observable traces and summaries, not hidden private chain-of-thought.
- Intended for local pipeline validation and skill demos only.
