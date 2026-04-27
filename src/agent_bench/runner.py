"""Runner — dispatches enabled paths across the tasks of each scenario."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path as FSPath
from typing import Iterable

from agent_bench.config import LiveConfig
from agent_bench.metrics import BenchmarkResult
from agent_bench.paths.agent_engine_mcp import AgentEngineMCPPath
from agent_bench.paths.agent_engine_sdk import AgentEngineSDKPath
from agent_bench.paths.claude_mcp import ClaudeMCPPath
from agent_bench.scenarios.loader import Scenario, Task, load_scenario


@dataclass
class Cell:
    """One (scenario, task, path) bench result."""

    scenario: Scenario
    task: Task
    path_name: str
    path_short: str
    result: BenchmarkResult


@dataclass
class RunReport:
    """All cells from a full run."""

    cells: list[Cell] = field(default_factory=list)
    requested_scenarios: list[str] = field(default_factory=list)
    requested_paths: list[str] = field(default_factory=list)

    def for_scenario(self, name: str) -> list[Cell]:
        return [c for c in self.cells if c.scenario.name == name]

    def for_task(self, scenario_name: str, task_label: str) -> list[Cell]:
        return [
            c for c in self.cells
            if c.scenario.name == scenario_name and c.task.label == task_label
        ]


def _build_paths(
    path_slugs: Iterable[str],
    config: LiveConfig,
    connector_name: str,
    recordings_dir: FSPath,
) -> list:
    paths = []
    for slug in path_slugs:
        if slug == "ae-sdk":
            paths.append(AgentEngineSDKPath(config, connector_name))
        elif slug == "ae-mcp":
            paths.append(AgentEngineMCPPath(config, recordings_dir / "ae-mcp"))
        elif slug == "claude":
            paths.append(ClaudeMCPPath(recordings_dir / "claude"))
        else:
            raise ValueError(f"Unknown path slug: {slug}")
    return paths


async def run_scenario(
    scenario: Scenario,
    path_slugs: list[str],
    config: LiveConfig,
    recordings_dir: FSPath,
    on_cell: callable = None,
) -> list[Cell]:
    cells: list[Cell] = []
    paths = _build_paths(path_slugs, config, scenario.connector, recordings_dir)

    for task in scenario.tasks:
        async def _run_path(path):
            result = None
            async for _step, res in path.run_task(task, scenario):
                result = res
            return path, result

        try:
            pairs = await asyncio.gather(
                *[_run_path(p) for p in paths], return_exceptions=True
            )
        except Exception as exc:  # noqa: BLE001
            pairs = [exc] * len(paths)

        for idx, outcome in enumerate(pairs):
            path = paths[idx]
            if isinstance(outcome, Exception):
                result = BenchmarkResult(path_name=path.name)
                result.status = "error"
                result.error = f"{type(outcome).__name__}: {outcome}"
            else:
                _, result = outcome
                if result is None:
                    result = BenchmarkResult(path_name=path.name)
                    result.status = "error"
                    result.error = "No result yielded"
            cell = Cell(
                scenario=scenario, task=task,
                path_name=path.name, path_short=path.short_name,
                result=result,
            )
            cells.append(cell)
            if on_cell:
                on_cell(cell)

    for p in paths:
        try:
            await p.close()
        except Exception:  # noqa: BLE001
            pass

    return cells


async def run_all(
    scenario_names: list[str],
    path_slugs: list[str],
    recordings_dir: FSPath,
    on_cell: callable = None,
) -> RunReport:
    report = RunReport(
        requested_scenarios=list(scenario_names),
        requested_paths=list(path_slugs),
    )
    required_connectors = [load_scenario(n).connector for n in scenario_names]
    # Only the SDK path requires live creds; if ae-sdk isn't in path_slugs,
    # we can run with an empty config, but config is cheap so always load.
    config = LiveConfig.from_env(required_connectors=required_connectors)
    for name in scenario_names:
        sc = load_scenario(name)
        cells = await run_scenario(sc, path_slugs, config, recordings_dir, on_cell)
        report.cells.extend(cells)
    return report
