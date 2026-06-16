# SPDX-License-Identifier: MIT
"""Shared path resolution for the services package.

Delegates to self_coaching._paths.repo_root() when available (editable install),
falls back to relative-path probe. Other services/ modules should import from here
instead of reimplementing _repo_root().
"""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    """Canonical repo root. Prefer self_coaching._paths; fall back to file location."""
    try:
        from self_coaching._paths import repo_root as _canonical
        return _canonical()
    except ImportError:
        return Path(__file__).resolve().parents[1]


def mock_services_dir() -> Path:
    """Resolved mock-services/ directory (handles assets/ layout for Hermes installs)."""
    root = repo_root()
    ms = root / "mock-services"
    if ms.is_dir():
        return ms
    alt = root / "assets" / "mock-services"
    if alt.is_dir():
        return alt
    return ms  # Caller will get FileNotFoundError if neither exists


def ensure_mock_services_importable() -> None:
    """Add mock-services/ to sys.path if not already present."""
    ms = str(mock_services_dir())
    if ms not in sys.path:
        sys.path.insert(0, ms)
