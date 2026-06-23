#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Evolution loop clock smoke — Track 1 live integration (AgentEvals + Pipeline + CLI train).

Phases:
  1. Preflight: Pipeline, Supabase, AgentEvals (+ optional CLI probe)
  2. Clock tick: one full evolution tick (E-path → T-path) with live backends
  3. Audit: completeness report + golden diff for evolution_loop_live

Usage:
  cp scenarios/demo.live.env.example scenarios/demo.live.env
  python scripts/evolution_loop_clock_smoke.py --env-file scenarios/demo.live.env --phase preflight
  python scripts/evolution_loop_clock_smoke.py --env-file scenarios/demo.live.env --dry-run --probe-cli
  python scripts/evolution_loop_clock_smoke.py --env-file scenarios/demo.live.env
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
_SC = REPO_ROOT / "modes" / "self-coaching"
_COACH = REPO_ROOT / "modes" / "coach"
_MODES = REPO_ROOT / "modes"
_MOCK = REPO_ROOT / "mock-services"
_TOOLS = REPO_ROOT / "tools"
for _entry in (
    str(_MODES),
    str(_COACH),
    str(_SC),
    str(_SC / "self-learning"),
    str(_MOCK),
    str(REPO_ROOT),
    str(_TOOLS),
):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

DEFAULT_ENV = REPO_ROOT / "scenarios" / "demo.live.env"
DEFAULT_ENV_EXAMPLE = REPO_ROOT / "scenarios" / "demo.live.env.example"
DEFAULT_SCENARIO = REPO_ROOT / "scenarios" / "evolution_loop_live.json"
GOLDEN = REPO_ROOT / "tests" / "fixtures" / "golden" / "completeness_report_evolution_loop_live.json"
ROOT = _MOCK / "ci-evolution-loop"
_PROBE_COMMAND = (
    "echo TRAINING_COMPLETE checkpoint=/tmp/evolution-loop-smoke "
    "model_id=evolution-loop-probe metrics={}"
)
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _backend(name: str, default: str = "mock") -> str:
    return os.environ.get(name, default).strip().lower()


def _resolve_env_file(path: Path | None) -> Path:
    if path is not None and path.is_file():
        return path
    if DEFAULT_ENV.is_file():
        return DEFAULT_ENV
    if DEFAULT_ENV_EXAMPLE.is_file():
        return DEFAULT_ENV_EXAMPLE
    return path or DEFAULT_ENV


