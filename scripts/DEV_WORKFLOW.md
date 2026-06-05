# Dev branch workflow (single public repo)

[`main`](https://github.com/Miya-Liu/self-coaching/tree/main) stays lean for skill-pack users and integrators. Branch **`dev`** holds the full engineering tree (tests, integration docs, OpenAPI snapshots).

**Note:** `dev` is still public on GitHub — it is a separate branch, not a private fork.

## Branches

| Branch | Audience | Contents |
|--------|----------|----------|
| `main` | Public default | Allowlisted paths only — skills, mock spine, orchestrator, public guides |
| `dev` | Developers | Full tree — `tests/`, `docs/integration/`, `integration-plan.md`, `progress.md` |

## Daily workflow

```bash
# Develop on dev
git checkout dev
# ... edit code, docs, tests ...
git add -A
git commit -m "your message"
git push origin dev

# Promote production paths to main (dry-run first)
git checkout main
bash scripts/promote-to-main.sh
bash scripts/promote-to-main.sh --push
```

Edit promotion rules when the public surface changes:

- `scripts/promote-allowlist.txt` — paths copied from `dev` → `main`
- `scripts/promote-denylist.txt` — paths removed from `main` on each promote

## What stays on `dev` only

- `tests/` and `tests/fixtures/`
- `docs/integration/` (OpenAPI snapshots, `mapping.md`)
- `docs/project/integration-plan.md`, `docs/project/progress.md`
- This file (`scripts/DEV_WORKFLOW.md`)

## `.gitignore` on `dev`

`dev` does not ignore `tests/`. After `git checkout dev`, use `scripts/gitignore.dev` as a reference if you need to restore the dev variant of `.gitignore`.

## Clone

```bash
git clone https://github.com/Miya-Liu/self-coaching.git
cd self-coaching
git checkout dev   # full developer tree
```
