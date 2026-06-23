# Skill pack changelog

Version is tracked in [`modes/self-coaching/SKILL_PACK_VERSION`](../../modes/self-coaching/SKILL_PACK_VERSION).

## Unreleased (docs)

- Canonical naming: repo **self-coaching**; modes **self-coaching** / **coach**; submodules **self-learning**, **self-questioning**, **self-evaluation**, **self-tuning**
- Coach mode design: per-agent coaching roots, supervision registry, optional LLM proxy (M5)

## 0.2.0

- AERL pipelines via `run-pipeline.sh`; mock loop via `python -m self_coaching.demo`
- T1 deploy path: `scripts/install-skill-pack.sh`, `docs/guides/deploy-skill-pack.md`
- `doctor.sh` skill-pack checks and `SKILL_PACK_VERSION`
- `preflight.sh` validates `.env` / `AERL_ROOT` when set
- Mock services and HTTP client hardening (optional; not required for T1)

## 0.1.0

- Initial atomic skills layout and mock-services harness
