"""YAML scenario loader.

Supports two scenario formats:

1. **Legacy** (single-task): Uses a `task` block with `action`, `entity`,
   `params`. The agent-mcp and native-mcp tool_calls are derived at
   runtime by the path classes.

2. **Choreographed** (multi-step): Uses a `paths` block where each path
   declares an ordered list of `tool_calls` with `server`, `tool`, and
   `args`. Supports cross-connector workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


SCENARIOS_DIR = Path(__file__).parent


Action = Literal["search", "get", "list", "list-all", "context_store_search"]


@dataclass
class ToolCall:
    """A single MCP tool invocation in a choreographed scenario."""

    server: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    connector_id_env: str | None = None
    paginate_to_end: bool = False


@dataclass
class PathSpec:
    """The declared execution plan for one path (e.g. agent-mcp)."""

    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class Task:
    """A head-to-head task across all paths (legacy format)."""

    label: str
    action: Action
    entity: str
    metric_focus: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    """A loaded benchmark scenario."""

    name: str
    title: str
    connector: str
    connector_id_env: str
    description: str = ""
    annotations: dict[str, str] = field(default_factory=dict)
    is_comparable: bool = True
    faux_prompt: str = ""
    # Legacy single-task format
    task: Task | None = None
    # New choreographed format
    paths: dict[str, PathSpec] | None = None

    @property
    def is_choreographed(self) -> bool:
        return self.paths is not None

    @property
    def inferred_action(self) -> str:
        """Best-effort action label, derived from task or scenario name."""
        if self.task:
            return self.task.action
        for suffix in ("get", "list-all", "list", "search"):
            if self.name.endswith(f"-{suffix}"):
                return suffix
        return "multi-step"

    @property
    def inferred_entity(self) -> str:
        """Best-effort entity label, derived from task or first tool call."""
        if self.task:
            return self.task.entity
        if self.paths:
            first_path = self.paths.get("agent-mcp") or next(iter(self.paths.values()), None)
            if first_path and first_path.tool_calls:
                entity = first_path.tool_calls[0].args.get("entity")
                if entity:
                    return entity
        return self.connector

    @property
    def connectors(self) -> list[str]:
        """Real connectors referenced by this scenario (those with env vars)."""
        if not self.is_choreographed:
            return [self.connector]
        seen: list[str] = []
        for path_spec in self.paths.values():
            for tc in path_spec.tool_calls:
                if tc.connector_id_env:
                    name = tc.connector_id_env.removesuffix("_CONNECTOR_ID").lower()
                    if name not in seen:
                        seen.append(name)
        return seen or [self.connector]


def _parse_tool_call(data: dict[str, Any]) -> ToolCall:
    return ToolCall(
        server=data["server"],
        tool=data["tool"],
        args=data.get("args", {}),
        connector_id_env=data.get("connector_id_env"),
        paginate_to_end=data.get("paginate_to_end", False),
    )


def _parse_path_spec(data: dict[str, Any]) -> PathSpec:
    return PathSpec(
        tool_calls=[_parse_tool_call(tc) for tc in data.get("tool_calls", [])],
    )


def load_scenario(name: str) -> Scenario:
    """Load a scenario by name from the scenarios directory."""
    path = SCENARIOS_DIR / f"{name}.yaml"
    if not path.exists():
        available = list_scenarios()
        raise FileNotFoundError(
            f"Scenario '{name}' not found. Available: {', '.join(available)}"
        )
    with open(path) as f:
        data = yaml.safe_load(f)

    task = None
    paths = None

    if "task" in data:
        task_data = data["task"]
        task = Task(
            label=task_data["label"],
            action=task_data["action"],
            entity=task_data["entity"],
            metric_focus=task_data["metric_focus"],
            params=task_data.get("params", {}),
        )

    if "paths" in data:
        paths = {
            name: _parse_path_spec(spec)
            for name, spec in data["paths"].items()
        }

    return Scenario(
        name=data["name"],
        title=data["title"],
        connector=data["connector"],
        connector_id_env=data.get("connector_id_env", ""),
        task=task,
        description=data.get("description", ""),
        annotations=data.get("annotations", {}),
        is_comparable=data.get("is_comparable", True),
        faux_prompt=data.get("faux_prompt", ""),
        paths=paths,
    )


def list_scenarios() -> list[str]:
    """List all available scenario names."""
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))


def scenarios_for_connector(connector: str) -> list[str]:
    """List scenario names that belong to a given connector."""
    return [
        name for name in list_scenarios()
        if load_scenario(name).connector == connector
    ]
