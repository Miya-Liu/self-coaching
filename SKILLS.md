# Skills index

This repository is a **skill pack** plus its mock runtime and evolution framework. Repo-root folders like `services/`, `mock-services/`, `tools/`, and `tests/` support the demo and trainer loop — they are not Hermes skills themselves. The five discoverable skills live under `modes/self-coaching/`.

Use `bash scripts/install-skill-pack.sh --hermes` to copy skills and the **mock-services harness** into `~/.hermes/skills/self-coaching/`. Add `--with-mock` for `pip install -e .` so `python -m self_coaching.demo` works from your repo clone.

| You want to… | Run |
| --- | --- |
| Just use the skills in Hermes | `bash scripts/install-skill-pack.sh --hermes` |
| Run mock CLI from Hermes install | `cd ~/.hermes/skills/self-coaching && python mock-services/mock_self_coaching.py --help` |
| Run `python -m self_coaching.demo` | `bash scripts/install-skill-pack.sh --hermes --with-mock` (from repo clone) |
| Update Hermes skills after `git pull` | `bash scripts/update-skill-pack.sh --hermes` |
| Update repo clone / Cursor / pack copy | See [deploy-skill-pack.md#upgrade](docs/guides/deploy-skill-pack.md#upgrade) |
| Develop / modify the runtime | `pip install -e .` |

`pip install` does **not** copy skills into `~/.hermes/skills/` — use the bash installer for that.

**Windows:** Git Bash or WSL for install (`install-skill-pack.sh` is bash-only). PowerShell: `.\scripts\mock-self-coaching-demo.ps1` runs the demo only.

**Installed layout (Hermes):**

```
~/.hermes/skills/self-coaching/
  SKILL.md              # umbrella
  mock-services/        # stdlib mock harness (always installed with --hermes)
  scenarios/
  tools/
  self-learning/
  self-play/
  self-evaluation/
  self-tuning/
  assets/               # Python loop runtime (not Hermes-discoverable)
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
