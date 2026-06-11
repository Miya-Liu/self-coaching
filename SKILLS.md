# Skills index

This repository is a **skill pack** plus its mock runtime and evolution framework. Repo-root folders like `services/`, `mock-services/`, `tools/`, and `tests/` support the demo and trainer loop — they are not Hermes skills themselves. The five discoverable skills live under `modes/self-coaching/`.

Use `bash scripts/install-skill-pack.sh --hermes` to copy them into `~/.hermes/skills/self-coaching/` (sub-skills nested inside the umbrella directory). Add `--with-mock` for the runnable demo assets and Python runtime.

| You want to… | Run |
| --- | --- |
| Just use the skills in Hermes | `bash scripts/install-skill-pack.sh --hermes` |
| Also run the mock demo locally | `bash scripts/install-skill-pack.sh --hermes --with-mock` |
| Update Hermes skills after `git pull` | `bash scripts/update-skill-pack.sh --hermes` |
| Update repo clone / Cursor / pack copy | See [deploy-skill-pack.md#upgrade](docs/guides/deploy-skill-pack.md#upgrade) |
| Develop / modify the runtime | `pip install -e .` |

`pip install` does **not** copy skills into `~/.hermes/skills/` — use the bash installer for that.

**Windows:** Git Bash or WSL for install (`install-skill-pack.sh` is bash-only). PowerShell: `.\scripts\mock-self-coaching-demo.ps1` runs the demo only.

**Installed layout (Hermes):**

```
~/.hermes/skills/self-coaching/
  SKILL.md              # umbrella
  self-learning/
  self-play/
  self-evaluation/
  self-tuning/
  assets/               # only with --with-mock
```

| Skill | Source path | Role |
|-------|-------------|------|
| **self-coaching** | `modes/self-coaching/SKILL.md` | Umbrella orchestration policy |
| **self-learning** | `modes/self-coaching/self-learning/SKILL.md` | Experience → memory, skill patches, eval cases |
| **self-play** | `modes/self-coaching/self-play/SKILL.md` | Generate and curate tasks and trajectories |
| **self-evaluation** | `modes/self-coaching/self-evaluation/SKILL.md` | Eval runners, failure routing, promotion gates |
| **self-tuning** | `modes/self-coaching/self-tuning/SKILL.md` | SFT/GRPO pipeline discipline, manifests, rollback |

**Install:** [README § Install (Hermes Agent users)](README.md#install-hermes-agent-users) · [`docs/guides/install-as-hermes-skill.md`](docs/guides/install-as-hermes-skill.md)

**Verify after install:**

```bash
hermes skill list | grep -E '^(self-coaching|self-learning|self-play|self-evaluation|self-tuning)$'
```
