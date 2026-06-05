---
name: promote-dev-main
description: >-
  Commits and pushes changes on branch dev, then promotes allowlisted paths to
  main via .cursor/skills/promote-dev-main/promote-to-main.sh for the
  self-coaching two-branch layout. Use when the user asks to commit, push,
  publish, release, sync main, promote to main, or ship updates from dev to the
  public branch.
---

# Dev → main commit and promote

Single public repo, two branches. **`dev`** = full tree; **`main`** = lean public face.

| Branch | Contents |
|--------|----------|
| `dev` | Everything: `tests/`, `docs/integration/`, `integration-plan.md`, `progress.md`, `.cursor/skills/` |
| `main` | Allowlisted paths only (see `promote-allowlist.txt` in this folder) |

**Do not** open or merge a GitHub PR `dev` → `main`. Promotion is **selective checkout**, not a branch merge.

Extended reference: [WORKFLOW.md](WORKFLOW.md).

## Skill folder layout

```
.cursor/skills/promote-dev-main/
├── SKILL.md                 # this file
├── WORKFLOW.md              # human-readable workflow
├── promote-to-main.sh       # promote script
├── promote-allowlist.txt
├── promote-denylist.txt
├── gitignore.dev            # dev branch template
└── gitignore.main           # applied on main during promote
```

---

## Before starting

1. Confirm the user **explicitly asked** to commit and/or push (never commit unprompted).
2. Run promote script in **Git Bash** on Windows (not PowerShell).
3. Use `curl.exe` in PowerShell; use `bash .cursor/skills/...` for promote.

Checklist:

```
- [ ] On branch dev (for dev commit)
- [ ] git status reviewed
- [ ] No secrets staged (.env, tokens, credentials)
- [ ] User approved commit message
```

---

## Phase 1 — Commit and push `dev`

```bash
git checkout dev
git status
git diff
git log -3 --oneline
```

**Stage by intent:**

| Change type | Action |
|-------------|--------|
| Code, tests, integration docs | `git add` on **dev** |
| Dev-only | `tests/`, `docs/integration/`, `docs/project/integration-plan.md`, `docs/project/progress.md` |
| Public surface | Will promote via `promote-allowlist.txt` |

```bash
git commit -m "Subject line." -m "Optional body."
git push origin dev
```

If `origin/dev` was deleted: `git push -u origin dev`.

**`.gitignore` on dev:** `cp .cursor/skills/promote-dev-main/gitignore.dev .gitignore`

---

## Phase 2 — Promote to `main`

Always **dry-run first**:

```bash
git checkout main
git pull origin main
bash .cursor/skills/promote-dev-main/promote-to-main.sh
```

Review staged diff. Expected:

- **Updated** paths from `promote-allowlist.txt`
- **Removed** paths from `promote-denylist.txt` (deletions are normal)
- **`.gitignore`** replaced from `gitignore.main`

If diff looks wrong, stop. Edit allowlist/denylist in this folder on **dev**, commit, push, retry.

```bash
bash .cursor/skills/promote-dev-main/promote-to-main.sh --push
git checkout dev
```

---

## What never lands on `main`

- `.cursor/` (this skill folder)
- `tests/`
- `docs/integration/`
- `docs/project/integration-plan.md`, `docs/project/progress.md`

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| GitHub “Can’t automatically merge” dev→main PR | Ignore; use `promote-to-main.sh`, not PR merge |
| `dev` branch missing on origin | `git push -u origin dev` |
| Promote deleted files from `main` | Expected denylist behavior |
| `export-integration-snapshots.sh` Python error | Run in Git Bash (`cygpath` fix in script) |
| PowerShell `curl -s` fails | Use `curl.exe` |

---

## Example (user: “commit and push to dev and main”)

1. `git checkout dev` → stage → commit → `git push origin dev`
2. `git checkout main` → `bash .cursor/skills/promote-dev-main/promote-to-main.sh` → review
3. `bash .cursor/skills/promote-dev-main/promote-to-main.sh --push`
4. `git checkout dev`

Report: dev commit SHA, promote commit SHA, and that `main` was pushed.
