# Skill pack changelog

Version is tracked in [`modes/skill/SKILL_PACK_VERSION`](../../modes/skill/SKILL_PACK_VERSION).

## Unreleased (docs)

- Canonical naming: repo **self-coaching**; modes **skill** / **coach**; submodules **self-learning**, **self-play**, **self-evaluation**, **self-tuning**
- Coach mode design: per-agent coaching roots, supervision registry, optional LLM proxy (M5)

## 0.2.0

- External autoresearch: no vendored `upstream/autoresearch`; use `AUTORESEARCH_ROOT` (see `upstream/README.md`)
- T1 deploy path: `scripts/install-skill-pack.sh`, `docs/guides/deploy-skill-pack.md`
- `doctor.sh` skill-pack checks and `SKILL_PACK_VERSION`
- `run-once.sh` falls back to `python train.py` when `uv` is absent
- `preflight.sh` validates `AERL_ROOT` when set
- Mock services and HTTP client hardening (optional; not required for T1)

## 0.1.0

- Initial atomic skills layout and mock-services harness
