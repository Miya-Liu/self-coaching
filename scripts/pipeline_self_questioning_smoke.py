#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Smoke test: pipeline self-questioning adapter (dry_run by default).

Usage:
  PIPELINE_DRY_RUN=1 python scripts/pipeline_self_questioning_smoke.py
  PIPELINE_INTEGRATION_TESTS=1 PIPELINE_SERVICE_URL=http://host:8001 python scripts/pipeline_self_questioning_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.adapters.self_questioning_pipeline_adapter import build_self_questioning_pipeline_engine  # noqa: E402


def main() -> int:
    os.environ.setdefault("PIPELINE_DRY_RUN", "1")
    base = os.environ.get("PIPELINE_SERVICE_URL")
    if not base:
        print("pipeline_self_questioning_smoke: SKIP — PIPELINE_SERVICE_URL not set", file=sys.stderr)
        return 0
    engine = build_self_questioning_pipeline_engine(base)

    health = engine._client.health()
    print(f"health: {health.get('status')}")

    batch = engine.generate_batch(coaching_root=REPO_ROOT / "mock-services" / "ci-pipeline-smoke", n=1)
    print("batch:", json.dumps(batch, indent=2, sort_keys=True))
    if not batch.get("proceed"):
        print("pipeline_self_questioning_smoke: FAIL batch did not proceed", file=sys.stderr)
        return 1

    suite = engine.generate_suite(
        coaching_root=REPO_ROOT / "mock-services" / "ci-pipeline-smoke",
        n_variants=1,
        user_query="smoke",
    )
    print("suite:", json.dumps(suite, indent=2, sort_keys=True))
    if not suite.get("proceed"):
        print("pipeline_self_questioning_smoke: FAIL suite did not proceed", file=sys.stderr)
        return 1

    print("pipeline_self_questioning_smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
