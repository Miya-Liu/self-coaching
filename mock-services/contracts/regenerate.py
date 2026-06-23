#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Regenerate `mock_service_contract.json` from `openapi.yaml`.

The JSON file is a compact summary used by the skill itself; the YAML is the
formal source of truth used by real-service implementers.

Run from the repo root:
    python mock-services/contracts/regenerate.py

CI invokes this and asserts no diff to enforce that both files stay in sync.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parent
OPENAPI = CONTRACTS_DIR / "openapi.yaml"
JSON_OUT = CONTRACTS_DIR / "mock_service_contract.json"


def _load_yaml(text: str) -> dict:
    """Minimal YAML loader for the structure we control.

    We avoid pulling in PyYAML to keep mock-services stdlib-only. This is NOT
    a general YAML parser — it handles only the subset our openapi.yaml uses.
    """
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        # Fallback path: parse only what we need (info.version, top-level paths
        # and method tuples). Good enough for the regenerate use case.
        return _parse_minimal(text)


def _parse_minimal(text: str) -> dict:
    """Extract just info.version, paths (with methods), and tags."""
    out: dict = {"info": {}, "paths": {}, "tags": []}
    in_info = False
    in_paths = False
    in_tags = False
    current_path: str | None = None
    info_indent = -1
    paths_indent = -1
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if indent == 0 and stripped.startswith("info:"):
            in_info, in_paths, in_tags = True, False, False
            info_indent = -1
            continue
        if indent == 0 and stripped.startswith("paths:"):
            in_info, in_paths, in_tags = False, True, False
            paths_indent = -1
            continue
        if indent == 0 and stripped.startswith("tags:"):
            in_info, in_paths, in_tags = False, False, True
            continue
        if indent == 0 and not stripped.startswith("-"):
            in_info = in_paths = in_tags = False
            continue

        if in_info:
            m = re.match(r"(\w+):\s*(.*)$", stripped)
            if m and indent <= (info_indent if info_indent >= 0 else 99):
                info_indent = indent
                key, val = m.group(1), m.group(2).strip()
                if val:
                    out["info"][key] = val.strip('"').strip("'")
        elif in_paths:
            if stripped.startswith("/"):
                m = re.match(r"(/\S+):\s*$", stripped)
                if m:
                    current_path = m.group(1)
                    out["paths"][current_path] = []
                    paths_indent = indent
            elif current_path and indent > paths_indent:
                m = re.match(r"(get|post|put|delete|patch):\s*$", stripped)
                if m:
                    out["paths"][current_path].append(m.group(1).upper())
        elif in_tags:
            m = re.match(r"-\s*name:\s*(\S+)", stripped)
            if m:
                out["tags"].append(m.group(1))
    return out


def build_compact_contract(spec: dict) -> dict:
    """Convert the OpenAPI spec into the compact JSON shape consumed by the skill."""
    endpoints = []
    paths = spec.get("paths", {})
    for path in sorted(paths.keys()):
        methods = paths[path]
        # Both shapes supported: minimal parser returns list of method strings;
        # full yaml.safe_load returns dict-of-method -> operation object.
        if isinstance(methods, dict):
            method_iter = sorted(methods.keys())
        else:
            method_iter = sorted(set(m.upper() for m in methods))
        for m in method_iter:
            endpoints.append({"method": m.upper(), "path": path})

    version = spec.get("info", {}).get("version", "1.0.0")
    # Compact: keep version as integer-major when possible (legacy `version: 1`).
    try:
        major = int(version.split(".")[0])
    except (ValueError, AttributeError):
        major = 1

    return {
        "artifacts": {
            "eval_cases": ".self-coaching/cases/eval_cases.jsonl",
            "eval_reports": ".self-coaching/reports/eval_runs/<run_id>/report.json",
            "learning_events": ".self-coaching/events/learning_events.jsonl",
            "self_questioning_candidates": ".self-coaching/cases/self_questioning_candidates.jsonl",
            "summary": ".self-coaching/manifests/mock_pipeline_summary.json",
            "train_split": ".self-coaching/curated/train.jsonl",
            "training_manifest": ".self-coaching/manifests/training_run_manifest.json",
        },
        "interfaces": {
            "cli": {
                "commands": ["init", "learn", "self-questioning", "evaluate", "train", "run-all", "serve"]
            },
            "http": {
                "base_url": "http://127.0.0.1:8765",
                "endpoints": endpoints,
                "openapi": "openapi.yaml",
            },
            "python_module": {
                "module": "mock_self_coaching",
                "functions": ["init", "learn", "self_questioning", "evaluate", "train", "run_all"],
            },
        },
        "openapi_version": version,
        "purpose": "Local deterministic mock interfaces for testing the self-coaching learning -> self-questioning -> evaluation -> training pipeline without real external services.",
        "service": "mock-self-coaching",
        "version": major,
    }


def main() -> int:
    if not OPENAPI.is_file():
        print(f"openapi.yaml not found at {OPENAPI}", file=sys.stderr)
        return 2
    spec = _load_yaml(OPENAPI.read_text(encoding="utf-8"))
    contract = build_compact_contract(spec)
    new_text = json.dumps(contract, indent=2, sort_keys=True) + "\n"

    old_text = JSON_OUT.read_text(encoding="utf-8") if JSON_OUT.is_file() else ""
    if old_text == new_text:
        print(f"{JSON_OUT.name}: up to date")
        return 0

    if "--check" in sys.argv:
        print(f"DRIFT: {JSON_OUT.name} is out of sync with openapi.yaml", file=sys.stderr)
        print("Run: python mock-services/contracts/regenerate.py", file=sys.stderr)
        return 1

    JSON_OUT.write_text(new_text, encoding="utf-8")
    print(f"{JSON_OUT.name}: regenerated ({len(new_text)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
