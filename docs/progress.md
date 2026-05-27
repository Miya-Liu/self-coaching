
### Mapped to the doc’s components

| `pipeline.md` component | Your status | How to integrate |
|-------------------------|-------------|------------------|
| **Production Agent** | Out of scope here (your *consumer* is “any agent” via `client.py`) | integrate via API services of remote agents |
| **Trajectory Store** | Not wired; mock uses local JSONL under `.self-coaching/` | integrate via API services of remote database or LLM API proxy to collect trajectories |
| **Auto-Evaluation Service** | Not the doc’s scheduled metrics JSON (`score`, `baseline_score`, …); you have **mock** `POST /eval/runs` + reports | integrate with AgentEvals project for agent evaluation via API services |
| **Drop Detector** | Not implemented | local 24*7 service which automaticlly collect agent evals results at stable frequency and can be utilised by external agents |
| **Improvement Orchestrator** | **Not implemented** (`examples/self_improving_pipeline/` referenced in the doc isn’t in the repo) | local module to deploy which showcase an example/mock pipeline of how agent do self-improvement |
| **Curation Agent** | **Skill + mock self-play** only; no production trajectory pull / PII / dedup pipeline | integrate remote self-play service via API to trigger data curation, whose background probably be an agent or not |
| **Skill learning path** | **SKILLs + `learn()`**; not hooked to `learn_skills` in `pipeline.yaml` | TBD and open for proposals |
| **Model training path** | **SKILLs + shell pipelines + mock `train()`**; real AERL/trainer is external | integrate with AERL via API services |
| **Candidate evaluation** | **Mock evaluate + promotion flag**; not holdout/regression/cost gates from the doc |  |
| **Version Management** | Not implemented | local module to tag or track which agent have been using this skill and log the version of it using either uuid or timestampe or other better proposal approaches |

