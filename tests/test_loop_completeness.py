# SPDX-License-Identifier: MIT
"""Completeness reporter tests (C01–C18 matrix)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
MOCK_SERVICES = REPO_ROOT / "mock-services"
TOOLS = REPO_ROOT / "tools"
for _path in (SC_ROOT, SC_ROOT / "self-learning", MOCK_SERVICES, REPO_ROOT, TOOLS):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from client import ModuleClient  # noqa: E402
from loop_completeness import build_context, main, run_audit, write_report  # noqa: E402
from loop_driver import run_tasks, run_t_path  # noqa: E402
from loop_store import LoopStore, append_jsonl  # noqa: E402
from mock_agent_registry import AgentRegistry  # noqa: E402
from state import LoopStateStore  # noqa: E402

EPATH_FIXTURE = MOCK_SERVICES / "fixtures" / "task_stream" / "e_path_v1.jsonl"
TPATH_FIXTURE = MOCK_SERVICES / "fixtures" / "task_stream" / "t_path_v1.jsonl"
SPARSE_SCENARIO = REPO_ROOT / "scenarios" / "sparse_failures.json"
DENSE_SCENARIO = REPO_ROOT / "scenarios" / "dense_failures.json"
FULL_LOOP_SCENARIO = REPO_ROOT / "scenarios" / "full_loop.json"
FULL_LOOP_LIVE_SCENARIO = REPO_ROOT / "scenarios" / "full_loop_live.json"


def _write_eval_pair(run_dir: Path, *, current: float, candidate: float) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for name, score in (("current_eval.json", current), ("candidate_eval.json", candidate)):
        (run_dir / name).write_text(
            json.dumps({"score": score, "split": "holdout"}, indent=2) + "\n",
            encoding="utf-8",
        )
    (run_dir / "decision.json").write_text(
        json.dumps({"recommendation": "promote" if candidate >= current else "reject"}, indent=2) + "\n",
        encoding="utf-8",
    )


def _bootstrap_synthetic_pass_root(root: Path, *, promote: bool = True) -> None:
    """Minimal artifact tree that satisfies C01–C18 for full_loop promote scenario."""
    registry = AgentRegistry(root)
    registry.ensure_agent("demo-agent")
    draft = registry.create_version(
        "demo-agent",
        components={"skill_bundle_version": "skills-loop-v1"},
        source="mock_self_learning",
    )
    registry.activate("demo-agent", draft["version_id"])

    loop_dir = root / ".self-coaching" / "loop"
    loop_dir.mkdir(parents=True, exist_ok=True)
    (loop_dir / "state.json").write_text(
        json.dumps({"generation": 1, "support_count": 0, "buffer_count": 4, "tasks_processed": 14}, indent=2) + "\n",
        encoding="utf-8",
    )

    store = LoopStore(root)
    traj_id, traj_ref = store.save_trajectory(
        "syn-001",
        {
            "messages": [{"role": "assistant", "content": "ok"}],
            "tool_trace_summary": ["fetch status"],
            "final_answer": "deployment status summarized",
            "capability": ["tool_use"],
        },
        rubric_result={"score": 1.0, "breakdown": {"tools_ok": True, "answer_ok": True}},
    )
    append_jsonl(
        loop_dir / "support.jsonl",
        {
            "task_id": "syn-fail",
            "generation": 0,
            "version_id": "ver-0001",
            "trajectory_id": traj_id,
            "score": 0.0,
            "event_text": "synthetic failure",
            "trajectory_ref": traj_ref,
        },
    )
    append_jsonl(
        loop_dir / "tuning_buffer.jsonl",
        {
            "task_id": "syn-ok",
            "generation": 1,
            "version_id": draft["version_id"],
            "score": 0.95,
            "used_for_train": True,
            "trajectory_ref": traj_ref,
        },
    )

    (loop_dir / "e_path_last.json").write_text(
        json.dumps(
            {
                "generation": 1,
                "sigma_size_before_learn": 3,
                "sparse_self_play": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    run_dir = loop_dir / "runs" / "t_path"
    _write_eval_pair(run_dir, current=0.85, candidate=0.90 if promote else 0.70)
    (run_dir / "training.json").write_text(json.dumps({"run_id": "train-syn", "status": "trained"}, indent=2) + "\n", encoding="utf-8")

    reports = root / ".self-coaching" / "reports" / "eval_runs" / "eval-syn"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "report.json").write_text(json.dumps({"metrics": {"overall": 0.9}}, indent=2) + "\n", encoding="utf-8")

    curated = root / ".self-coaching" / "curated"
    curated.mkdir(parents=True, exist_ok=True)
    for name in ("train.jsonl", "validation.jsonl", "holdout.jsonl"):
        append_jsonl(curated / name, {"id": f"{name}-row", "case_id": f"{name}-only"})

    t_path_last = {
        "promoted": promote,
        "train_result": {"run_id": "train-syn", "status": "trained"},
        "candidate_version_id": "ver-candidate",
        "production_version_id": "ver-0001",
        "current_eval": {"score": 0.85},
        "candidate_eval": {"score": 0.90 if promote else 0.70},
        "batch_fill": None,
        "run_dir": str(run_dir),
    }
    (loop_dir / "t_path_last.json").write_text(json.dumps(t_path_last, indent=2) + "\n", encoding="utf-8")

    if promote:
        model_draft = registry.create_version(
            "demo-agent",
            components={"model_id": "mock-sft-candidate"},
            source="mock_aerl",
        )
        registry.activate("demo-agent", model_draft["version_id"])


def test_synthetic_matrix_emits_c01_through_c18(tmp_path: Path):
    root = tmp_path / "synthetic-pass"
    _bootstrap_synthetic_pass_root(root, promote=True)
    scenario = json.loads(FULL_LOOP_SCENARIO.read_text(encoding="utf-8"))
    report = run_audit(build_context(root, scenario))

    ids = {row["id"]: row for row in report["rows"]}
    assert set(ids) == {f"C{i:02d}" for i in range(1, 19)}

    for check_id in (f"C{i:02d}" for i in range(1, 15)):
        if ids[check_id]["invocation"] is not None:
            assert ids[check_id]["invocation"] == "pass", ids[check_id]

    assert ids["C06"]["invocation"] is None
    assert ids["C07"]["invocation"] is None
    assert ids["C16"]["semantic"] == "pass"
    assert ids["C17"]["semantic"] == "pass"
    assert ids["C18"]["semantic"] == "pass"
    assert report["status"] == "PASS"


def test_c18_semantic_fails_when_candidate_regresses_despite_invocation_pass(tmp_path: Path):
    root = tmp_path / "synthetic-c18-fail"
    _bootstrap_synthetic_pass_root(root, promote=False)
    scenario = json.loads(FULL_LOOP_SCENARIO.read_text(encoding="utf-8"))
    report = run_audit(build_context(root, scenario))

    rows = {row["id"]: row for row in report["rows"]}
    invocation_passes = [row for row in report["rows"] if row.get("invocation") == "pass"]
    assert invocation_passes, "expected invocation evidence rows to pass"

    assert rows["C18"]["semantic"] == "fail"
    assert rows["C18"]["invocation"] is None
    assert report["status"] == "FAIL"


def test_sparse_failures_scenario_expects_c06(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)
    monkeypatch.delenv("MOCK_SELF_LEARNING_URL", raising=False)

    root = tmp_path / "sparse"
    client = ModuleClient(root)
    scenario = json.loads(SPARSE_SCENARIO.read_text(encoding="utf-8"))
    stream = REPO_ROOT / scenario["task_stream"]

    run_tasks(
        root,
        task_stream_path=stream,
        limit=1,
        sigma_min=1,
        sigma_play=3,
        client=client,
        agent_id="demo-agent",
    )

    report = run_audit(build_context(root, scenario))
    rows = {row["id"]: row for row in report["rows"]}
    assert rows["C06"]["invocation"] == "pass"
    assert rows["C18"]["semantic"] is None


def test_dense_failures_skips_c06(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)
    monkeypatch.delenv("MOCK_SELF_LEARNING_URL", raising=False)

    root = tmp_path / "dense"
    client = ModuleClient(root)
    scenario = json.loads(DENSE_SCENARIO.read_text(encoding="utf-8"))
    loop_cfg = scenario["loop"]

    run_tasks(
        root,
        task_stream_path=REPO_ROOT / scenario["task_stream"],
        limit=loop_cfg["limit"],
        sigma_min=loop_cfg["sigma_min"],
        sigma_play=loop_cfg["sigma_play"],
        client=client,
        agent_id="demo-agent",
    )

    report = run_audit(build_context(root, scenario))
    rows = {row["id"]: row for row in report["rows"]}
    assert rows["C06"]["invocation"] is None
    assert rows["C10"]["invocation"] == "pass"


def test_e2e_full_loop_completeness_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Exit gate: E-path + T-path on mocks; completeness PASS including C18."""
    monkeypatch.setenv("AGENT_ID", "demo-agent")
    monkeypatch.delenv("MOCK_SELF_PLAY_URL", raising=False)
    monkeypatch.delenv("MOCK_SELF_LEARNING_URL", raising=False)
    monkeypatch.delenv("MOCK_AERL_URL", raising=False)

    root = tmp_path / "full-loop-e2e"
    client = ModuleClient(root)
    scenario = json.loads(FULL_LOOP_SCENARIO.read_text(encoding="utf-8"))

    run_tasks(
        root,
        task_stream_path=EPATH_FIXTURE,
        limit=10,
        sigma_min=3,
        sigma_play=0,
        enable_e_path=True,
        enable_t_path=False,
        client=client,
        agent_id="demo-agent",
    )

    state = LoopStateStore(root).load()
    assert state.generation >= 1

    registry = AgentRegistry(root)
    versions = registry.list_versions("demo-agent")
    assert len(versions) >= 2

    run_tasks(
        root,
        task_stream_path=TPATH_FIXTURE,
        limit=4,
        enable_e_path=False,
        enable_t_path=False,
        client=client,
        agent_id="demo-agent",
    )

    # Holdout gate: regressing production so SFT candidate clears check_promotion + C18.
    bad = registry.create_version(
        "demo-agent",
        components={"model_id": "bad-regress-v1"},
        source="full-loop-t-path-setup",
    )
    registry.activate("demo-agent", bad["version_id"])
    active_model = registry.get_agent("demo-agent")["version"]["components"]["model_id"]
    assert "regress" in str(active_model)

    loop_store = LoopStore(root)
    state = LoopStateStore(root).load()
    t_result = run_t_path(
        client=client,
        registry=registry,
        loop_store=loop_store,
        state=state,
        coaching_root=root,
        agent_id="demo-agent",
        beta=4,
    )
    assert t_result is not None
    assert t_result["promoted"] is True

    report = run_audit(build_context(root, scenario))
    out = write_report(root, report)
    assert out.is_file()

    rows = {row["id"]: row for row in report["rows"]}
    assert rows["C18"]["semantic"] == "pass", rows["C18"]
    assert report["status"] == "PASS", report.get("failures")

    exit_code = main(["--root", str(root), "--expect-json", str(FULL_LOOP_SCENARIO), "--json"])
    assert exit_code == 0


def test_full_loop_live_require_pass_ignores_c14_fail(tmp_path: Path):
    """Live scenario only requires C12 + C18; C14 promote failure is allowed."""
    root = tmp_path / "live-audit"
    scenario = json.loads(FULL_LOOP_LIVE_SCENARIO.read_text(encoding="utf-8"))
    _bootstrap_synthetic_pass_root(root, promote=False)

    run_dir = root / ".self-coaching" / "loop" / "runs" / "t_path"
    _write_eval_pair(run_dir, current=0.5, candidate=0.5)
    (root / ".self-coaching" / "loop" / "t_path_last.json").write_text(
        json.dumps({"promoted": False, "train_result": {"run_id": "train-1", "status": "ok"}}, indent=2) + "\n",
        encoding="utf-8",
    )

    report = run_audit(build_context(root, scenario))
    rows = {row["id"]: row for row in report["rows"]}
    assert rows["C12"]["invocation"] == "pass"
    assert rows["C18"]["semantic"] == "pass"
    assert rows["C14"]["invocation"] == "fail"
    assert report["status"] == "PASS"
