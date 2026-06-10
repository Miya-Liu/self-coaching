# SPDX-License-Identifier: MIT
"""``python -m self_coaching`` — mock loop demo entry point."""
from __future__ import annotations

try:
    from .demo import main
except ImportError:
    from demo import main  # type: ignore[no-redef]

if __name__ == "__main__":
    raise SystemExit(main())
