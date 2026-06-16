# SPDX-License-Identifier: MIT
"""Shared path constants for the self-coaching package.

Canonical location for repo root, mock-services, and self-learning paths.
Other modules should import from here instead of reimplementing _repo_root().
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SC_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _SC_ROOT.parents[1]
_MOCK_SERVICES = _REPO_ROOT / "mock-services"
if not _MOCK_SERVICES.is_dir():
    _MOCK_SERVICES = _REPO_ROOT / "assets" / "mock-services"
_SELF_LEARNING = _SC_ROOT / "self-learning"
if str(_SELF_LEARNING) not in sys.path:
    sys.path.insert(0, str(_SELF_LEARNING))


def repo_root() -> Path:
    """Canonical repo root resolution.

    Priority: SELF_COACHING_SKILL_ROOT env → probe for mock-services/ → fallback.
    """
    raw = os.environ.get("SELF_COACHING_SKILL_ROOT")
    if raw:
        root = Path(raw).expanduser().resolve()
        if (root / "mock-services").is_dir() or (root / "assets" / "mock-services").is_dir():
            return root

    for candidate in (_REPO_ROOT, _SC_ROOT.parents[2], _SC_ROOT.parent):
        if (candidate / "mock-services").is_dir():
            return candidate
        if (candidate / "assets" / "mock-services").is_dir():
            return candidate

    return _REPO_ROOT


def mock_services_dir() -> Path:
    """Resolved mock-services directory."""
    root = repo_root()
    ms = root / "mock-services"
    if ms.is_dir():
        return ms
    return root / "assets" / "mock-services"
