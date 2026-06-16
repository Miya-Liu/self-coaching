# SPDX-License-Identifier: MIT
"""Shared path constants for the self-coaching package."""

from __future__ import annotations

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
