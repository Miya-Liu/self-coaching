# Install as a Hermes Skill

This repo ships as a 5-skill pack (`self-coaching` umbrella +
`self-learning` / `self-play` / `self-evaluation` / `self-tuning`
submodules). Install into a Hermes Agent home so the agent can
load it with `skill_view`.

## One-command install (mock-ready)

```bash
bash scripts/install-skill-pack.sh ~/.hermes/skills --hermes --with-mock
```

This installs five Hermes-discoverable skills (markdown +
metadata), runs `pip install -e .` for the Python runtime, and
bundles mock-service assets under
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
