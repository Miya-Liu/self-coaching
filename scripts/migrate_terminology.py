#!/usr/bin/env python3
"""Terminology migration script (completed 2026-06-23).

Applied renames:
1. self-play / selfplay → self-questioning / self_questioning
2. Marked AERL-related code as on-hold (services not yet deployed)
3. Renamed services/LoRA → services/lora
4. Renamed training_client.py → trainer_client.py (consistency with trainer_http, trainer_rest_client)
5. Renamed SELF_QUESTIONING_SERVICE_API.md → docs/integration/pipeline-service-api.md

This script is kept for reference. Re-running it is safe (idempotent — skips already-renamed files).
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DRY_RUN = "--dry-run" in sys.argv


def log(msg: str) -> None:
    print(f"{'[DRY] ' if DRY_RUN else ''}  {msg}")


# ─── Phase 1: File/directory renames ─────────────────────────────────────────

FILE_RENAMES: list[tuple[str, str]] = [
    # self-play → self-questioning (source)
    ("modes/self-coaching/self-play", "modes/self-coaching/self-questioning"),
    ("modes/self-coaching/self_play_factory.py", "modes/self-coaching/self_questioning_factory.py"),
    ("mock-services/mock_self_play.py", "mock-services/mock_self_questioning.py"),
    ("services/adapters/selfplay_pipeline_adapter.py", "services/adapters/self_questioning_pipeline_adapter.py"),
    ("services/adapters/self_play_client_adapter.py", "services/adapters/self_questioning_client_adapter.py"),
    # self-play → self-questioning (scripts)
    ("scripts/pipeline_self_play_smoke.py", "scripts/pipeline_self_questioning_smoke.py"),
    ("scripts/mock-self-play-smoke.sh", "scripts/mock-self-questioning-smoke.sh"),
    # self-play → self-questioning (tests)
    ("tests/test_mock_self_play.py", "tests/test_mock_self_questioning.py"),
    ("tests/test_self_play_proceed_gating.py", "tests/test_self_questioning_proceed_gating.py"),
    ("tests/test_self_play_loop_wiring.py", "tests/test_self_questioning_loop_wiring.py"),
    ("tests/test_loop_self_play_sparse.py", "tests/test_loop_self_questioning_sparse.py"),
    ("tests/test_selfplay_pipeline_adapter.py", "tests/test_self_questioning_pipeline_adapter.py"),
    # self-play → self-questioning (docs)
    ("docs/project/self-play-integration-plan.md", "docs/project/self-questioning-integration-plan.md"),
    ("docs/project/self-play-pipeline-implementation.md", "docs/project/self-questioning-pipeline-implementation.md"),
    # LoRA → lora
    ("services/LoRA", "services/lora"),
    # training_client → trainer_client (consistency with trainer_rest_client, trainer_http)
    ("services/adapters/training_client.py", "services/adapters/trainer_client.py"),
    # Self-Questioning service API doc → cleaner location
    ("services/SELF_QUESTIONING_SERVICE_API.md", "docs/integration/pipeline-service-api.md"),
]


def rename_files() -> None:
    print("\n═══ Phase 1: File & directory renames ═══")
    for src_rel, dst_rel in FILE_RENAMES:
        src = REPO / src_rel
        dst = REPO / dst_rel
        if not src.exists():
            log(f"SKIP (not found): {src_rel}")
            continue
        # On Windows, case-only renames need an intermediate step
        if src.resolve() == dst.resolve():
            # Case-only rename (e.g. LoRA → lora on case-insensitive FS)
            tmp = src.with_name(src.name + "_tmp_rename")
            log(f"RENAME (case-change): {src_rel} → {dst_rel}")
            if not DRY_RUN:
                shutil.move(str(src), str(tmp))
                shutil.move(str(tmp), str(dst))
            continue
        if dst.exists():
            log(f"SKIP (dst exists): {dst_rel}")
            continue
        log(f"RENAME: {src_rel} → {dst_rel}")
        if not DRY_RUN:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))


# ─── Phase 2: Content replacements ──────────────────────────────────────────

# Order matters: longer patterns first to avoid partial matches
CONTENT_REPLACEMENTS: list[tuple[str, str]] = [
    # ── File/module references ──
    ("selfplay_pipeline_adapter", "self_questioning_pipeline_adapter"),
    ("self_play_client_adapter", "self_questioning_client_adapter"),
    ("self_play_factory", "self_questioning_factory"),
    ("mock_self_play", "mock_self_questioning"),
    ("pipeline_self_play_smoke", "pipeline_self_questioning_smoke"),
    ("mock-self-play-smoke", "mock-self-questioning-smoke"),
    # ── Class names ──
    ("SelfPlayPipelineEngine", "SelfQuestioningPipelineEngine"),
    ("PipelineSelfPlayClientAdapter", "PipelineSelfQuestioningClientAdapter"),
    ("MockSelfPlayEngine", "MockSelfQuestioningEngine"),
    ("_SelfPlayHandler", "_SelfQuestioningHandler"),
    # ── Function names ──
    ("build_self_play_pipeline_engine", "build_self_questioning_pipeline_engine"),
    ("build_self_play_engine", "build_self_questioning_engine"),
    ("run_batch_self_play", "run_batch_self_questioning"),
    ("run_suite_self_play", "run_suite_self_questioning"),
    ("self_play_via_http", "self_questioning_via_http"),
    ("generate_suite_via_http", "generate_suite_via_http"),  # keep — generic name
    ("_expect_sparse_self_play", "_expect_sparse_self_questioning"),
    ("_expect_batch_self_play", "_expect_batch_self_questioning"),
    ("_sparse_self_play_ok", "_sparse_self_questioning_ok"),
    ("_self_play_base_url", "_self_questioning_base_url"),
    # ── Config field names ──
    ("selfplay_backend", "self_questioning_backend"),
    ("self_play_factory", "self_questioning_factory"),
    ("self_play_url", "self_questioning_url"),
    # ── Env vars ──
    ("ORCHESTRATOR_SELFPLAY_BACKEND", "ORCHESTRATOR_SELF_QUESTIONING_BACKEND"),
    ("MOCK_SELF_PLAY_URL", "MOCK_SELF_QUESTIONING_URL"),
    ("MOCK_SELF_PLAY_PORT", "MOCK_SELF_QUESTIONING_PORT"),
    ("SELF_PLAY_BASE_URL", "SELF_QUESTIONING_BASE_URL"),
    # ── URL paths (OpenAPI / HTTP routes) ──
    ("/self-play/generate-suite", "/self-questioning/generate-suite"),
    ("/self-play/generate", "/self-questioning/generate"),
    # ── Data paths ──
    ("self_play_candidates.jsonl", "self_questioning_candidates.jsonl"),
    # ── Doc/prose (hyphenated form) ──
    ("self-play", "self-questioning"),
    # ── Remaining snake_case in prose or identifiers ──
    ("self_play", "self_questioning"),
    # ── training_client → trainer_client (import paths) ──
    ("from .training_client import", "from .trainer_client import"),
    ("training_client.py", "trainer_client.py"),
    ("training_client", "trainer_client"),
    # ── TrainingClient class name → TrainerClient ──
    ("TrainingClient", "TrainerClient"),
    # ── LoRA folder path ──
    ("services/LoRA", "services/lora"),
]

# Files/dirs to skip during content replacement
SKIP_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", ".ci-verify-hermes", ".ci-verify-install"}
SKIP_FILES = {"migrate_terminology.py"}
CONTENT_EXTENSIONS = {".py", ".md", ".yaml", ".yml", ".json", ".sh", ".ps1", ".toml", ".env", ".txt", ".cfg"}


def should_process(path: Path) -> bool:
    parts = set(path.relative_to(REPO).parts)
    if parts & SKIP_DIRS:
        return False
    if path.name in SKIP_FILES:
        return False
    if path.suffix not in CONTENT_EXTENSIONS:
        return False
    return True


def replace_content() -> None:
    print("\n═══ Phase 2: Content replacements ═══")
    changed_count = 0
    for root, dirs, files in os.walk(REPO):
        # Prune skipped dirs
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            fpath = Path(root) / fname
            if not should_process(fpath):
                continue
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            original = content
            for old, new in CONTENT_REPLACEMENTS:
                if old == new:
                    continue
                content = content.replace(old, new)

            if content != original:
                changed_count += 1
                rel = fpath.relative_to(REPO)
                log(f"MODIFIED: {rel}")
                if not DRY_RUN:
                    fpath.write_text(content, encoding="utf-8")

    log(f"Total files modified: {changed_count}")


# ─── Phase 3: AERL on-hold markers ──────────────────────────────────────────

AERL_ON_HOLD_HEADER = '''# ⚠️ ON-HOLD: AERL services not yet deployed
# This module depends on the AERL training platform which is not available
# in the current deployment. Kept for future integration when AERL is live.
# Status: ON-HOLD — do not remove, do not invest further until AERL deploys.

'''

AERL_FILES = [
    "services/adapters/aerl_client.py",
    "mock-services/mock_aerl.py",
    "scripts/mock-aerl-smoke.sh",
    "scripts/mock-aerl-extended-smoke.sh",
    "tests/test_mock_aerl.py",
    "tests/test_aerl_adapter.py",
    "tests/test_aerl_mock_extended.py",
]


def mark_aerl_on_hold() -> None:
    print("\n═══ Phase 3: Mark AERL as on-hold ═══")
    for rel in AERL_FILES:
        fpath = REPO / rel
        if not fpath.exists():
            log(f"SKIP (not found): {rel}")
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
        except OSError:
            continue
        if "ON-HOLD" in content:
            log(f"SKIP (already marked): {rel}")
            continue
        log(f"MARK ON-HOLD: {rel}")
        if not DRY_RUN:
            # For .sh files use different comment syntax
            if fpath.suffix == ".sh":
                header = AERL_ON_HOLD_HEADER  # # comments work for both
            else:
                header = AERL_ON_HOLD_HEADER
            fpath.write_text(header + content, encoding="utf-8")


# ─── Phase 4: Update __init__.py exports ─────────────────────────────────────

def update_adapters_init() -> None:
    print("\n═══ Phase 4: Update services/adapters/__init__.py ═══")
    init_path = REPO / "services" / "adapters" / "__init__.py"
    if not init_path.exists():
        log("SKIP: __init__.py not found")
        return
    # Content replacements already handled the imports.
    # Just verify it looks right.
    content = init_path.read_text(encoding="utf-8")
    if "self_questioning_pipeline_adapter" in content:
        log("OK: __init__.py already updated by Phase 2")
    else:
        log("WARNING: __init__.py may need manual review")


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"Terminology migration {'(DRY RUN)' if DRY_RUN else ''}")
    print(f"Repo root: {REPO}")
    rename_files()
    replace_content()
    mark_aerl_on_hold()
    update_adapters_init()
    print("\n═══ Done ═══")
    if DRY_RUN:
        print("Re-run without --dry-run to apply changes.")
    else:
        print("Changes applied. Run tests: pytest tests/ -x --tb=short")


if __name__ == "__main__":
    main()
