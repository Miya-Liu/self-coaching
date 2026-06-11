# Install as a Hermes Skill

This repo ships as a 5-skill pack (`self-coaching` umbrella +
`self-learning` / `self-play` / `self-evaluation` / `self-tuning`
submodules). Install into a Hermes Agent home so the agent can
load it with `skill_view`.

## Windows

Use **Git Bash** or **WSL** to run the installer —
`scripts/install-skill-pack.sh` is POSIX bash only; there is no
PowerShell installer. Paths resolve via `$HOME` (e.g.
`C:\Users\you\.hermes\skills\self-coaching`). After install, the
mock demo can be run from PowerShell via
`.\scripts\mock-self-coaching-demo.ps1` (demo wrapper only; not
used for skill install).

## Skills vs Python runtime

`pyproject.toml` installs the **mock/demo Python package** only — not
Hermes skills. Pick your path:

| You want to… | Run |
| --- | --- |
| Just use the skills in Hermes | `bash scripts/install-skill-pack.sh --hermes` |
| Also run the mock demo locally | `bash scripts/install-skill-pack.sh --hermes --with-mock` |
| Develop / modify the runtime | `pip install -e .` (from a repo clone) |

## One-command install (mock-ready)

```bash
bash scripts/install-skill-pack.sh ~/.hermes/skills --hermes --with-mock
```

This installs five Hermes-discoverable skills nested under
`~/.hermes/skills/self-coaching/` (submodules in
`self-coaching/self-learning/`, etc. — not flat siblings at
the skills root), runs `pip install -e .` for the Python
runtime, and bundles mock-service assets under
`~/.hermes/skills/self-coaching/assets/` (with neutralized
`name:` frontmatter so Hermes does not see duplicate skills).

## Verify

```bash
hermes skill list | grep self-coaching
# expect: self-coaching, self-learning, self-play,
#         self-evaluation, self-tuning

hermes skill view self-coaching | head -30
# expect: frontmatter with name, version 0.3.1, related_skills
```

## Validate end-to-end on mocks

From any directory (requires editable install from the repo clone):

```bash
python -m self_coaching.demo
```

Expected: exit 0, `completeness_report.json` with
`status: PASS`, all 18 matrix rows recorded.

## What you just installed

| Skill | Purpose |
| --- | --- |
| `self-coaching` | Umbrella policy + mock loop demo |
| `self-learning` | Experience → memory / skill patches |
| `self-play` | Generate / curate adversarial tasks |
| `self-evaluation` | Eval pipelines + promotion gates |
| `self-tuning` | SFT / GRPO / LoRA training pipelines |
