# Hook setup (self-coaching)

Use **command** hooks that print short, bounded text. Training output must always go to `logs/*.log` files, never into the hook’s stdout at full volume.

Paths below assume the skill is installed at `.cursor/skills/self-coaching/`. If your path differs, adjust the `command` string.

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

**Suggested event:** e.g. start of a coding/agent step where experiments are allowed, or a dedicated `UserPromptSubmit` matcher (e.g. `self-coach` / `experiment`).

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "(?i)self-?coach|experiment|train",
      "hooks": [{
        "type": "command",
        "command": "bash .cursor/skills/self-coaching/scripts/hook-experiment.sh"
      }]
    }]
  }
}
```

## 2) Learnings context hook (stagnation / no improvement)

When the loop shows no clear metric improvement, run this to inject the **tail** of `experience/LEARNINGS.md` (optimization insights).

**Suggested event:** a second `UserPromptSubmit` matcher (e.g. `stuck`, `stagnat`, `flat`, `no improve`) or a manual “review learnings” pattern.

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "(?i)stuck|stagnat|no improve|review learnings",
      "hooks": [{
        "type": "command",
        "command": "bash .cursor/skills/self-coaching/scripts/hook-inject-learnings.sh"
      }]
    }]
  }
}
```

## 3) Error context hook (similar errors)

Injects the **tail** of `experience/ERROR.md` so repeated failures are visible without rereading full logs.

**Suggested event:** matcher for `error`, `oom`, `crash`, `failed`, or after tool failures.

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "(?i)error|oom|crash|failed run",
      "hooks": [{
        "type": "command",
        "command": "bash .cursor/skills/self-coaching/scripts/hook-inject-errors.sh"
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
        "command": "bash .cursor/skills/self-coaching/scripts/activator.sh"
      }]
    }]
  }
}
```

## Combining

Merge all desired `UserPromptSubmit` array entries in your project’s hook file. Matchers are evaluated in order; avoid duplicate blank matchers unless intentional.

**Note:** `hook-inject-*.sh` use `tail` to limit lines. Do not point hooks at `logs/*.log` in full; always cap size.