def _check_golden(report: dict[str, Any], golden: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if golden.get("status") is not None and report.get("status") != golden.get("status"):
        errors.append(f"status={report.get('status')!r} expected {golden.get('status')!r}")
    rows = {row["id"]: row for row in report.get("rows", [])}
    for spec in golden.get("rows", []):
        row_id = spec["id"]
        actual = rows.get(row_id)
        if actual is None:
            errors.append(f"missing row {row_id}")
            continue
        for col in ("invocation", "semantic"):
            expected = spec.get(col)
            if expected is not None and actual.get(col) != expected:
                errors.append(f"{row_id}.{col}={actual.get(col)!r} expected {expected!r}")
    return errors


def golden_from_report(report: dict[str, Any], *, row_ids: list[str] | None = None) -> dict[str, Any]:
    """Build a stable golden subset from a live completeness audit report."""
    ids = row_ids or ["C06", "C07", "C12", "C18"]
    rows_by_id = {row["id"]: row for row in report.get("rows", [])}
    return {
        "scenario": report.get("scenario"),
        "status": report.get("status"),
        "required_rows": ids,
        "rows": [
            {
                "id": row_id,
                "invocation": rows_by_id[row_id].get("invocation"),
                "semantic": rows_by_id[row_id].get("semantic"),
            }
            for row_id in ids
            if row_id in rows_by_id
        ],
    }


def write_golden(report: dict[str, Any], path: Path = GOLDEN) -> Path:
    """Persist golden fixture from a passing audit report (M-W2)."""
    payload = golden_from_report(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def preflight(*, probe_cli: bool = False) -> dict[str, bool]:
    """Check connectivity to configured real services before a full tick."""
    results: dict[str, bool] = {}
    sq_backend = _backend("ORCHESTRATOR_SELF_QUESTIONING_BACKEND")
    train = _backend("ORCHESTRATOR_TRAIN_BACKEND")
    eval_backend = _backend("ORCHESTRATOR_EVAL_BACKEND")

    if sq_backend == "pipeline":
        pipeline_url = os.environ.get("PIPELINE_SERVICE_URL", "http://10.110.158.146:8001")
        print(f"  [preflight] Pipeline Service: {pipeline_url}")
        try:
            from services.adapters.pipeline_service_client import PipelineServiceClient

            client = PipelineServiceClient(
                pipeline_url,
                poll_interval_s=float(os.environ.get("PIPELINE_POLL_INTERVAL_S", "2")),
                poll_timeout_s=float(os.environ.get("PIPELINE_PREFLIGHT_TIMEOUT_S", "120")),
            )
            health = client.health()
            results["pipeline_health"] = health.get("status") == "ok"
            print(f"    health: {health.get('status')}")
        except Exception as exc:
            results["pipeline_health"] = False
            print(f"    FAIL: {exc}")

        if results.get("pipeline_health"):
            try:
                from services.adapters.self_questioning_pipeline_adapter import build_self_questioning_pipeline_engine

                os.environ["PIPELINE_DRY_RUN"] = "1"
                engine = build_self_questioning_pipeline_engine(pipeline_url)
                batch = engine.generate_batch(coaching_root=ROOT, n=1)
                results["pipeline_dry_run"] = batch.get("proceed", False)
                print(f"    dry_run batch: proceed={batch.get('proceed')} job_id={batch.get('job_id')}")
            except Exception as exc:
                results["pipeline_dry_run"] = False
                print(f"    dry_run FAIL: {exc}")
            finally:
                os.environ.pop("PIPELINE_DRY_RUN", None)

    if train == "cli":
        supabase_url = os.environ.get("SUPABASE_URL")
        if supabase_url:
            print(f"  [preflight] Supabase: {supabase_url}")
            try:
                req = urllib.request.Request(
                    f"{supabase_url.rstrip('/')}/rest/v1/",
                    headers={
                        "apikey": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
                        "Authorization": f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')}",
                    },
                )
                with _NO_PROXY_OPENER.open(req, timeout=10) as resp:
                    results["supabase_reachable"] = resp.status == 200
                    print(f"    status: {resp.status}")
            except (urllib.error.URLError, OSError, ValueError) as exc:
                results["supabase_reachable"] = False
                print(f"    FAIL: {exc}")
        else:
            results["supabase_reachable"] = False
            print("  [preflight] Supabase: not configured (SUPABASE_URL missing)")

        if probe_cli:
            print("  [preflight] CLI train probe (db_bridge round-trip)")
            try:
                from services.adapters.cli_train_commands import resolve_train_cwd
                from services.adapters.cli_train_transport import CLITrainTransport

                timeout_s = int(os.environ.get("EVOLUTION_LOOP_PROBE_TIMEOUT_S", "120"))
                transport = CLITrainTransport.from_env(poll_timeout_s=float(timeout_s))
                row = transport.send_and_wait(
                    _PROBE_COMMAND,
                    cwd=resolve_train_cwd(),
                    tmux_id="evolution-loop-smoke-probe",
                    timeout_seconds=timeout_s,
                )
                transport.close()
                ok = row.get("status") == "SUCCEEDED"
                results["cli_probe"] = ok
                print(f"    status: {row.get('status')}")
            except Exception as exc:
                results["cli_probe"] = False
                print(f"    FAIL: {exc}")

    if eval_backend == "agentevals":
        ae_url = os.environ.get("AGENTEVALS_BASE_URL") or os.environ.get("MOCK_AGENTEVALS_URL")
        print(f"  [preflight] AgentEvals: {ae_url or '(not configured)'}")
        if not ae_url:
            results["agentevals_health"] = False
            print("    FAIL: AGENTEVALS_BASE_URL missing")
        else:
            try:
                from services.adapters.agentevals_client import AgentEvalsClient

                client = AgentEvalsClient(base_url=ae_url, poll_timeout_s=30.0)
                health = client.health()
                results["agentevals_health"] = str(health.get("status", "")).lower() == "ok"
                print(f"    health: {health.get('status')}")
            except Exception as exc:
                results["agentevals_health"] = False
                print(f"    FAIL: {exc}")

    return results


def _preflight_required_ok(results: dict[str, bool], *, probe_cli: bool) -> bool:
    checks: list[bool] = []
    if _backend("ORCHESTRATOR_SELF_QUESTIONING_BACKEND") == "pipeline":
        checks.extend([results.get("pipeline_health", False), results.get("pipeline_dry_run", False)])
    if _backend("ORCHESTRATOR_TRAIN_BACKEND") == "cli":
        checks.append(results.get("supabase_reachable", False))
        if probe_cli:
            checks.append(results.get("cli_probe", False))
    if _backend("ORCHESTRATOR_EVAL_BACKEND") == "agentevals":
        checks.append(results.get("agentevals_health", False))
    return bool(checks) and all(checks)


def collect_artifacts(coaching_root: Path) -> dict[str, Any]:
    loop_dir = coaching_root / ".self-coaching" / "loop"
    run_dir = loop_dir / "runs" / "t_path"
    return {
        "e_path_last": _read_json(loop_dir / "e_path_last.json"),
        "t_path_last": _read_json(loop_dir / "t_path_last.json"),
        "training": _read_json(run_dir / "training.json"),
        "candidate_eval": _read_json(run_dir / "candidate_eval.json"),
        "current_eval": _read_json(run_dir / "current_eval.json"),
        "completeness_report": _read_json(loop_dir / "completeness_report.json"),
    }


def assert_tick_artifacts(
    artifacts: dict[str, Any],
    *,
    dry_run: bool,
) -> list[str]:
    """Validate external service responses recorded on disk."""
    errors: list[str] = []
    e_path = artifacts.get("e_path_last") or {}
    t_path = artifacts.get("t_path_last") or {}
    sparse = e_path.get("sparse_self_questioning") or {}
    batch_fill = t_path.get("batch_fill") or {}
    training = artifacts.get("training") or t_path.get("train_result") or {}
    candidate_eval = artifacts.get("candidate_eval") or {}

    if _backend("ORCHESTRATOR_SELF_QUESTIONING_BACKEND") == "pipeline":
        if not (sparse.get("suite_id") or sparse.get("job_id")):
            errors.append("C06: missing sparse suite_id or pipeline job_id")
        if sparse.get("pipeline_service") and not sparse.get("proceed"):
            errors.append("C06: pipeline sparse self-questioning proceed=false")
        if not (batch_fill.get("suite_id") or batch_fill.get("job_id")):
            errors.append("C07: missing batch suite_id or pipeline job_id")
        if batch_fill.get("pipeline_service") and not batch_fill.get("proceed"):
            errors.append("C07: pipeline batch self-questioning proceed=false")
        for label, payload in (("C06", sparse), ("C07", batch_fill)):
            if payload.get("pipeline_service") and payload.get("job_id"):
                stages = payload.get("stage_results") or {}
                if stages and not all(stages.get(str(i)) for i in (1, 2, 3)):
                    errors.append(f"{label}: pipeline stage_results incomplete: {stages}")

    if _backend("ORCHESTRATOR_TRAIN_BACKEND") == "cli" and not dry_run:
        terminal = training.get("terminal_status") or training.get("status")
        backend = training.get("_train_backend")
        if terminal not in {"SUCCEEDED", "trained", None}:
            errors.append(f"CLI train: terminal status {terminal!r}")
        if backend and backend != "cli":
            errors.append(f"CLI train: expected _train_backend=cli got {backend!r}")

    if _backend("ORCHESTRATOR_EVAL_BACKEND") == "agentevals":
        run_id = candidate_eval.get("run_id")
        raw = candidate_eval.get("raw") or {}
        run_detail = raw.get("run_detail") or {}
        if not run_id and not run_detail.get("id"):
            errors.append("AgentEvals: missing candidate holdout run_id")
        if run_detail and str(run_detail.get("status", "")).lower() not in {"", "succeeded"}:
            errors.append(f"AgentEvals: candidate run status={run_detail.get('status')!r}")

    if not t_path.get("promoted") and not dry_run:
        errors.append("T-path: promoted=false")

    return errors


def run_clock_tick(
    scenario_path: Path,
    *,
    keep_state: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run one full evolution tick with live backends."""
    from clock import load_scenario, run_tick

    saved_train_backend: str | None = None
    saved_supabase: dict[str, str | None] = {}
    if dry_run:
        os.environ["PIPELINE_DRY_RUN"] = "1"
        if _backend("ORCHESTRATOR_TRAIN_BACKEND") == "cli":
            saved_train_backend = os.environ.get("ORCHESTRATOR_TRAIN_BACKEND")
            os.environ["ORCHESTRATOR_TRAIN_BACKEND"] = "mock"
            # Hide all db_bridge creds so LoopConfig live-mode auto-detection
            # does not upgrade train mock→cli via cli_train_env_configured().
            for key in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "BRIDGE_USER_ID"):
                saved_supabase[key] = os.environ.pop(key, None)

    if not keep_state and ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True, exist_ok=True)

    scenario = load_scenario(scenario_path)
    print(f"  [tick] scenario={scenario.get('name')} agent={scenario.get('agent_id')}")
    print(
        "  [tick] backends:"
        f" eval={os.environ.get('ORCHESTRATOR_EVAL_BACKEND')},"
        f" learn={os.environ.get('ORCHESTRATOR_LEARN_BACKEND')},"
        f" self_questioning={os.environ.get('ORCHESTRATOR_SELF_QUESTIONING_BACKEND')},"
        f" train={os.environ.get('ORCHESTRATOR_TRAIN_BACKEND')}"
    )
    if _backend("ORCHESTRATOR_SELF_QUESTIONING_BACKEND") == "pipeline":
        poll_timeout = float(os.environ.get("PIPELINE_POLL_TIMEOUT_S", "3600"))
        print(f"  [tick] pipeline poll timeout: {poll_timeout}s")
        if not dry_run and poll_timeout < 600:
            print(
                f"  WARNING: PIPELINE_POLL_TIMEOUT_S={poll_timeout}s is likely too short for "
                f"real batch jobs. The .example recommends 3600s. Set PIPELINE_POLL_TIMEOUT_S=3600 "
                f"in your env file or pass --dry-run for a faster integrated check.",
                file=sys.stderr,
            )
    if dry_run:
        print("  [tick] dry_run=1 (pipeline dry_run; train uses mock when cli configured)")

    t0 = time.time()
    try:
        summary = run_tick(ROOT, scenario)
    finally:
        os.environ.pop("PIPELINE_DRY_RUN", None)
        if saved_train_backend is not None:
            os.environ["ORCHESTRATOR_TRAIN_BACKEND"] = saved_train_backend
        for key, value in saved_supabase.items():
            if value is not None:
                os.environ[key] = value
    elapsed = time.time() - t0

    print(f"  [tick] completed in {elapsed:.1f}s")
    print(f"    generation: {summary.get('generation_before')} → {summary.get('generation_after')}")
    print(f"    sparse self-questioning (C06): {summary.get('sparse_self_questioning_suite_id')}")
    print(f"    batch self-questioning (C07): {summary.get('batch_self_questioning_suite_id')}")
    print(f"    batch proceed: {summary.get('batch_self_questioning_proceed')}")
    print(f"    T-path promoted: {summary.get('t_path_promoted')}")

    return summary


def run_audit_phase(scenario_path: Path) -> dict[str, Any]:
    """Run completeness audit on the coaching root."""
    from clock import load_scenario
    from loop_completeness import build_context, run_audit, write_report

    scenario = load_scenario(scenario_path)
    report = run_audit(build_context(ROOT, scenario))
    write_report(ROOT, report)

    pass_count = sum(1 for r in report.get("rows", []) if r.get("invocation") == "pass")
    fail_count = sum(1 for r in report.get("rows", []) if r.get("invocation") == "fail")
    total = len(report.get("rows", []))
    print(f"  [audit] status={report.get('status')} pass={pass_count}/{total} fail={fail_count}")
    if report.get("failures"):
        for failure in report["failures"]:
            print(f"    FAIL: {failure}")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evolution loop clock smoke — Track 1 live integration verification"
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Environment file (default: scenarios/demo.live.env or .example)",
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        default=DEFAULT_SCENARIO,
        help="Scenario manifest (default: scenarios/evolution_loop_live.json)",
    )
    parser.add_argument(
        "--phase",
        choices=["preflight", "tick", "audit", "all"],
        default="all",
        help="Which phase to run (default: all)",
    )
    parser.add_argument("--keep-state", action="store_true", help="Don't wipe coaching root before tick")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pipeline dry_run + mock train for a faster integrated tick",
    )
    parser.add_argument(
        "--probe-cli",
        action="store_true",
        help="During preflight, run a short CLI train echo probe via db_bridge",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary on stdout")
    parser.add_argument(
        "--write-golden",
        action="store_true",
        help="After a PASS audit, write tests/fixtures/golden/completeness_report_evolution_loop_live.json (M-W2)",
    )
    args = parser.parse_args(argv)

    from loop_env import apply_loop_defaults, apply_service_mode, load_env_file

    env_path = _resolve_env_file(args.env_file)
    if env_path.is_file():
        load_env_file(env_path)
    else:
        print(f"WARNING: env file not found: {env_path}", file=sys.stderr)
        print(f"  Copy {DEFAULT_ENV_EXAMPLE} → scenarios/demo.live.env", file=sys.stderr)
        apply_loop_defaults()

    mode = os.environ.get("LOOP_SERVICE_MODE", "live")
    apply_service_mode(mode)

    print("═══ Evolution Loop Clock Smoke ═══")
    print(f"  mode: {mode}")
    print(f"  eval: {os.environ.get('ORCHESTRATOR_EVAL_BACKEND')}")
    print(f"  learn: {os.environ.get('ORCHESTRATOR_LEARN_BACKEND')}")
    print(f"  self_questioning: {os.environ.get('ORCHESTRATOR_SELF_QUESTIONING_BACKEND')}")
    print(f"  train: {os.environ.get('ORCHESTRATOR_TRAIN_BACKEND')}")
    print(f"  scenario: {args.scenario}")
    print(f"  coaching_root: {ROOT}")
    print()

    results: dict[str, Any] = {}
    errors: list[str] = []

    if args.phase in ("preflight", "all"):
        print("─── Phase 1: Preflight ───")
        preflight_results = preflight(probe_cli=args.probe_cli)
        results["preflight"] = preflight_results
        print()
        if args.phase == "preflight":
            ok = _preflight_required_ok(preflight_results, probe_cli=args.probe_cli)
            print(f"preflight: {'PASS' if ok else 'FAIL'}")
            if args.json:
                print(json.dumps(results, indent=2))
            return 0 if ok else 1
        if not _preflight_required_ok(preflight_results, probe_cli=False):
            print("ABORT: preflight failed for a required backend.")
            return 1

    if args.phase in ("tick", "all"):
        print("─── Phase 2: Clock Tick ───")
        try:
            summary = run_clock_tick(args.scenario, keep_state=args.keep_state, dry_run=args.dry_run)
            results["tick"] = summary
            artifacts = collect_artifacts(ROOT)
            results["artifacts"] = artifacts
            tick_errors = assert_tick_artifacts(artifacts, dry_run=args.dry_run)
            if tick_errors:
                for err in tick_errors:
                    print(f"  ASSERT FAIL: {err}", file=sys.stderr)
                errors.extend(tick_errors)
        except Exception as exc:
            print(f"  FAIL: {exc}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            results["tick"] = {"status": "error", "error": str(exc)}
            if args.json:
                print(json.dumps(results, indent=2, default=str))
            return 1
        print()

    if args.phase in ("audit", "all"):
        print("─── Phase 3: Audit ───")
        if not ROOT.exists():
            print("  SKIP: coaching root not found (run --phase tick first)")
            return 1
        report = run_audit_phase(args.scenario)
        results["audit"] = report
        if report.get("status") != "PASS":
            errors.append(f"completeness audit status={report.get('status')!r}")
        if GOLDEN.is_file():
            golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
            golden_errors = _check_golden(report, golden)
            if golden_errors:
                for err in golden_errors:
                    print(f"  GOLDEN FAIL: {err}", file=sys.stderr)
                errors.extend(golden_errors)
        else:
            print(f"  WARNING: golden fixture missing: {GOLDEN}", file=sys.stderr)
        if args.write_golden:
            if report.get("status") != "PASS":
                errors.append("cannot --write-golden unless audit status=PASS")
            else:
                out = write_golden(report)
                print(f"  [golden] wrote {out}")
        print()

    status = "PASS" if not errors else "FAIL"
    tick = results.get("tick", {})
    checks: list[str] = []
    if tick:
        checks.append(f"C06={tick.get('sparse_self_questioning_suite_id') or 'MISSING'}")
        checks.append(f"C07={tick.get('batch_self_questioning_suite_id') or 'MISSING'}")
        checks.append(f"proceed={tick.get('batch_self_questioning_proceed')}")
        checks.append(f"promoted={tick.get('t_path_promoted')}")
    print(f"evolution_loop_clock_smoke: {status} ({', '.join(checks) if checks else 'preflight only'})")

    if args.json:
        print(json.dumps({"status": status, "errors": errors, **results}, indent=2, default=str))

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
