"""Test fixtures for the db_bridge package.

Ensures the repository root (parent of ``db_bridge``) is importable so tests
can ``import db_bridge`` regardless of pytest's invocation directory.

Skips all tests in this directory gracefully when the ``supabase`` package is
not installed (pip install -e ".[supabase]").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    import supabase  # noqa: F401

    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False


def pytest_collect_file(parent, file_path):  # type: ignore[override]
    """Skip collection of test files when supabase is not installed."""
    if not HAS_SUPABASE and file_path.suffix == ".py" and file_path.name.startswith("test_"):
        return None
    return None  # fall through to default collector


collect_ignore_glob: list[str] = []
if not HAS_SUPABASE:
    collect_ignore_glob = ["test_*.py"]
