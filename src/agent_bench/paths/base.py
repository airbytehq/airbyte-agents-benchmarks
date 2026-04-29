"""Protocol for benchmark paths in the new three-path model."""

from __future__ import annotations

from typing import AsyncIterator, Protocol

from agent_bench.metrics import BenchmarkResult, StepResult
from agent_bench.scenarios.loader import Scenario, Task


class BenchmarkPath(Protocol):
    """Each path runs one task at a time and yields step-wise progress.

    A path is bound to one connector's scope at construction (auth + connector
    instance ID). The runner iterates over tasks and calls `run_task`.
    """

    name: str  # human-readable ("REST Baseline (via SDK)" | "Agent MCP" | "Native MCP")
    short_name: str  # CLI slug ("agent-sdk" | "agent-mcp" | "native-mcp")

    async def run_task(
        self, task: Task, scenario: Scenario
    ) -> AsyncIterator[tuple[StepResult, BenchmarkResult]]:
        """Yield (step_just_completed, running_total) after each step."""
        ...

    async def close(self) -> None:
        """Release any HTTP clients / connector handles."""
        ...
