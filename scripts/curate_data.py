#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Curate self-play trajectories into train/dev/holdout JSONL splits (M3 stub).

Reads trajectory or candidate records from JSONL, filters privacy-checked rows,
deduplicates by case_id, and writes split files under a coaching root.

Usage:
    python scripts/curate_data.py \\
        --input mock-services/demo-run-cli/.self-coaching/curated/train.jsonl \\
        --out-dir /path/to/coaching-root/.self-coaching/curated \\
        --require-privacy-checked
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no}: expected JSON object")
        rows.append(row)
    return rows


def _row_key(row: dict[str, Any]) -> str:
    case_id = row.get("case_id") or row.get("id")
    if case_id:
        return str(case_id)
    payload = json.dumps(row, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _privacy_checked(row: dict[str, Any]) -> bool:
    labels = row.get("labels") or {}
    if isinstance(labels, dict) and labels.get("privacy_checked") is True:
        return True
    return row.get("privacy_checked") is True


def _split_rows(
    rows: list[dict[str, Any]],
    *,
    train_ratio: float,
    dev_ratio: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if train_ratio <= 0 or dev_ratio < 0 or train_ratio + dev_ratio >= 1:
        raise ValueError("ratios must satisfy 0 < train_ratio and train_ratio + dev_ratio < 1")
    holdout_ratio = 1.0 - train_ratio - dev_ratio
    n = len(rows)
    train_end = int(n * train_ratio)
    dev_end = train_end + int(n * dev_ratio)
    # Stable order: input file order after dedupe.
    train = rows[:train_end]
    dev = rows[train_end:dev_end]
    holdout = rows[dev_end:]
    if not holdout and holdout_ratio > 0 and n > 1:
        holdout = [rows[-1]]
        if len(dev) > 0:
            dev = dev[:-1]
        elif len(train) > 1:
            train = train[:-1]
    return train, dev, holdout


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def curate(
    *,
    input_path: Path,
    out_dir: Path,
    require_privacy_checked: bool,
    train_ratio: float,
    dev_ratio: float,
) -> dict[str, Any]:
    raw = _load_jsonl(input_path)
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    skipped_privacy = 0
    skipped_dup = 0

    for row in raw:
        if require_privacy_checked and not _privacy_checked(row):
            skipped_privacy += 1
            continue
        key = _row_key(row)
        if key in seen:
            skipped_dup += 1
            continue
        seen.add(key)
        kept.append(row)

    train, dev, holdout = _split_rows(kept, train_ratio=train_ratio, dev_ratio=dev_ratio)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "train": out_dir / "train.jsonl",
        "validation": out_dir / "validation.jsonl",
        "holdout": out_dir / "holdout.jsonl",
    }
    _write_jsonl(paths["train"], train)
    _write_jsonl(paths["validation"], dev)
    _write_jsonl(paths["holdout"], holdout)

    manifest = {
        "status": "ok",
        "input": str(input_path),
        "out_dir": str(out_dir),
        "counts": {
            "input": len(raw),
            "kept": len(kept),
            "skipped_privacy": skipped_privacy,
            "skipped_duplicate": skipped_dup,
            "train": len(train),
            "validation": len(dev),
            "holdout": len(holdout),
        },
        "paths": {k: str(v) for k, v in paths.items()},
        "require_privacy_checked": require_privacy_checked,
        "split_ratios": {"train": train_ratio, "dev": dev_ratio},
    }
    manifest_path = out_dir / "curation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Curate JSONL trajectories into train/dev/holdout splits.")
    parser.add_argument("--input", type=Path, required=True, help="Source JSONL (trajectories or candidates)")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for split JSONL files")
    parser.add_argument(
        "--require-privacy-checked",
        action="store_true",
        help="Drop rows without labels.privacy_checked=true",
    )
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2

    try:
        manifest = curate(
            input_path=args.input,
            out_dir=args.out_dir,
            require_privacy_checked=args.require_privacy_checked,
            train_ratio=args.train_ratio,
            dev_ratio=args.dev_ratio,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
