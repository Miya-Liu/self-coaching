# Skill pack changelog

Version is tracked in [`SKILL_PACK_VERSION`](../SKILL_PACK_VERSION) at the repo root.

## 0.2.0

- External autoresearch: no vendored `upstream/autoresearch`; use `AUTORESEARCH_ROOT` (see `upstream/README.md`)
- T1 deploy path: `scripts/install-skill-pack.sh`, `docs/guides/deploy-skill-pack.md`
- `doctor.sh` skill-pack checks and `SKILL_PACK_VERSION`
- `run-once.sh` falls back to `python train.py` when `uv` is absent
- `preflight.sh` validates `AERL_ROOT` when set
- Mock services and HTTP client hardening (optional; not required for T1)

## 0.1.0

- Initial atomic skills layout and mock-services harness
