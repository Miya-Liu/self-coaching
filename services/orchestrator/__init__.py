# SPDX-License-Identifier: MIT
"""Evolution engine (T3). See docs/design/pipelines.md."""

from .eval_metrics import EvalMetrics, normalize_from_mock_eval
from .drop_detector import DropCheckResult, check_drop

__all__ = [
    "EvalMetrics",
    "normalize_from_mock_eval",
    "DropCheckResult",
    "check_drop",
]
