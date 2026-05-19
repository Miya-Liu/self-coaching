# Self-Coaching Mock Services Production-Readiness Report

Status: FAIL

Scope: pipeline and integration readiness using deterministic mock services; not a claim that real training/eval infra is production-ready.

Run root: `C:\Users\liumy26\.hermes\skills\self-coaching\mock-services\production-readiness-runs\agent-skill-simulation`
JSON report: `C:\Users\liumy26\.hermes\skills\self-coaching\mock-services\production-readiness-runs\production_readiness_report.json`

## Check Summary

- PASS [required] python_compile_mock_and_plugin: 
- PASS [required] import_mock_module: 
- PASS [required] contract_cli_command_init: 
- PASS [required] contract_cli_command_learn: 
- PASS [required] contract_cli_command_self-play: 
- PASS [required] contract_cli_command_evaluate: 
- PASS [required] contract_cli_command_train: 
- PASS [required] contract_cli_command_run-all: 
- PASS [required] contract_cli_command_serve: 
- PASS [required] contract_http_endpoint_/health: 
- PASS [required] contract_http_endpoint_/learning/events: 
- PASS [required] contract_http_endpoint_/self-play/generate: 
- PASS [required] contract_http_endpoint_/eval/runs: 
- PASS [required] contract_http_endpoint_/eval/runs/{run_id}/report: 
- PASS [required] contract_http_endpoint_/training/runs: 
- PASS [required] contract_http_endpoint_/pipeline/run-all: 
- PASS [required] phase_learning_init_workspace: {'status': 'initialized', 'root': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation', 'manifest': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation\\.self-coaching\
- PASS [required] phase_learning_event_written: {'id': 'learn-584985e4fa', 'timestamp': '2026-05-19T01:43:15Z', 'source': 'agent-skill-simulation', 'capability': ['tool_use'], 'event': 'Production-readiness simulation: verify side effects before claiming success', 'classification': 'eval_case_candidate', 'privacy_checked': True, 'durable_artifact
- PASS [required] phase_self_play_generated_cases: {'status': 'generated', 'count': 5, 'case_ids': ['case-7532f0dd8f', 'case-1fa600d29e', 'case-7d1a1150c8', 'case-393d11f7c0', 'case-f01d15e341']}
- PASS [required] phase_evaluation_baseline_passes: {'status': 'passed', 'run_id': 'eval-e504d7d2ff', 'report': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation\\.self-coaching\\reports\\eval_runs\\eval-e504d7d2ff\\report.json', 'recommendation': 'promote'}
- PASS [required] negative_gate_bad_candidate_blocked: {'status': 'failed', 'run_id': 'eval-bc415f8496', 'report': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation\\.self-coaching\\reports\\eval_runs\\eval-bc415f8496\\report.json', 'recommendation': 'do_not_promote'}
- PASS [required] phase_training_manifest_written: {'status': 'trained', 'run_id': 'train-69e84d599e', 'candidate': 'mock-sft-candidate-4d599e', 'manifest': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation\\.self-coaching\\manifests\\training_run_manifest.json', 'log_file': 'C:\\Us
- PASS [required] phase_candidate_eval_passes: {'status': 'passed', 'run_id': 'eval-740abf95fc', 'report': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation\\.self-coaching\\reports\\eval_runs\\eval-740abf95fc\\report.json', 'recommendation': 'promote'}
- PASS [required] phase_run_all_grpo_promotable: {'status': 'ok', 'root': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation\\run-all-subroot', 'init': {'status': 'initialized', 'root': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\a
- FAIL [required] artifact_contract_required_paths: missing: [
  "C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation\\.self-coaching\\curated\\validation.jsonl",
  "C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation\\.se
- PASS [required] case_records_have_rubric_and_privacy: cases=5
- PASS [required] eval_train_split_no_exact_id_overlap: eval=3 train=2
- PASS [required] training_records_have_observable_traces: train=2
- PASS [required] generated_artifacts_secret_scan: []
- PASS [required] plugin_register_capabilities: {'name': 'mock-self-coaching', 'version': '0.1.0', 'interfaces': ['python_module', 'cli', 'http'], 'capabilities': ['learning', 'self_play', 'evaluation', 'training']}
- PASS [required] http_health: {'root': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation-http', 'status': 'ok', 'version': '0.1.0'}
- PASS [required] http_full_phase_sequence: {'train': {'candidate': 'mock-grpo-candidate-6604b4', 'log_file': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\mock-services\\production-readiness-runs\\agent-skill-simulation-http\\.self-coaching\\logs\\train-f0c46604b4.log', 'manifest': 'C:\\Users\\liumy26\\.hermes\\skills\\self-coaching\\
- PASS [required] cli_subprocess_run_all: {'returncode': 0, 'stdout_tail': 'ate": "mock-sft-candidate-93e921",\n    "log_file": "C:\\\\Users\\\\liumy26\\\\.hermes\\\\skills\\\\self-coaching\\\\mock-services\\\\production-readiness-runs\\\\agent-skill-simulation-cli-subprocess\\\\.self-coaching\\\\logs\\\\train-2ff393e921.log",\n    "manifes
- PASS [optional] bash_mock_run_all_wrapper: skipped: bash not found

## Verdict
The mock-service pipeline is not yet integration-ready; fix required failures above before treating the skill as production-ready even for mocks.
