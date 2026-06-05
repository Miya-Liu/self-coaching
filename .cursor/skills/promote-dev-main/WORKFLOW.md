# Dev → main workflow reference

[`main`](https://github.com/Miya-Liu/self-coaching/tree/main) stays lean for skill-pack users. Branch **`dev`** holds the full engineering tree.

All tooling lives in **`.cursor/skills/promote-dev-main/`** (not under `scripts/` — not part of self-coaching runtime).

| File | Role |
|------|------|
| `SKILL.md` | Cursor agent instructions |
| `promote-to-main.sh` | Copy allowlisted paths dev → main |
| `promote-allowlist.txt` | What ships to `main` |
| `promote-denylist.txt` | What is stripped from `main` |
| `gitignore.dev` | Template for `dev` (tests tracked) |
| `gitignore.main` | Applied on `main` during promote |

## Daily workflow

```bash
git checkout dev
# edit, commit, push
git push origin dev

git checkout main
bash .cursor/skills/promote-dev-main/promote-to-main.sh
bash .cursor/skills/promote-dev-main/promote-to-main.sh --push
git checkout dev
```

**Do not** merge a GitHub PR `dev` → `main`. Use `promote-to-main.sh` only.

## Dev-only (never on `main`)

- `.cursor/`
- `tests/`
- `docs/integration/`
- `docs/project/integration-plan.md`, `docs/project/progress.md`

## `.gitignore` on `dev`

```bash
cp .cursor/skills/promote-dev-main/gitignore.dev .gitignore
```

## Cursor

In chat: `@promote-dev-main commit and push to dev, then promote to main`
