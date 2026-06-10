#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Backward-compatible shim — prefer ``python -m self_coaching.demo``."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SC = _ROOT / "modes" / "self-coaching"
if str(_SC) not in sys.path:
    sys.path.insert(0, str(_SC))

try:
    from self_coaching.demo import main  # type: ignore[import-not-found]
except ImportError:
    from demo import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
