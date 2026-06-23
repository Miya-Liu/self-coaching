# SPDX-License-Identifier: MIT
"""Live probes for CLI training via db_bridge remote shell (opt-in).

Set CLI_TRAIN_INTEGRATION_TESTS=1 and provide Supabase credentials:

  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  BRIDGE_USER_ID

Optional:
  CLI_TRAIN_ENV_FILE=scenarios/demo.cli-train.env
  CLI_TRAIN_CWD=/dfs/share-groups/letrain/zhoujie/AReaL-main
  CLI_TRAIN_INTEGRATION_TIMEOUT_S=120

Uses a short echo command (not full GPU training). Requires run_shell_runner
active on the AReaL host with AREAL_REMOTE_SHELL_ENABLED=true.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
sys.path.insert(0, str(SC_ROOT))
sys.path.insert(0, str(REPO_ROOT))

from services.adapters.cli_train_adapter import CLITrainAdapter  # noqa: E402
from services.adapters.cli_train_commands import (  # noqa: E402
    TrainCommandSpec,
    resolve_train_cwd,
)
from services.adapters.cli_train_output import parse_training_marker  # noqa: E402
from services.adapters.cli_train_transport import CLITrainTransport  # noqa: E402

INTEGRATION_ENABLED = os.environ.get("CLI_TRAIN_INTEGRATION_TESTS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}
PROBE_TIMEOUT_S = int(os.environ.get("CLI_TRAIN_INTEGRATION_TIMEOUT_S", "120"))

_PROBE_COMMAND = (
    "echo TRAINING_COMPLETE checkpoint=/tmp/cli-train-integration "
    "model_id=integration-probe metrics={}"
)


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            os.environ.setdefault(key, value)


def _ensure_credentials() -> None:
    env_file = os.environ.get("CLI_TRAIN_ENV_FILE")
    if env_file:
        path = Path(env_file)
        if path.is_file():
            _load_env_file(path)
    db_bridge_env = REPO_ROOT / "services" / "LoRA" / "db_bridge" / ".env"
    if db_bridge_env.is_file():
        _load_env_file(db_bridge_env)


def _credentials_present() -> bool:
    return bool(
        os.environ.get("SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        and os.environ.get("BRIDGE_USER_ID")
    )


def _transport() -> CLITrainTransport:
    _ensure_credentials()
    return CLITrainTransport.from_env()


pytestmark = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="set CLI_TRAIN_INTEGRATION_TESTS=1 to run live CLI train probes",
)


@pytest.fixture(scope="module", autouse=True)
def _require_credentials():
    _ensure_credentials()
    if not _credentials_present():
        pytest.skip(
            "SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and BRIDGE_USER_ID required "
            "(set CLI_TRAIN_ENV_FILE or services/lora/db_bridge/.env)"
        )


class TestCLITrainTransportLive:
    def test_probe_round_trip(self):
        transport = _transport()
        row = transport.send_and_wait(
            _PROBE_COMMAND,
            cwd=resolve_train_cwd(),
            tmux_id="cli-train-integration-probe",
            timeout_seconds=PROBE_TIMEOUT_S,
        )
        transport.close()
        assert row.get("status") == "SUCCEEDED"
        stdout = row.get("stdout_tail") or ""
        marker = parse_training_marker(stdout)
        assert marker.get("model_id") == "integration-probe"
        assert marker.get("checkpoint") == "/tmp/cli-train-integration"


class TestCLITrainAdapterLive:
    def test_adapter_probe_via_transport_override(self, monkeypatch: pytest.MonkeyPatch):
        spec = TrainCommandSpec(
            run_id="cli-train-integration-adapter",
            command=_PROBE_COMMAND,
            cwd=resolve_train_cwd(),
            tmux_id="cli-train-integration-adapter",
            config_path="probe",
            log_file="training_cli-train-integration-adapter.log",
            timeout_seconds=PROBE_TIMEOUT_S,
        )
        monkeypatch.setattr(
            "services.adapters.cli_train_adapter.build_train_command_spec",
            lambda **kwargs: spec,
        )
        adapter = CLITrainAdapter(transport=_transport())
        result = adapter.train(pipeline="grpo", base_model="qwen3-8b")
        assert result["status"] == "trained"
        assert result["candidate"] == "integration-probe"
        assert result["terminal_status"] == "SUCCEEDED"
        assert result["_train_backend"] == "cli"
