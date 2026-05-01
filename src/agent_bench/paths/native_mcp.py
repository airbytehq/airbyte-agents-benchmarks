"""Path A: Native MCP servers.

These MCP tools (`mcp__claude_ai_Slack__*`, `mcp__claude_ai_Linear__*`,
`mcp__claude_ai_Granola__*`) are provided by each SaaS vendor and invoked via
an MCP client (e.g. Claude Code or Cursor), not by Python code. So this path is built
around a "record once, replay" model:

  1. Call `tool_specs(task, scenario)` to get the exact tool+args the
     benchmark would invoke for a task.
  2. Execute those tool calls from an MCP client (driver/harness), saving
     `{tool, args, wall_clock_ms, response}` to a per-task JSON file.
  3. `run_task` reads the recording and computes StepResult metrics.

Tool surface notes:
  - Slack: no get-channel-by-ID → single-record-fetch falls back to
    slack_search_channels(query=<name_hint>). List falls back to three
    20-result search calls (API max is 20/page).
  - Linear: clean direct mappings for all three tasks.
  - Granola: query_granola_meetings returns a synthesized answer (not
    records); list_meetings has no limit param; get_meeting_transcript
    expects a UUID.
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
            tool="mcp__claude_ai_Slack__slack_search_channels",
            args={"query": task.params["keyword"], "limit": 20},
        )],
    )


@_register("slack", "get")
def _slack_get(task: Task) -> TaskPlan:
    # No direct get-channel-by-ID in native MCP — fall back to search.
    hint = task.params.get("name_hint") or task.params["id"]
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__claude_ai_Slack__slack_search_channels",
            args={"query": hint, "limit": 20},
            note="No native get-channel-by-ID; search-then-filter.",
        )],
        notes=["Native MCP has no get-channel-by-ID; returns N records, client filters."],
    )


@_register("slack", "list")
def _slack_list(task: Task) -> TaskPlan:
    # Search API caps at 20/page — paginate to approximate bulk list.
    limit = int(task.params.get("limit", 50))
    pages = max(1, (limit + 19) // 20)
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__claude_ai_Slack__slack_search_channels",
            args={"query": " ", "limit": 20} | ({"cursor": f"<page{p + 1}-cursor>"} if p else {}),
            note=f"page {p + 1}/{pages}",
        ) for p in range(pages)],
        notes=[f"Native MCP caps channel search at 20/page; {pages} calls needed to approach {limit}."],
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


@_register("linear", "list")
def _linear_list(task: Task) -> TaskPlan:
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__claude_ai_Linear__list_issues",
            args={"limit": int(task.params.get("limit", 50))},
        )],
    )


# ---------- Granola ----------

@_register("granola", "search")
def _granola_search(task: Task) -> TaskPlan:
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__claude_ai_Granola__query_granola_meetings",
            args={"query": task.params["keyword"]},
            note="Returns synthesized answer with citations, not raw records.",
        )],
        notes=["Native MCP's Granola search returns a synthesized answer (not structured records)."],
    )


@_register("granola", "get")
def _granola_get(task: Task) -> TaskPlan:
    # Native MCP expects a UUID; Airbyte Agents' note ID (not_…) is not a UUID.
    # Use a claude_mcp_id override if present; otherwise the recording step
    # must map the Airbyte Agents ID to Granola's UUID out-of-band.
    mid = task.params.get("claude_mcp_id") or task.params["id"]
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__claude_ai_Granola__get_meeting_transcript",
            args={"meeting_id": mid},
            note="Takes UUID; Airbyte Agents note IDs need translation.",
        )],
    )


@_register("granola", "list")
def _granola_list(task: Task) -> TaskPlan:
    return TaskPlan(
        calls=[ToolCallSpec(
            tool="mcp__claude_ai_Granola__list_meetings",
            args={"time_range": "last_30_days"},
            note="No limit param; returns all meetings in the range.",
        )],
        notes=["Native MCP's list_meetings has no limit; record count = whatever the time range yields."],
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
    return 1  # free-form text (e.g., query_granola_meetings)
