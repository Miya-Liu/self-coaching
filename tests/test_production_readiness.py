# SPDX-License-Identifier: MIT
"""Tests for mock production-readiness harness."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mock-services"))

from production_readiness import run_all_checks  # noqa: E402


def test_production_readiness_passes(tmp_path: Path):
    checks = run_all_checks(tmp_path / "ready")
    failed = [c for c in checks if c.severity == "required" and not c.ok]
    assert not failed, [(c.name, c.detail) for c in failed]
    artifact = next(c for c in checks if c.name == "artifact_contract_required_paths")
    assert artifact.ok
    validation = tmp_path / "ready" / ".self-coaching" / "curated" / "validation.jsonl"
    holdout = tmp_path / "ready" / ".self-coaching" / "curated" / "holdout.jsonl"
    assert validation.is_file() and validation.stat().st_size > 0
    assert holdout.is_file() and holdout.stat().st_size > 0
