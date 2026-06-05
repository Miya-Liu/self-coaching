---
description: "Installable self-coaching skill: umbrella policy plus submodules self-learning, self-play, self-evaluation, self-tuning for host agent self-evolution."
---

# self-coaching (skill pack)

A **portable skill** for coaching a host agent through a gated loop: observe experience, improve via **self-learning** and **self-play**, measure with **self-evaluation**, optionally **self-tuning**, record **Experience**, and merge only after human approval.

Load **`SKILL.md`** (`name: self-coaching`) for the full orchestration policy, then load one **submodule** when executing a single phase:

| Submodule | Folder | Role |
|-----------|--------|------|
| **self-learning** | `self-learning/` | Experience → memory, skill patches, eval cases, experience logs |
| **self-play** | `self-play/` | Generate and curate tasks and trajectories |
| **self-evaluation** | `self-evaluation/` | Eval runners, failure routing, reports, promotion gates |
| **self-tuning** | `self-tuning/` | SFT/GRPO pipeline discipline, manifests, rollback |

**self-tuning** includes `pipelines/` (AERL SFT/GRPO) and `services/example.env` (copy to `.env` locally; never commit secrets).

Optional host wiring: `adapters/` (how to install this pack into your agent runtime).

Do not put raw train logs, credentials, or hidden chain-of-thought into skills or curated records. Full training output → `logs/`; reusable lessons → `experience/`; promote only after **self-evaluation**.
