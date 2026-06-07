# SPDX-License-Identifier: MIT
"""Load and validate coach mode supervision registry (agents.yaml)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - optional at runtime
    yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class AgentEvalConfig:
    suite_id_canary: str
    suite_id_holdout: str | None = None
    interval: str | None = None


@dataclass(frozen=True)
class AgentImprovementConfig:
    train_pipeline: str = "sft"
    min_cases_for_model_path: int = 100


@dataclass(frozen=True)
class SupervisedAgent:
    id: str
    coaching_root: Path
    model: str | None = None
    prefer_skill_first: bool = True
    eval: AgentEvalConfig | None = None
    improvement: AgentImprovementConfig | None = None


class RegistryError(ValueError):
    """Invalid or missing supervision registry."""


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistryError(f"{field} must be a mapping")
    return value


def _parse_agent(raw: dict[str, Any]) -> SupervisedAgent:
    agent_id = raw.get("id")
    if not agent_id or not isinstance(agent_id, str):
        raise RegistryError("each agent requires a non-empty string id")

    coaching_root = raw.get("coaching_root")
    if not coaching_root or not isinstance(coaching_root, str):
        raise RegistryError(f"agent {agent_id!r}: coaching_root is required")

    eval_cfg: AgentEvalConfig | None = None
    if "eval" in raw and raw["eval"] is not None:
        ev = _require_mapping(raw["eval"], f"agent {agent_id}.eval")
        canary = ev.get("suite_id_canary")
        if not canary or not isinstance(canary, str):
            raise RegistryError(f"agent {agent_id!r}: eval.suite_id_canary is required")
        holdout = ev.get("suite_id_holdout")
        if holdout is not None and not isinstance(holdout, str):
            raise RegistryError(f"agent {agent_id!r}: eval.suite_id_holdout must be a string")
        interval = ev.get("interval")
        if interval is not None and not isinstance(interval, str):
            raise RegistryError(f"agent {agent_id!r}: eval.interval must be a string")
        eval_cfg = AgentEvalConfig(
            suite_id_canary=canary,
            suite_id_holdout=holdout,
            interval=interval,
        )

    improvement_cfg: AgentImprovementConfig | None = None
    if "improvement" in raw and raw["improvement"] is not None:
        imp = _require_mapping(raw["improvement"], f"agent {agent_id}.improvement")
        pipeline = imp.get("train_pipeline", "sft")
        if not isinstance(pipeline, str):
            raise RegistryError(f"agent {agent_id!r}: improvement.train_pipeline must be a string")
        min_cases = imp.get("min_cases_for_model_path", 100)
        if not isinstance(min_cases, int) or min_cases < 0:
            raise RegistryError(f"agent {agent_id!r}: improvement.min_cases_for_model_path must be a non-negative int")
        improvement_cfg = AgentImprovementConfig(
            train_pipeline=pipeline,
            min_cases_for_model_path=min_cases,
        )

    model = raw.get("model")
    if model is not None and not isinstance(model, str):
        raise RegistryError(f"agent {agent_id!r}: model must be a string")

    prefer_skill_first = raw.get("prefer_skill_first", True)
    if not isinstance(prefer_skill_first, bool):
        raise RegistryError(f"agent {agent_id!r}: prefer_skill_first must be a boolean")

    return SupervisedAgent(
        id=agent_id,
        coaching_root=Path(coaching_root),
        model=model,
        prefer_skill_first=prefer_skill_first,
        eval=eval_cfg,
        improvement=improvement_cfg,
    )


def parse_registry(data: dict[str, Any]) -> list[SupervisedAgent]:
    """Parse a registry document (from YAML or JSON)."""
    agents_raw = data.get("agents", [])
    if not isinstance(agents_raw, list):
        raise RegistryError("agents must be a list")

    agents = [_parse_agent(_require_mapping(item, "agent entry")) for item in agents_raw]
    seen: set[str] = set()
    for agent in agents:
        if agent.id in seen:
            raise RegistryError(f"duplicate agent id: {agent.id!r}")
        seen.add(agent.id)
    return agents


def _load_document(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    elif yaml is not None:
        data = yaml.safe_load(text)
    else:
        raise RegistryError(
            f"PyYAML is required to load {path.name}; use a .json registry or pip install pyyaml"
        )
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RegistryError("registry root must be a mapping")
    return data


def load_registry(path: str | Path) -> list[SupervisedAgent]:
    """Load agents from a YAML or JSON registry file."""
    registry_path = Path(path)
    if not registry_path.is_file():
        raise RegistryError(f"registry not found: {registry_path}")
    return parse_registry(_load_document(registry_path))


def default_registry_path() -> Path:
    """Prefer agents.yaml beside this module; fall back to agents.example.yaml."""
    base = Path(__file__).resolve().parent
    preferred = base / "agents.yaml"
    if preferred.is_file():
        return preferred
    return base / "agents.example.yaml"
