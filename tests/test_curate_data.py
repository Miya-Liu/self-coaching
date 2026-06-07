# SPDX-License-Identifier: MIT
"""Unit tests for scripts/curate_data.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_curate_module():
    path = REPO_ROOT / "scripts" / "curate_data.py"
    spec = importlib.util.spec_from_file_location("curate_data", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["curate_data"] = mod
    spec.loader.exec_module(mod)
    return mod


curate = _load_curate_module().curate


@pytest.fixture
def sample_rows() -> list[dict]:
    base = {
        "labels": {"privacy_checked": True, "use_for": ["train"]},
        "messages": [{"role": "user", "content": "hi"}],
    }
    return [{**base, "case_id": f"case-{i}", "id": f"traj-{i}"} for i in range(10)]


def test_curate_splits_and_dedupes(tmp_path: Path, sample_rows: list[dict]):
    src = tmp_path / "input.jsonl"
    with src.open("w", encoding="utf-8") as fh:
        for row in sample_rows:
            fh.write(json.dumps(row) + "\n")
        fh.write(json.dumps(sample_rows[0]) + "\n")

    out = tmp_path / "curated"
    manifest = curate(
        input_path=src,
        out_dir=out,
        require_privacy_checked=True,
        train_ratio=0.8,
        dev_ratio=0.1,
    )

    assert manifest["counts"]["input"] == 11
    assert manifest["counts"]["skipped_duplicate"] == 1
    assert manifest["counts"]["kept"] == 10
    assert manifest["counts"]["train"] == 8
    assert manifest["counts"]["validation"] == 1
    assert manifest["counts"]["holdout"] == 1
    assert (out / "train.jsonl").is_file()
    assert (out / "validation.jsonl").is_file()
    assert (out / "holdout.jsonl").is_file()
    assert (out / "curation_manifest.json").is_file()


def test_curate_filters_privacy(tmp_path: Path):
    src = tmp_path / "input.jsonl"
    rows = [
        {"case_id": "a", "labels": {"privacy_checked": False}},
        {"case_id": "b", "labels": {"privacy_checked": True}},
    ]
    src.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    manifest = curate(
        input_path=src,
        out_dir=tmp_path / "out",
        require_privacy_checked=True,
        train_ratio=0.5,
        dev_ratio=0.0,
    )
    assert manifest["counts"]["skipped_privacy"] == 1
    assert manifest["counts"]["kept"] == 1
