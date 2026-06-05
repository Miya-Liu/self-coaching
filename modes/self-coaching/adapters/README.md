# Self-coaching mode — host adapters

Install **`modes/self-coaching/`** into external agent runtimes. Each adapter documents paths, hooks, and `SKILL_ROOT` for that host.

| Adapter | Host |
|---------|------|
| `hermes.py` | Hermes |
| `openclaw.py` | OpenClaw |

Example config: `configs/self-coaching.example.yaml` at repo root.

Design: [docs/design/self_coaching_mode.md](../../docs/design/self_coaching_mode.md).
