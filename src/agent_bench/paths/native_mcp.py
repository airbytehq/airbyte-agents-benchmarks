"""Path A: Native MCP servers.

These MCP tools are provided by each SaaS vendor and invoked via an MCP
client (e.g. Claude Code or Cursor), not by Python code. So this path is
built around a "record once, replay" model:

  1. Call `tool_specs(task, scenario)` to get the exact tool+args the
     benchmark would invoke for a task.
  2. Execute those tool calls from an MCP client (driver/harness), saving
     `{tool, args, wall_clock_ms, response}` to a per-task JSON file.
  3. `run_task` reads the recording and computes StepResult metrics.

Tool surface notes:
  - Slack (hosted MCP at `mcp.slack.com/mcp`): exposes search-style tools
    only. Channel/user search use `slack_search_channels` /
    `slack_search_users` (20 results/page max). No get-by-ID; channel
    "get" falls back to search-then-filter.
  - Linear: clean direct mappings for search and get.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path as FSPath
from typing import Any, AsyncIterator, Callable

from agent_bench.metrics import BenchmarkResult, StepResult, count_tokens
from agent_bench.scenarios.loader import Scenario, Task


@dataclass
class ToolCallSpec:
    """A single MCP tool invocation plan."""

    tool: str
    args: dict[str, Any]
    note: str = ""


@dataclass
class TaskPlan:
    """What Path A would invoke for one task (may be multi-call)."""

    calls: list[ToolCallSpec] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# (connector, action) → builder(task) -> TaskPlan
_DISPATCH: dict[tuple[str, str], Callable[[Task], TaskPlan]] = {}


def _register(connector: str, action: str):
    def deco(fn: Callable[[Task], TaskPlan]):
        _DISPATCH[(connector, action)] = fn
        return fn
    return deco


# ---------- Slack ----------

@_register("slack", "search")
def _slack_search(task: Task) -> TaskPlan:
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__slack__slack_search_channels",
            args={"query": task.params["keyword"], "limit": 20},
        )],
    )


@_register("slack", "user_search")
def _slack_user_search(task: Task) -> TaskPlan:
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__slack__slack_search_users",
            args={"query": task.params["keyword"], "limit": 20},
        )],
    )


@_register("slack", "get")
def _slack_get(task: Task) -> TaskPlan:
    # No direct get-channel-by-ID in native MCP — fall back to search.
    hint = task.params.get("name_hint") or task.params["id"]
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__slack__slack_search_channels",
            args={"query": hint, "limit": 20},
            note="No native get-channel-by-ID; search-then-filter.",
        )],
        notes=["Native MCP has no get-channel-by-ID; returns N records, client filters."],
    )


# ---------- Linear ----------

@_register("linear", "search")
def _linear_search(task: Task) -> TaskPlan:
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__claude_ai_Linear__list_issues",
            args={"query": task.params["keyword"], "limit": 10},
        )],
    )


@_register("linear", "get")
def _linear_get(task: Task) -> TaskPlan:
    # Linear MCP accepts both UUID and AGENTIC-338 identifier; prefer identifier for readability.
    ident = task.params.get("identifier") or task.params["id"]
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__claude_ai_Linear__get_issue",
            args={"id": ident},
        )],
    )



# ---------- Path ----------

class NativeMCPPath:
    """Record-replay path for vendor-native MCP servers."""

    name = "Native MCP"
    short_name = "native-mcp"

    def __init__(self, recordings_dir: FSPath) -> None:
        self._recordings_dir = recordings_dir

    def plan(self, task: Task, scenario: Scenario) -> TaskPlan:
        key = (scenario.connector, task.action)
        if key not in _DISPATCH:
            raise ValueError(f"No Native MCP dispatch for {key}")
        return _DISPATCH[key](task)

    def recording_path(self, task: Task, scenario: Scenario) -> FSPath:
        return self._recordings_dir / "recording.json"

    async def run_task(
        self, task: Task, scenario: Scenario
    ) -> AsyncIterator[tuple[StepResult, BenchmarkResult]]:
        result = BenchmarkResult(path_name=self.name)
        rec_path = self.recording_path(task, scenario)

        if not rec_path.exists():
            result.status = "skipped"
            result.error = f"No recording at {rec_path} — run `agent-bench record --paths native-mcp` first."
            step = StepResult(
                label=f"{task.action} {task.entity} [no recording]",
                latency_ms=None,
                payload_bytes=0,
                tokens=0,
                records=0,
            )
            result.steps.append(step)
            yield step, result
            return

        with rec_path.open() as f:
            recording = json.load(f)

        # recording is a list of {tool, args, wall_clock_ms, response}
        total_tokens = 0
        total_records = 0
        for idx, call in enumerate(recording):
            resp = call.get("response")
            payload = json.dumps(resp, default=str)
            tokens = count_tokens(resp)
            records = _count_records(resp)
            total_tokens += tokens
            total_records += records
            step = StepResult(
                label=f"{call.get('tool', '?')} (call {idx + 1}/{len(recording)})",
                latency_ms=_parse_wall_clock(call),
                payload_bytes=len(payload.encode()),
                tokens=tokens,
                records=records,
            )
            result.steps.append(step)
            yield step, result

        result.total_records = total_records
        if task.metric_focus == "single_record_fetch":
            result.single_record_calls = len(result.steps)
            result.single_record_tokens = total_tokens

    async def close(self) -> None:
        pass


def _parse_wall_clock(call: dict[str, Any]) -> float | None:
    """Return wall-clock ms from a recording entry, or `None` if unmeasured."""
    raw = call.get("wall_clock_ms")
    if isinstance(raw, int | float) and raw > 0:
        return float(raw)
    return None


def _count_records(response: Any) -> int:
    """Heuristic record count for an arbitrary native MCP response."""
    if response is None:
        return 0
    if isinstance(response, dict):
        for key in ("results", "data", "channels", "members", "users", "issues", "projects", "meetings", "notes"):
            v = response.get(key)
            if isinstance(v, list):
                return len(v)
        # Single-entity get
        if any(k in response for k in ("id", "identifier", "meeting_id")):
            return 1
        return 1  # fallback: one response = one record
    if isinstance(response, list):
        return len(response)
    return 1  # free-form text
