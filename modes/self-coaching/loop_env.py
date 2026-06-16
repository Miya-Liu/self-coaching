# SPDX-License-Identifier: MIT
"""Load demo service profiles from .env files (mock-module / mock-http / live)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

VALID_MODES = frozenset({"mock-module", "mock-http", "live"})

MOCK_URL_KEYS = (
    "MOCK_SELF_LEARNING_URL",
    "MOCK_SELF_PLAY_URL",
    "MOCK_AERL_URL",
    "MOCK_AGENTEVALS_URL",
    "AGENTEVALS_BASE_URL",
)

LOOP_DEFAULTS: dict[str, str] = {
    "LOOP_SERVICE_MODE": "mock-module",
    "LOOP_AGENT_ID": "demo-agent",
    "LOOP_TAU_FAIL": "0.75",
    "LOOP_SIGMA_MIN": "3",
    "LOOP_SIGMA_PLAY": "0",
    "LOOP_BATCH_SIZE": "4",
    "LOOP_IDLE_AFTER": "0",
    "LOOP_HOLDOUT_TIMEOUT_S": "5",
    "ORCHESTRATOR_EVAL_BACKEND": "mock",
    "ORCHESTRATOR_TRAIN_BACKEND": "mock",
    "ORCHESTRATOR_LEARN_BACKEND": "mock",
    "ORCHESTRATOR_TRANSPORT": "module",
    "AGENTEVALS_SUITE_ID": "tool-use-canary",
    "AGENTEVALS_SUITE_ID_HOLDOUT": "tool-use-holdout",
    "LOOP_AUTO_START_MOCK_STACK": "1",
}


@dataclass(frozen=True)
class ServiceProfile:
    mode: str
    agent_id: str
    eval_backend: str
    train_backend: str
    auto_start_mock_stack: bool
    service_urls: dict[str, str]


def _strip_optional_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: str | Path, *, overwrite: bool = True) -> dict[str, str]:
    """Parse a dotenv-style file into key/value pairs and apply to os.environ."""
    env_path = Path(path).resolve()
    if not env_path.is_file():
        raise FileNotFoundError(f"env file not found: {env_path}")

    loaded: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = _strip_optional_quotes(value.split("#", 1)[0].strip())
        loaded[key] = value
        if overwrite or key not in os.environ:
            os.environ[key] = value
    return loaded


def apply_loop_defaults() -> None:
    for key, value in LOOP_DEFAULTS.items():
        os.environ.setdefault(key, value)


def resolve_service_mode(*, with_http: bool = False) -> str:
    if with_http:
        return "mock-http"
    mode = os.environ.get("LOOP_SERVICE_MODE", "mock-module").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"invalid LOOP_SERVICE_MODE={mode!r}; expected one of {sorted(VALID_MODES)}")
    os.environ["LOOP_SERVICE_MODE"] = mode
    return mode


def apply_service_mode(mode: str) -> None:
    """Normalize env for the selected service mode."""
    agent_id = os.environ.get("LOOP_AGENT_ID", "demo-agent")
    os.environ["AGENT_ID"] = agent_id
    os.environ["LOOP_AGENT_ID"] = agent_id
    apply_loop_defaults()
    os.environ["LOOP_SERVICE_MODE"] = mode

    if mode == "mock-module":
        for key in MOCK_URL_KEYS:
            os.environ.pop(key, None)
        os.environ.pop("TRAINER_BASE_URL", None)
        os.environ["ORCHESTRATOR_EVAL_BACKEND"] = "mock"
        os.environ["ORCHESTRATOR_TRAIN_BACKEND"] = "mock"
        os.environ["ORCHESTRATOR_LEARN_BACKEND"] = "mock"
        os.environ["ORCHESTRATOR_TRANSPORT"] = "module"
        return

    if mode == "mock-http":
        os.environ.setdefault("ORCHESTRATOR_EVAL_BACKEND", "mock")
        os.environ.setdefault("ORCHESTRATOR_TRAIN_BACKEND", "mock")
        ae_port = os.environ.get("MOCK_AGENTEVALS_PORT", "38180")
        learning_port = os.environ.get("MOCK_SELF_LEARNING_PORT", "38766")
        self_play_port = os.environ.get("MOCK_SELF_PLAY_PORT", "38767")
        aerl_port = os.environ.get("MOCK_AERL_PORT", "38004")
        os.environ.setdefault("MOCK_AGENTEVALS_URL", f"http://127.0.0.1:{ae_port}")
        os.environ.setdefault("MOCK_SELF_LEARNING_URL", f"http://127.0.0.1:{learning_port}")
        os.environ.setdefault("MOCK_SELF_PLAY_URL", f"http://127.0.0.1:{self_play_port}")
        os.environ.setdefault("MOCK_AERL_URL", f"http://127.0.0.1:{aerl_port}")
        os.environ.setdefault("TRAINER_BASE_URL", f"http://127.0.0.1:{aerl_port}")
        return

    # live — upgrade backends only when a matching service URL is configured
    ae_url = os.environ.get("AGENTEVALS_BASE_URL") or os.environ.get("MOCK_AGENTEVALS_URL")
    train_url = os.environ.get("TRAINER_BASE_URL") or os.environ.get("MOCK_AERL_URL")
    if os.environ.get("ORCHESTRATOR_EVAL_BACKEND", "mock") == "mock" and ae_url:
        os.environ["ORCHESTRATOR_EVAL_BACKEND"] = "agentevals"
    if os.environ.get("ORCHESTRATOR_TRAIN_BACKEND", "mock") == "mock" and train_url:
        os.environ["ORCHESTRATOR_TRAIN_BACKEND"] = "aerl"
    os.environ.setdefault("LOOP_HOLDOUT_TIMEOUT_S", "300")


def should_auto_start_mock_stack(mode: str) -> bool:
    if mode != "mock-http":
        return False
    return os.environ.get("LOOP_AUTO_START_MOCK_STACK", "1").strip() not in {"0", "false", "False", "no"}


def service_profile(mode: str | None = None) -> ServiceProfile:
    resolved = mode or os.environ.get("LOOP_SERVICE_MODE", "mock-module")
    urls = {key: os.environ[key] for key in MOCK_URL_KEYS if os.environ.get(key)}
    if os.environ.get("TRAINER_BASE_URL"):
        urls["TRAINER_BASE_URL"] = os.environ["TRAINER_BASE_URL"]
    return ServiceProfile(
        mode=resolved,
        agent_id=os.environ.get("LOOP_AGENT_ID", "demo-agent"),
        eval_backend=os.environ.get("ORCHESTRATOR_EVAL_BACKEND", "mock"),
        train_backend=os.environ.get("ORCHESTRATOR_TRAIN_BACKEND", "mock"),
        auto_start_mock_stack=should_auto_start_mock_stack(resolved),
        service_urls=urls,
    )


def format_service_profile(profile: ServiceProfile) -> str:
    lines = [
        f"service mode: {profile.mode}",
        f"agent_id: {profile.agent_id}",
        f"eval_backend: {profile.eval_backend}",
        f"train_backend: {profile.train_backend}",
    ]
    if profile.mode == "mock-http":
        lines.append(f"auto_start_mock_stack: {profile.auto_start_mock_stack}")
    if profile.service_urls:
        lines.append("service urls:")
        for key in sorted(profile.service_urls):
            lines.append(f"  {key}={profile.service_urls[key]}")
    else:
        lines.append("service urls: (in-process mocks)")
    return "\n".join(lines)


def configure_demo_env(
    *,
    env_file: str | Path | None = None,
    with_http: bool = False,
) -> ServiceProfile:
    """Load optional env file, resolve mode, apply profile.

    After this call, os.environ is configured and LoopConfig.from_env() will
    produce the correct config. Legacy callers use the returned ServiceProfile;
    new code should call LoopConfig.from_env() after this.
    """
    if env_file is not None:
        load_env_file(env_file)
    else:
        apply_loop_defaults()

    mode = resolve_service_mode(with_http=with_http)
    apply_service_mode(mode)
    return service_profile(mode)


def default_env_file(repo_root: str | Path) -> Path | None:
    """Return scenarios/demo.env if present."""
    candidate = Path(repo_root) / "scenarios" / "demo.env"
    return candidate if candidate.is_file() else None


def _skill_root_from_env() -> Path | None:
    raw = os.environ.get("SELF_COACHING_SKILL_ROOT")
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    if (root / "mock-services").is_dir() or (root / "assets" / "mock-services").is_dir():
        return root
    return None


def _repo_root() -> Path:
    from_env = _skill_root_from_env()
    if from_env is not None:
        return from_env
    here = Path(__file__).resolve().parent
    for candidate in (here.parents[1], here.parents[2], here.parent):
        if (candidate / "mock-services").is_dir():
            return candidate
        if (candidate / "assets" / "mock-services").is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not locate repo root (mock-services/). "
        "Set SELF_COACHING_SKILL_ROOT to your Hermes install (~/.hermes/skills/self-coaching), "
        "or: pip install -e ."
    )


def build_loop_client(coaching_root: str | Path, config: Any | None = None) -> Any:
    """Build SelfCoaching loop client with composite eval/train/learn adapters.

    Args:
        coaching_root: Path to the coaching root directory.
        config: Optional LoopConfig. If None, builds from os.environ (legacy).
    """
    import sys

    # Lazy import to avoid circular dep at module level
    try:
        from .loop_config import LoopConfig
    except ImportError:
        from loop_config import LoopConfig

    if config is None:
        config = LoopConfig.from_env()

    repo_root = _repo_root()
    mock_services = repo_root / "mock-services"
    if not mock_services.is_dir():
        mock_services = repo_root / "assets" / "mock-services"
    if str(mock_services) not in sys.path:
        sys.path.insert(0, str(mock_services))
    import client as client_mod  # noqa: E402

    root = Path(coaching_root).resolve()
    if config.transport == "http":
        base_url = config.orchestrator_base_url or "http://127.0.0.1:8765"
        inner = client_mod.build_client("http", base_url=base_url, api_key=config.api_token)
    else:
        inner = client_mod.ModuleClient(root)

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from services.adapters import build_composite_client  # noqa: E402

    return build_composite_client(
        inner,
        eval_backend=config.eval_backend,
        train_backend=config.train_backend,
        learn_backend=config.learn_backend,
    )
