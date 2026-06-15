# self-coaching

Portable, agent-agnostic evolution platform: a **skill pack** (`modes/self-coaching/`) plus an optional **mock runtime** for end-to-end validation. The contract is **`modes/self-coaching/SKILL.md`** and on-disk **Experience** — not tied to one IDE.

| Mode | Who evolves | Deploy |
|------|-------------|--------|
| **self-coaching** | Host agent | **T1** skill pack |
| **coach** | Coach service supervises external agents | **T2** API + **T3** engine |

Submodules: **self-learning**, **self-play**, **self-evaluation**, **self-tuning**. Full docs: [`docs/README.md`](docs/README.md).

## Quick install

```bash
git clone https://github.com/Miya-Liu/self-coaching.git && cd self-coaching
bash scripts/install-skill-pack.sh --hermes              # Hermes skills + mock harness
bash scripts/install-skill-pack.sh --hermes --with-mock  # + pip install -e . for python -m self_coaching.demo
```

Repo clone (no Hermes): `bash scripts/install-skill-pack.sh . --with-mock`

**Windows:** Git Bash or WSL for install scripts; mock demo from PowerShell: `python scripts/mock_self_coaching_demo.py`

Upgrade Hermes skills after `git pull`: `bash scripts/update-skill-pack.sh --hermes`. Details: [`docs/guides/deploy-skill-pack.md`](docs/guides/deploy-skill-pack.md).

## Workflow

```mermaid
sequenceDiagram
    autonumber
    participant U as Human
    participant A as Agent
    participant G as Loading Gate
    participant B as Performance
    participant C as Data Pool
    participant M as Local Model
    participant D as Deploy Gate
    participant T as Trainer
    participant X as Results

    U->>A: Enable self-coaching
    A->>G: Ensure Opening Gate
    G->>B: Review performance
    B->>G: Needs improvement
    G->>C: Load training data
    C->>M: Load model checkpoint
    G->>A: Experiment Ready
    A->>D: Create experiment + worktree
    loop Experiment iterations
        A->>T: Edit in worktree; run train
        T->>A: Results / errors
    end
    A->>U: Request authorization
    alt Approve
        A->>M: Replace local model
        A->>C: Update data
    end
```

Gate → implementation mapping: [architecture.md](docs/design/architecture.md#conceptual-mapping). Experiment iterations run inside the **Deploy Gate**; merge to `main` or weight swap requires **human approval**.

## Try the mock loop

```bash
bash scripts/mock-self-coaching-demo.sh          # Linux / Git Bash
python scripts/mock_self_coaching_demo.py        # Windows / cross-platform
```

Expected: `completeness: PASS` (C01–C18 audit). More: [runbook](docs/guides/runbook.md#mock-loop-demo).

## Repo layout (essentials)

| Path | Role |
|------|------|
| `modes/self-coaching/` | T1 skill pack (5 skills) |
| `modes/coach/` | Coach mode shell |
| `mock-services/` | Mock Coaching API (T2) |
| `services/orchestrator/` | Evolution engine (T3) |
| `scripts/` | Install, doctor, demos |
| `docs/` | [Documentation index](docs/README.md) |

Default trainer path: AERL HTTP pipelines (`scripts/run-pipeline.sh`) or mock loop (`python -m self_coaching.demo`).

## Scope

Training may run autonomously inside a worktree; **merge** and **production promotion** always need explicit user approval.
