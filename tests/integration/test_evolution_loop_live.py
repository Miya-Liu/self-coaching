# SPDX-License-Identifier: MIT
"""Live integration test for the self-coaching evolution loop (real backends).

Covers the integrated real services for the clock loop (E → P → T):
  - Self-questioning via Pipeline Service (ORCHESTRATOR_SELF_QUESTIONING_BACKEND=pipeline)
  - Self-tuning via CLI train / db_bridge (ORCHESTRATOR_TRAIN_BACKEND=cli)
  - Eval + learn remain mock (see scenarios/evolution_loop.json)

Enable with:
  EVOLUTION_LOOP_INTEGRATION_TESTS=1 pytest tests/integration/test_evolution_loop_live.py -v

Optional env:
  EVOLUTION_LOOP_ENV_FILE=scenarios/demo.live.env
  EVOLUTION_LOOP_INTEGRATION_TICK=1   # full tick with real remote training (slow)
  EVOLUTION_LOOP_KEEP_STATE=1         # do not wipe coaching root between tick runs
  EVOLUTION_LOOP_PROBE_TIMEOUT_S=120  # CLI probe poll budget

Examples:
  # Fast: connectivity + pipeline loop tick (~30s)
  EVOLUTION_LOOP_INTEGRATION_TESTS=1 pytest tests/integration/test_evolution_loop_live.py -k "preflight or pipeline" -v

  # CLI train round-trip (requires run_shell_runner on AReaL host)
  EVOLUTION_LOOP_INTEGRATION_TESTS=1 CLI_TRAIN_INTEGRATION_TESTS=1 \\
    pytest tests/integration/test_evolution_loop_live.py -k cli_probe -v

  # Full tick with real remote training (hours)
  EVOLUTION_LOOP_INTEGRATION_TESTS=1 EVOLUTION_LOOP_INTEGRATION_TICK=1 \\
    pytest tests/integration/test_evolution_loop_live.py -k full_tick -v
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO_ROOT / "scripts"
_DEFAULT_ENV = REPO_ROOT / "scenarios" / "demo.live.env.example"
_TICK_ROOT = REPO_ROOT / "mock-services" / "ci-evolution-loop-test"
_PROBE_TIMEOUT_S = int(os.environ.get("EVOLUTION_LOOP_PROBE_TIMEOUT_S", "120"))
_PROBE_COMMAND = (
    "echo TRAINING_COMPLETE checkpoint=/tmp/evolution-loop-integration "
    "model_id=evolution-loop-probe metrics={}"
)

for _entry in (
    str(REPO_ROOT),
    str(_SCRIPTS),
    str(REPO_ROOT / "modes"),
    str(REPO_ROOT / "modes" / "self-coaching"),
    str(REPO_ROOT / "modes" / "coach"),
    str(REPO_ROOT / "mock-services"),
    str(REPO_ROOT / "tools"),
):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

INTEGRATION_ENABLED = os.environ.get("EVOLUTION_LOOP_INTEGRATION_TESTS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}
TICK_ENABLED = os.environ.get("EVOLUTION_LOOP_INTEGRATION_TICK", "").strip().lower() in {
    "1",
    "true",
    "yes",
}
CLI_PROBE_ENABLED = os.environ.get("CLI_TRAIN_INTEGRATION_TESTS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

pytestmark = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="set EVOLUTION_LOOP_INTEGRATION_TESTS=1 to run live evolution loop probes",
)


def _load_env_file(path: Path) -> None:
    from loop_env import load_env_file, apply_loop_defaults, apply_service_mode

    if path.is_file():
        load_env_file(path)
    else:
        apply_loop_defaults()
    mode = os.environ.get("LOOP_SERVICE_MODE", "live")
    apply_service_mode(mode)


def _env_file() -> Path:
    raw = os.environ.get("EVOLUTION_LOOP_ENV_FILE", str(_DEFAULT_ENV))
    return Path(raw)


@pytest.fixture(scope="module", autouse=True)
def _configure_live_env():
    env_path = _env_file()
    if not env_path.is_file():
        pytest.skip(f"env file not found: {env_path}")
    _load_env_file(env_path)
    yield


class TestEvolutionLoopPreflight:
    """Fast connectivity probes — pipeline health, dry_run batch, Supabase reachability."""

    def test_pipeline_and_supabase_preflight(self):
        from evolution_loop_clock_smoke import preflight

        results = preflight()
        assert results.get("pipeline_health") is True, "Pipeline Service /health failed"
        assert results.get("pipeline_dry_run") is True, "Pipeline dry_run batch did not proceed"
        assert results.get("supabase_reachable") is True, "Supabase not reachable (check SUPABASE_URL)"


class TestEvolutionLoopPipelineTick:
    """End-to-end clock tick with real pipeline self-questioning (dry_run) and mock train/eval."""

    def test_clock_tick_c06_c07_with_pipeline_backend(self, monkeypatch: pytest.MonkeyPatch):
        import os

        from clock import load_scenario, run_tick
        from loop_env import build_loop_client
        from evolution_loop_clock_smoke import run_audit_phase
        from services.adapters.pipeline_service_client import PipelineServiceClient
        from services.adapters.self_questioning_pipeline_adapter import SelfQuestioningPipelineEngine

        monkeypatch.setenv("PIPELINE_DRY_RUN", "1")
        monkeypatch.setenv("ORCHESTRATOR_SELF_QUESTIONING_BACKEND", "pipeline")
        monkeypatch.setenv("ORCHESTRATOR_TRAIN_BACKEND", "mock")
        monkeypatch.setenv("ORCHESTRATOR_EVAL_BACKEND", "mock")

        pipeline_url = os.environ.get("PIPELINE_SERVICE_URL", "http://10.110.158.146:8001")
        fast_engine = SelfQuestioningPipelineEngine(
            PipelineServiceClient(
                pipeline_url,
                poll_interval_s=2.0,
                poll_timeout_s=60.0,
            ),
            use_sync=True,
        )
        monkeypatch.setattr("clock.build_self_questioning_engine", lambda root, config=None: fast_engine)

        if _TICK_ROOT.exists():
            shutil.rmtree(_TICK_ROOT)
        _TICK_ROOT.mkdir(parents=True, exist_ok=True)

        scenario = load_scenario(REPO_ROOT / "scenarios" / "evolution_loop.json")
        monkeypatch.setattr("evolution_loop_clock_smoke.ROOT", _TICK_ROOT)

        summary = run_tick(_TICK_ROOT, scenario, client=build_loop_client(_TICK_ROOT))

        assert summary.get("sparse_self_questioning_suite_id"), "C06 sparse self-questioning suite missing"
        assert summary.get("batch_self_questioning_suite_id"), "C07 batch self-questioning suite missing"
        assert summary.get("batch_self_questioning_proceed") is True, "batch self-questioning proceed=false"
        assert summary.get("t_path_promoted") is True, "T-path did not promote"

        report = run_audit_phase(REPO_ROOT / "scenarios" / "evolution_loop.json")
        assert report.get("status") == "PASS", report.get("failures")


@pytest.mark.skipif(
    not CLI_PROBE_ENABLED,
    reason="set CLI_TRAIN_INTEGRATION_TESTS=1 to run live CLI train probe",
)
class TestEvolutionLoopCLITrainProbe:
    """CLI train round-trip via db_bridge (requires run_shell_runner on AReaL host)."""

    def test_cli_probe_round_trip(self, monkeypatch: pytest.MonkeyPatch):
        from services.adapters.cli_train_adapter import CLITrainAdapter
        from services.adapters.cli_train_commands import TrainCommandSpec, resolve_train_cwd
        from services.adapters.cli_train_output import parse_training_marker
        from services.adapters.cli_train_transport import CLITrainTransport

        spec = TrainCommandSpec(
            run_id="evolution-loop-cli-probe",
            command=_PROBE_COMMAND,
            cwd=resolve_train_cwd(),
            tmux_id="evolution-loop-cli-probe",
            config_path="probe",
            log_file="training_evolution-loop-cli-probe.log",
            timeout_seconds=_PROBE_TIMEOUT_S,
        )
        monkeypatch.setattr(
            "services.adapters.cli_train_adapter.build_train_command_spec",
            lambda **kwargs: spec,
        )

        transport = CLITrainTransport.from_env(poll_timeout_s=float(_PROBE_TIMEOUT_S))
        try:
            row = transport.send_and_wait(
                spec.command,
                cwd=spec.cwd,
                tmux_id=spec.tmux_id,
                timeout_seconds=spec.timeout_seconds,
            )
        finally:
            transport.close()

        assert row.get("status") == "SUCCEEDED", row
        marker = parse_training_marker(row.get("stdout_tail") or "")
        assert marker.get("model_id") == "evolution-loop-probe"

        adapter = CLITrainAdapter(transport=CLITrainTransport.from_env(poll_timeout_s=float(_PROBE_TIMEOUT_S)))
        try:
            result = adapter.train(pipeline="grpo", base_model="qwen3-8b")
        finally:
            adapter._transport.close()

        assert result["status"] == "trained"
        assert result["candidate"] == "evolution-loop-probe"
        assert result["_train_backend"] == "cli"


@pytest.mark.skipif(
    not TICK_ENABLED,
    reason="set EVOLUTION_LOOP_INTEGRATION_TICK=1 to run full live clock tick with real training",
)
class TestEvolutionLoopFullTick:
    """Full evolution tick — real pipeline self-questioning and real CLI train dispatch."""

    def test_clock_tick_all_real_backends(self, monkeypatch: pytest.MonkeyPatch):
        from clock import load_scenario, run_tick
        from loop_env import build_loop_client
        from services.adapters.cli_train_adapter import CLITrainAdapter
        from services.adapters.cli_train_commands import TrainCommandSpec, resolve_train_cwd
        from services.adapters.cli_train_transport import CLITrainTransport
        from evolution_loop_clock_smoke import run_audit_phase

        monkeypatch.delenv("PIPELINE_DRY_RUN", raising=False)
        monkeypatch.setenv("ORCHESTRATOR_SELF_QUESTIONING_BACKEND", "pipeline")
        monkeypatch.setenv("ORCHESTRATOR_TRAIN_BACKEND", "cli")

        spec = TrainCommandSpec(
            run_id="evolution-loop-full-tick",
            command=_PROBE_COMMAND,
            cwd=resolve_train_cwd(),
            tmux_id="evolution-loop-full-tick",
            config_path="probe",
            log_file="training_evolution-loop-full-tick.log",
            timeout_seconds=_PROBE_TIMEOUT_S,
        )
        monkeypatch.setattr(
            "services.adapters.cli_train_adapter.build_train_command_spec",
            lambda **kwargs: spec,
        )

        transport = CLITrainTransport.from_env(poll_timeout_s=float(_PROBE_TIMEOUT_S))
        adapter = CLITrainAdapter(transport=transport)
        monkeypatch.setattr("loop_env._build_train_adapter", lambda config: adapter)

        keep_state = os.environ.get("EVOLUTION_LOOP_KEEP_STATE", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if not keep_state and _TICK_ROOT.exists():
            shutil.rmtree(_TICK_ROOT)
        _TICK_ROOT.mkdir(parents=True, exist_ok=True)

        scenario = load_scenario(REPO_ROOT / "scenarios" / "evolution_loop.json")
        monkeypatch.setattr("evolution_loop_clock_smoke.ROOT", _TICK_ROOT)

        summary = run_tick(_TICK_ROOT, scenario, client=build_loop_client(_TICK_ROOT))

        assert summary.get("sparse_self_questioning_suite_id"), "C06 sparse self-questioning suite missing"
        assert summary.get("batch_self_questioning_suite_id"), "C07 batch self-questioning suite missing"
        assert summary.get("batch_self_questioning_proceed") is True, "batch self-questioning proceed=false"
        assert summary.get("t_path_promoted") is True, "T-path did not promote"

        train_path = _TICK_ROOT / ".self-coaching" / "loop" / "runs" / "t_path" / "training.json"
        train_result = json.loads(train_path.read_text(encoding="utf-8"))
        assert train_result.get("candidate") == "evolution-loop-probe"

        report = run_audit_phase(REPO_ROOT / "scenarios" / "evolution_loop.json")
        assert report.get("status") == "PASS", report.get("failures")

        transport.close()
