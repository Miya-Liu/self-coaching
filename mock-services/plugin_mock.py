"""Mock self-coaching plugin module.

This file demonstrates a tiny importable module interface that another agent/tool/plugin could call
instead of shelling out to the CLI. It wraps mock_self_coaching.py functions and keeps the same artifact
contracts.
"""
from __future__ import annotations
from pathlib import Path

try:  # package-style import
    from .mock_self_coaching import init, learn, self_play, evaluate, train, run_all
except ImportError:  # direct path/module import during local smoke tests
    from mock_self_coaching import init, learn, self_play, evaluate, train, run_all


def run_demo(root: str | Path) -> dict:
    """Run the full mock self-coaching pipeline and return a summary dict."""
    return run_all(Path(root), capability="tool_use", pipeline="sft")


def register() -> dict:
    """Pseudo plugin registration metadata for documentation/testing."""
    return {
        "name": "mock-self-coaching",
        "version": "0.1.0",
        "interfaces": ["python_module", "cli", "http"],
        "capabilities": ["learning", "self_play", "evaluation", "training"],
    }
