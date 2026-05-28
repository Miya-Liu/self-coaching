---
description: "A self-coaching skill set for autonomous agents: self-learning from experience, self-play data generation, evaluation pipelines, and SFT/RL training loops with executable governance."
---

This folder decomposes self-coaching into atomic skills. Load `self-coaching` for the orchestration overview, then load the specific step skill when executing a phase:

- `self-coaching-self-learning` — convert experience, corrections, bugs, eval failures, and tool issues into durable memory, skill patches, tests, eval cases, or project-local experience logs.
- `self-coaching-self-play` — generate, solve, critique, refine, and curate challenging task/trajectory records for eval, validation, SFT, or preference/RL datasets.
- `self-coaching-evaluation` — build, trigger, or interpret agent/model evaluation runners, failure routing, reports, and promotion gates.
- `self-coaching-training` — run curated data through SFT/GRPO-style pipeline helpers with lineage, logs, evaluation gates, and rollback.

Shared executable helpers live in `scripts/`:

- `init-experience.sh` creates `experience/`, `logs/`, and `worktrees/` in a target root.
- `hook-inject-errors.sh` and `hook-inject-learnings.sh` print bounded experience context.
- `hook-experiment.sh` prints the standard worktree/logging pattern.
- `preflight.sh` syncs an external autoresearch clone when `AUTORESEARCH_ROOT` is set.
- `run-once.sh` runs `uv run train.py` in an experiment worktree and redirects output to a log file.
- `run-pipeline.sh` runs named SFT/GRPO pipelines under `self-coaching-training/pipelines/`.
- `mock-run-all.sh` runs a deterministic local mock of the full learning → self-play → evaluation → training → evaluation loop.

Mock interfaces for testing live in `mock-services/`:

- CLI: `python mock-services/mock_self_coaching.py run-all --root <demo-root>`
- HTTP: `python mock-services/mock_self_coaching.py serve --root <demo-root> --port 8765`
- Python module: `mock-services/plugin_mock.py`
- Contract: `mock-services/contracts/mock_service_contract.json`

Do not put raw logs, credentials, or hidden private chain-of-thought into skills, memory, or curated records. Store logs in `logs/`, summarize reusable lessons in `experience/`, and promote only after evaluation.
