# SPDX-License-Identifier: MIT
"""Resolve mock vs pipeline self-play engines for E-path / T-path."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    from .loop_config import LoopConfig, _self_play_base_url
except ImportError:
    from loop_config import LoopConfig, _self_play_base_url


def _repo_root() -> Path:
    try:
        from ._paths import repo_root
        return repo_root()
    except ImportError:
        from _paths import repo_root
        return repo_root()


def _ensure_mock_services() -> None:
    mock_services = _repo_root() / "mock-services"
    if str(mock_services) not in sys.path:
        sys.path.insert(0, str(mock_services))


def build_self_play_engine(
    config: LoopConfig,
    coaching_root: str | Path,
    *,
    override: Any | None = None,
) -> Any | None:
    """Return a self-play engine for C06/C07, or None to use HTTP mock URL path."""
    if override is not None:
        return override
    if config.self_play_factory is not None:
        return config.self_play_factory(Path(coaching_root))

    backend = str(config.selfplay_backend or "mock").lower()
    if backend == "pipeline":
        if str(_repo_root()) not in sys.path:
            sys.path.insert(0, str(_repo_root()))
        from services.adapters.selfplay_pipeline_adapter import build_self_play_pipeline_engine

        return build_self_play_pipeline_engine(config.pipeline_service_url)

    sp_url = config.self_play_url or _self_play_base_url()
    if sp_url:
        return None

    _ensure_mock_services()
    from mock_self_play import MockSelfPlayEngine

    return MockSelfPlayEngine(coaching_root)


def run_batch_self_play(
    *,
    coaching_root: Path,
    capability: str = "tool_use",
    n: int = 3,
    config: LoopConfig | None = None,
    engine: Any | None = None,
) -> dict[str, Any]:
    """C07 batch self-play — mock HTTP, mock engine, or pipeline engine."""
    cfg = config or LoopConfig.from_env()
    sp_url = cfg.self_play_url or _self_play_base_url()
    resolved = build_self_play_engine(cfg, coaching_root, override=engine)

    if resolved is not None and hasattr(resolved, "generate_batch"):
        return resolved.generate_batch(coaching_root=coaching_root, capability=capability, n=n)

    if sp_url:
        _ensure_mock_services()
        from mock_self_play import self_play_via_http

        return self_play_via_http(sp_url, coaching_root=coaching_root, capability=capability, n=n)

    if resolved is None:
        _ensure_mock_services()
        from mock_self_play import MockSelfPlayEngine

        resolved = MockSelfPlayEngine(coaching_root)
    return resolved.generate_batch(coaching_root=coaching_root, capability=capability, n=n)


def run_suite_self_play(
    *,
    coaching_root: Path,
    body: dict[str, Any],
    config: LoopConfig | None = None,
    engine: Any | None = None,
) -> dict[str, Any]:
    """C06 sparse self-play — mock HTTP, mock engine, or pipeline engine."""
    cfg = config or LoopConfig.from_env()
    sp_url = cfg.self_play_url or _self_play_base_url()
    resolved = build_self_play_engine(cfg, coaching_root, override=engine)

    if resolved is not None and hasattr(resolved, "generate_suite"):
        return resolved.generate_suite(**body)

    if sp_url:
        _ensure_mock_services()
        from mock_self_play import generate_suite_via_http

        return generate_suite_via_http(sp_url, body)

    if resolved is None:
        _ensure_mock_services()
        from mock_self_play import MockSelfPlayEngine

        resolved = MockSelfPlayEngine(coaching_root)
    return resolved.generate_suite(**body)
