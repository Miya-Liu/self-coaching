# SPDX-License-Identifier: MIT
"""Tests for the in-process Python API of mock-services/mock_self_coaching.py.

These exercise the contract documented in `mock-services/contracts/mock_service_contract.json`
and `mock-services/README.md`. They MUST stay green for any real service that
swaps in via the same Python interface.

Return-shape reference (read from the implementation):
  init      -> {"status": "initialized", "root": str, "manifest": str}
  learn     -> full record dict: {"id", "timestamp", "source", "capability", "event", ...}
  self_play -> {"status": "generated", "count": int, "case_ids": [str, ...]}
  evaluate  -> {"status": "passed"|"failed", "run_id": str, "report": str, "recommendation": str}
  train     -> {"status": "trained", "run_id": str, "candidate": str, "manifest": str, "log_file": str}
              (raises SystemExit for unsupported pipelines)
  run_all   -> {"status": "ok", "root", "init", "learning_event_id", "self_play",
                "baseline_eval", "training", "candidate_eval", "promotion_allowed"}
"""

import json
from pathlib import Path

import pytest

import mock_self_coaching as msc


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A fresh demo-run root per test."""
    return tmp_path / "demo-run"


# -------- contract: function names --------

def test_module_exposes_documented_functions():
    """Contract JSON lists exactly these public functions."""
    expected = {"init", "learn", "self_play", "evaluate", "train", "run_all"}
    for name in expected:
        assert hasattr(msc, name), f"module is missing documented function: {name}"
        assert callable(getattr(msc, name))


# -------- init --------

def test_init_creates_experience_workspace(root):
    result = msc.init(root)
    assert result["status"] == "initialized"
    assert result["root"] == str(root)
    assert Path(result["manifest"]).is_file()

    # README guarantees these artifacts exist after init.
    for rel in [
        "experience/EXPERIMENT_LOG.md",
        "experience/ERROR.md",
        "experience/LEARNINGS.md",
    ]:
        p = root / rel
        assert p.is_file(), f"init should have created {rel}"
        assert p.stat().st_size > 0, f"{rel} should not be empty"


def test_init_is_idempotent(root):
    msc.init(root)
    log_path = root / "experience" / "EXPERIMENT_LOG.md"
    first = log_path.read_bytes()
    # Second init must not clobber existing content.
    msc.init(root)
    second = log_path.read_bytes()
    assert first == second, "init must not overwrite existing experience files"


# -------- learn --------

def test_learn_appends_jsonl_event(root):
    msc.init(root)
    record = msc.learn(root, event="Agent forgot verification step")
    # Real return shape is the full record itself.
    assert "id" in record
    assert record["event"] == "Agent forgot verification step"
    assert record["privacy_checked"] is True

    events_path = root / ".self-coaching" / "events" / "learning_events.jsonl"
    assert events_path.is_file()
    lines = [ln for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "Agent forgot verification step"
    assert payload["id"] == record["id"]


def test_learn_multiple_events_accumulate(root):
    msc.init(root)
    msc.learn(root, event="first")
    msc.learn(root, event="second")
    events_path = root / ".self-coaching" / "events" / "learning_events.jsonl"
    lines = [ln for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2


# -------- self_play --------

def test_self_play_generates_requested_count(root):
    msc.init(root)
    msc.learn(root, event="seed event for self-play")
    result = msc.self_play(root, capability="tool_use", n=5)
    assert result["status"] == "generated"
    assert result["count"] == 5
    assert len(result["case_ids"]) == 5

    cases_path = root / ".self-coaching" / "cases" / "self_play_candidates.jsonl"
    lines = [ln for ln in cases_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 5
    for ln in lines:
        case = json.loads(ln)
        assert "tool_use" in case["capability"]
        assert "id" in case


def test_self_play_seeds_event_if_none_exists(root):
    """If no learning events exist yet, self_play must auto-seed one."""
    msc.init(root)
    result = msc.self_play(root, capability="tool_use", n=2)
    assert result["count"] == 2
    events_path = root / ".self-coaching" / "events" / "learning_events.jsonl"
    assert events_path.is_file()
    assert events_path.stat().st_size > 0


# -------- evaluate --------

def test_evaluate_produces_report(root):
    msc.init(root)
    msc.learn(root, event="seed")
    msc.self_play(root, capability="tool_use", n=3)
    result = msc.evaluate(root, candidate="cand-A", baseline="base-A")
    assert result["status"] in ("passed", "failed")
    run_id = result["run_id"]
    assert Path(result["report"]).is_file()

    report_path = root / ".self-coaching" / "reports" / "eval_runs" / run_id / "report.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["candidate"] == "cand-A"
    assert report["baseline"] == "base-A"
    assert "scores" in report
    assert "overall" in report["scores"]


def test_evaluate_marks_known_bad_candidate_as_failing(root):
    """Implementation: candidates with 'bad' or 'regress' in the name fail scoring."""
    msc.init(root)
    msc.self_play(root, capability="tool_use", n=4)
    result = msc.evaluate(root, candidate="bad-candidate-v1", baseline="mock-baseline-v0")
    assert result["status"] == "failed"
    assert result["recommendation"] == "do_not_promote"


# -------- train --------

def test_train_writes_manifest(root):
    msc.init(root)
    msc.learn(root, event="seed")
    msc.self_play(root, capability="tool_use", n=3)
    msc.evaluate(root)
    result = msc.train(root, pipeline="sft")
    assert result["status"] == "trained"
    assert Path(result["manifest"]).is_file()
    assert Path(result["log_file"]).is_file()

    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["pipeline_id"] == "sft"
    assert "log_file" in manifest
    assert "rollback_target" in manifest


def test_train_supports_both_documented_pipelines(root):
    """registry.yaml lists 'sft' and 'grpo'."""
    for pipeline in ("sft", "grpo"):
        root_p = root.with_name(f"demo-{pipeline}")
        msc.init(root_p)
        msc.self_play(root_p, capability="tool_use", n=2)
        result = msc.train(root_p, pipeline=pipeline)
        assert result["status"] == "trained"
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        assert manifest["pipeline_id"] == pipeline


def test_train_unknown_pipeline_is_rejected(root):
    msc.init(root)
    msc.self_play(root, capability="tool_use", n=2)
    with pytest.raises(SystemExit):
        msc.train(root, pipeline="not-a-real-pipeline-id")


# -------- run_all (end-to-end) --------

def test_run_all_produces_full_artifact_set(root):
    result = msc.run_all(root, capability="tool_use", pipeline="sft")
    assert result["status"] == "ok"
    assert result["root"] == str(root)
    assert "promotion_allowed" in result

    # Documented expected artifacts from mock-services/README.md.
    expected = [
        "experience/EXPERIMENT_LOG.md",
        "experience/ERROR.md",
        "experience/LEARNINGS.md",
        ".self-coaching/events/learning_events.jsonl",
        ".self-coaching/cases/self_play_candidates.jsonl",
        ".self-coaching/cases/eval_cases.jsonl",
        ".self-coaching/curated/train.jsonl",
        ".self-coaching/manifests/training_run_manifest.json",
        ".self-coaching/manifests/mock_pipeline_summary.json",
    ]
    for rel in expected:
        assert (root / rel).is_file(), f"run_all missing artifact: {rel}"


def test_run_all_promotes_good_baseline(root):
    """run_all uses the deterministic happy-path candidate name, which scores
    100% under the implementation's `'bad' in name` rule, so promotion is allowed."""
    result = msc.run_all(root, capability="tool_use", pipeline="sft")
    assert result["promotion_allowed"] is True
    assert result["candidate_eval"]["status"] == "passed"


def test_run_all_writes_eval_run_id_into_manifest(root):
    """The pipeline must wire the candidate eval back into the training manifest."""
    result = msc.run_all(root, capability="tool_use", pipeline="sft")
    manifest_path = root / ".self-coaching" / "manifests" / "training_run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["eval_run_id"] == result["candidate_eval"]["run_id"]


def test_run_all_shape_is_stable_across_invocations(tmp_path: Path):
    """Same inputs must produce the same summary shape (README: 'deterministic and stdlib-only')."""
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    summary_a = msc.run_all(root_a, capability="tool_use", pipeline="sft")
    summary_b = msc.run_all(root_b, capability="tool_use", pipeline="sft")

    # Compare the deterministic shape: same keys, same stage outcomes.
    # Drop timestamps/paths which legitimately differ between runs.
    def _shape(s: dict) -> dict:
        return {
            "keys": sorted(s.keys()),
            "promotion_allowed": s["promotion_allowed"],
            "self_play_count": s["self_play"]["count"],
            "training_pipeline": s["training"]["status"],
        }
    assert _shape(summary_a) == _shape(summary_b)
