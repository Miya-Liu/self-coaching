---
description: "A self-coaching skill set for autonomous agents: self-learning from experience, self-play data generation, evaluation pipelines, and SFT/RL training loops with governance."
---

This folder decomposes self-coaching into atomic skills. Load `self-coaching` for the orchestration overview, then load the specific step skill when executing a phase:

- `self-coaching-self-learning` — convert experience, corrections, and bug fixes into durable memory, skills, tests, or eval cases.
- `self-coaching-self-play` — generate and curate challenging self-play tasks and trajectories.
- `self-coaching-evaluation` — build or trigger agent/model evaluation services and promotion gates.
- `self-coaching-training` — route curated data into SFT or preference/RL training with lineage and rollback.
