"""YAML scenario loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


SCENARIOS_DIR = Path(__file__).parent


Action = Literal["search", "get", "list"]


@dataclass
class Task:
    """A head-to-head task across all paths."""

    label: str
    action: Action
    entity: str
    metric_focus: str  # "narrow_context" | "single_record_fetch" | "bulk_list"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    """A loaded benchmark scenario."""

    name: str
    title: str
    connector: str  # slack | linear | granola
    connector_id_env: str  # env var name holding the connector instance UUID
    task: Task
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

    task_data = data["task"]
    task = Task(
        label=task_data["label"],
        action=task_data["action"],
        entity=task_data["entity"],
        metric_focus=task_data["metric_focus"],
        params=task_data.get("params", {}),
    )
    return Scenario(
        name=data["name"],
        title=data["title"],
        connector=data["connector"],
        connector_id_env=data["connector_id_env"],
        task=task,
        description=data.get("description", ""),
    )


def list_scenarios() -> list[str]:
    """List all available scenario names."""
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))


def scenarios_for_connector(connector: str) -> list[str]:
    """List scenario names that belong to a given connector."""
    return [
        name for name in list_scenarios()
        if name.startswith(f"{connector}-")
    ]
