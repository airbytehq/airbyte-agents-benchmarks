"""Runner — dispatches enabled paths across each scenario."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path as FSPath
from typing import Iterable

from agent_bench.config import LiveConfig
from agent_bench.metrics import BenchmarkResult
from agent_bench.paths.agent_mcp import AgentMCPPath
from agent_bench.paths.agent_sdk import AgentSDKPath
from agent_bench.paths.native_mcp import NativeMCPPath
from agent_bench.scenarios.loader import Scenario, load_scenario


@dataclass
class Cell:
    """One (scenario, path) bench result."""

    scenario: Scenario
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

    def for_connector(self, connector: str) -> list[Cell]:
        return [c for c in self.cells if c.scenario.connector == connector]


def _build_paths(
    path_slugs: Iterable[str],
    config: LiveConfig,
    connector_name: str,
    artifacts_dir: FSPath,
    scenario_name: str,
) -> list:
    paths = []
    scenario_dir = artifacts_dir / f"{scenario_name}-scenario"
    for slug in path_slugs:
        if slug == "agent-sdk":
            paths.append(AgentSDKPath(config, connector_name))
        elif slug == "agent-mcp":
            paths.append(AgentMCPPath(config, scenario_dir / "agent-mcp"))
        elif slug == "native-mcp":
            paths.append(NativeMCPPath(scenario_dir / "native-mcp"))
        else:
            raise ValueError(f"Unknown path slug: {slug}")
    return paths


async def run_scenario(
    scenario: Scenario,
    path_slugs: list[str],
    config: LiveConfig,
    artifacts_dir: FSPath,
    on_cell: callable = None,
) -> list[Cell]:
    cells: list[Cell] = []
    paths = _build_paths(path_slugs, config, scenario.connector, artifacts_dir, scenario.name)
    task = scenario.task

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
            scenario=scenario,
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
    artifacts_dir: FSPath,
    on_cell: callable = None,
) -> RunReport:
    report = RunReport(
        requested_scenarios=list(scenario_names),
        requested_paths=list(path_slugs),
    )
    required_connectors = list({load_scenario(n).connector for n in scenario_names})
    config = LiveConfig.from_env(required_connectors=required_connectors)
    for name in scenario_names:
        sc = load_scenario(name)
        cells = await run_scenario(sc, path_slugs, config, artifacts_dir, on_cell)
        report.cells.extend(cells)
    return report
