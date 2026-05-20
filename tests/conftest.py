# SPDX-License-Identifier: MIT
"""Make `mock-services` importable from tests without installing the package."""

import sys
from pathlib import Path

# Repo root = parent of tests/
REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_SERVICES = REPO_ROOT / "mock-services"

if str(MOCK_SERVICES) not in sys.path:
    sys.path.insert(0, str(MOCK_SERVICES))
