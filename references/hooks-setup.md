# Hook setup (self-coaching)

Hooks are **optional** reminders and context injectors. They are **not** part of the core `SKILL.md` contract; your host (IDE, extension, or custom runner) may use different event names or no hooks at all.

Use **command** hooks that print short, bounded text. Training output must always go to `logs/*.log` files, never into the hook’s stdout at full volume.

## `SKILL_ROOT`

Replace `SKILL_ROOT` in the examples below with the **absolute path** to this skill folder on your machine, e.g.:

- `C:\Users\you\work\self-coaching`
- `/home/you/skills/self-coaching`

JSON examples use `bash "$SKILL_ROOT/scripts/..."` style when your runner expands env vars; if not, use a full literal path in `command`.

## Environment variables (optional)

| Variable | Used by | Meaning |
|----------|---------|---------|
| `EXPERIMENT_ID` | `hook-experiment.sh` | Suffix for default worktree and log (default `run-01`) |
| `EXPERIMENT_WORKTREE` | `hook-experiment.sh` | Full path to experiment worktree |
| `EXPERIMENT_LOG_FILE` | `hook-experiment.sh` | Full path to training log file |
| `LEARNINGS_TAIL_LINES` | `hook-inject-learnings.sh` | Default `100` |
| `ERROR_TAIL_LINES` | `hook-inject-errors.sh` | Default `100` |
| `SKILL_LEARNINGS_FILE` / `SKILL_ERROR_FILE` | inject hooks | Override paths to the markdown log files |

## 1) Experiment command hook

Injects the **bash** pattern to run `uv run train.py` inside the worktree with full redirect to a log file.

**Note:** The JSON field name `UserPromptSubmit` and `hooks` shape are **examples** (similar to some IDEs). Map to your product’s “before prompt” or “session start” hook if the names differ.

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "(?i)self-?coach|experiment|train",
      "hooks": [{
        "type": "command",
        "command": "bash $SKILL_ROOT/scripts/hook-experiment.sh"
      }]
    }]
  }
}
```

## 2) Learnings context hook (stagnation / no improvement)

When the loop shows no clear metric improvement, run this to inject the **tail** of `experience/LEARNINGS.md` (optimization insights).

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "(?i)stuck|stagnat|no improve|review learnings",
      "hooks": [{
        "type": "command",
        "command": "bash $SKILL_ROOT/scripts/hook-inject-learnings.sh"
      }]
    }]
  }
}
```

## 3) Error context hook (similar errors)

Injects the **tail** of `experience/ERROR.md` so repeated failures are visible without rereading full logs.

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "(?i)error|oom|crash|failed run",
      "hooks": [{
        "type": "command",
        "command": "bash $SKILL_ROOT/scripts/hook-inject-errors.sh"
      }]
    }]
  }
}
```

## 4) Global activator (optional)

Reminder only; no large output.

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "bash $SKILL_ROOT/scripts/activator.sh"
      }]
    }]
  }
}
```

## Combining

Merge all desired `UserPromptSubmit` array entries in your project’s hook file if your product supports that structure. Matchers are evaluated in order; avoid duplicate blank matchers unless intentional.

**Note:** `hook-inject-*.sh` use `tail` to limit lines. Do not point hooks at `logs/*.log` in full; always cap size.

**Cursor and similar hosts:** if your config requires a path like `.cursor/skills/self-coaching/`, set `SKILL_ROOT` to the resolved absolute path, or use that path directly in `command` instead of `$SKILL_ROOT`.
