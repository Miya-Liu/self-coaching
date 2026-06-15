# SPDX-License-Identifier: MIT
"""CI wrapper for autonomous clock loop smoke."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_clock_loop_smoke() -> None:
    root = Path(__file__).resolve().parent.parent
    script = root / "scripts" / "clock_loop_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"clock_loop_smoke failed (exit {result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
