"""YAML scenario loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


SCENARIOS_DIR = Path(__file__).parent


Action = Literal["search", "get", "list"]


@dataclass
class Task:
    """A single head-to-head task across all paths."""

    label: str
    action: Action
    entity: str
    metric_focus: str  # "narrow_context" | "single_record_fetch" | "bulk_list"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    """A loaded benchmark scenario (one connector, N tasks)."""

    name: str
    title: str
    connector: str  # slack | linear | granola
    connector_id_env: str  # env var name holding the connector instance UUID
    tasks: list[Task] = field(default_factory=list)
    description: str = ""


def load_scenario(name: str) -> Scenario:
    """Load a scenario by name from the scenarios directory."""
    import yaml

    path = SCENARIOS_DIR / f"{name}.yaml"
    if not path.exists():
        available = list_scenarios()
        raise FileNotFoundError(
            f"Scenario '{name}' not found. Available: {', '.join(available)}"
        )
    with open(path) as f:
        data = yaml.safe_load(f)
    tasks = [
        Task(
            label=t["label"],
            action=t["action"],
            entity=t["entity"],
            metric_focus=t["metric_focus"],
            params=t.get("params", {}),
        )
        for t in data["tasks"]
    ]
    return Scenario(
        name=data["name"],
        title=data["title"],
        connector=data["connector"],
        connector_id_env=data["connector_id_env"],
        tasks=tasks,
        description=data.get("description", ""),
    )


def list_scenarios() -> list[str]:
    """List all available scenario names."""
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))
