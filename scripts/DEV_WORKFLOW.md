# Private dev repo workflow

Public [`self-coaching`](https://github.com/Miya-Liu/self-coaching) stays lean for skill-pack users and integrators. Full engineering artifacts live in a **private** companion repo.

## Repositories

| Remote | Repo | Branch | Contents |
|--------|------|--------|----------|
| `origin` | `Miya-Liu/self-coaching` (public) | `main` | Allowlisted paths only — skills, mock spine, orchestrator, public guides |
| `private` | `Miya-Liu/self-coaching-dev` (private) | `main` | Full tree from local `dev` — `tests/`, `docs/integration/`, OpenAPI snapshots, `integration-plan.md`, `progress.md` |

**GitHub does not support private branches on a public repo.** Use two repositories.

## One-time setup

1. Create **private** repo `self-coaching-dev` on GitHub (empty, no README).
2. From this clone:

```bash
export PRIVATE_REMOTE_URL=git@github.com:Miya-Liu/self-coaching-dev.git
bash scripts/setup-dev-remote.sh
```

## Daily workflow

```bash
# Work on dev branch
git checkout dev
# ... edit code, docs, tests ...
git add -A
git commit -m "your message"
git push private dev:main

# Promote production paths to public (dry-run first)
bash scripts/promote-to-public.sh
bash scripts/promote-to-public.sh --push
```

Edit allowlist / denylist when the public surface changes:

- `scripts/promote-allowlist.txt` — paths copied to public `main`
- `scripts/promote-denylist.txt` — paths removed from public `main` on each promote

## What stays private only

- `tests/` and `tests/fixtures/`
- `docs/integration/` (OpenAPI snapshots, `mapping.md`)
- `docs/project/integration-plan.md`, `docs/project/progress.md`
- `scripts/DEV_WORKFLOW.md` (this file — not on allowlist)

## Clone for a new machine

```bash
git clone git@github.com:Miya-Liu/self-coaching-dev.git
cd self-coaching-dev
git remote add public git@github.com:Miya-Liu/self-coaching.git
git fetch public
```

Optional second clone of public `self-coaching` for skill-pack-only work.
