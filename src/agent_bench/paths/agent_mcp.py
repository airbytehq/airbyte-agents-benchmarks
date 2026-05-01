"""Path B: Agent MCP (hosted proxy at mcp.airbyte.ai).

Invoked via `mcp__airbyte-agent__execute`. Supports two modes:

- **replay**: reads pre-recorded JSON-RPC responses from disk.
- **live**: speaks real JSON-RPC to ``mcp.airbyte.ai`` via
  `agent_bench.airbyte_mcp.AirbyteMCPClient` (browser-based
  PKCE auth, see `agent-bench auth`).

Both modes count tokens on the same payload shape that an LLM consumes
when calling the MCP tool — the FastMCP ``structuredContent`` (or, for
older recordings, the inner data after peeling the synthesized
``results[0].result`` envelope).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path as FSPath
from typing import Any, AsyncIterator, Literal

from agent_bench.config import LiveConfig
from agent_bench.metrics import BenchmarkResult, StepResult, count_tokens
from agent_bench.paths.native_mcp import ToolCallSpec, TaskPlan, _count_records
from agent_bench.paths.agent_sdk import _DISPATCH as _SDK_DISPATCH, _translate
from agent_bench.scenarios.loader import Scenario, Task


def _entity_select_fields(connector: str, entity: str) -> list[str]:
    """Minimal select_fields per (connector, entity) for fair narrow comparisons.

    Kept deliberately small (IDs + primary label + few metadata fields) so
    Path B and Path C return the same payload shape. If missing, the MCP
    requires select_fields or exclude_fields to be present.
    """
    mapping: dict[tuple[str, str], list[str]] = {
        ("slack", "channels"): ["id", "name", "num_members", "is_archived", "is_private", "created", "updated", "topic", "purpose"],
        ("linear", "issues"): ["id", "identifier", "title", "state", "priority", "createdAt", "updatedAt", "team", "labels"],
        ("granola", "notes"): ["id", "title", "created_at", "updated_at", "attendees", "summary_text", "transcript"],
        ("gong", "calls"): ["id", "title", "scheduled", "duration"],
        ("salesforce", "accounts"): ["Id", "Name", "Type", "Industry"],
        ("zendesk", "tickets"): ["id", "subject", "status", "priority"],
    }
    return mapping.get((connector, entity), ["id"])


class AgentMCPPath:
    """Agent MCP path with live and replay modes."""

    name = "Agent MCP"
    short_name = "agent-mcp"

    def __init__(
        self,
        config: LiveConfig,
        recordings_dir: FSPath,
        mode: Literal["live", "replay"] = "live",
    ) -> None:
        self._config = config
        self._recordings_dir = recordings_dir
        self._mode = mode
        self._connector: Any | None = None

    def plan(self, task: Task, scenario: Scenario) -> TaskPlan:
        connector_id = self._config.connector_ids[scenario.connector]
        sdk_action, sdk_params = _translate(task, _SDK_DISPATCH[scenario.connector])
        select_fields = _entity_select_fields(scenario.connector, task.entity)
        item = {
            "connector_id": connector_id,
            "entity": task.entity,
            "action": sdk_action,
            "params": sdk_params,
            "select_fields": select_fields,
        }
        return TaskPlan(
            calls=[ToolCallSpec(
                tool="mcp__airbyte-agent__execute",
                args={"items": [item]},
            )],
            notes=[
                "Before recording this connector, call "
                f"mcp__airbyte-agent__describe_connector(connector_id={connector_id!r}) once."
            ],
        )

    def recording_path(self, task: Task, scenario: Scenario) -> FSPath:
        return self._recordings_dir / "recording.json"

    async def run_task(
        self, task: Task, scenario: Scenario
    ) -> AsyncIterator[tuple[StepResult, BenchmarkResult]]:
        if self._mode == "live":
            async for step, result in self._run_live(task, scenario):
                yield step, result
        else:
            async for step, result in self._run_replay(task, scenario):
                yield step, result

    async def _run_live(
        self, task: Task, scenario: Scenario
    ) -> AsyncIterator[tuple[StepResult, BenchmarkResult]]:
        """Call `mcp.airbyte.ai` over real JSON-RPC.

        Requires a one-time browser auth via `agent-bench auth`.
        Token refresh is automatic until the FastMCP refresh token expires
        (approximately 30 minutes of inactivity).
        """
        from agent_bench.airbyte_mcp import AirbyteMCPClient

        result = BenchmarkResult(path_name=self.name)
        connector_id = self._config.connector_ids[scenario.connector]
        sdk_action, sdk_params = _translate(task, _SDK_DISPATCH[scenario.connector])
        select_fields = _entity_select_fields(scenario.connector, task.entity)
        args: dict[str, Any] = {
            "connector_id": connector_id,
            "entity": task.entity,
            "action": sdk_action,
            "params": sdk_params,
            "select_fields": select_fields,
        }

        if self._connector is None:
            self._connector = AirbyteMCPClient(
                organization_id=self._config.organization_id,
            )
            await self._connector.initialize()

        t0 = time.perf_counter()
        try:
            response, _ = await self._connector.call_tool("execute", {"items": [args]})
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - t0) * 1000
            result.status = "error"
            result.error = f"{type(exc).__name__}: {exc}"
            step = StepResult(
                label=f"{sdk_action} {task.entity} [error]",
                latency_ms=elapsed,
                payload_bytes=0,
                tokens=0,
                records=0,
            )
            result.steps.append(step)
            yield step, result
            return
        elapsed = (time.perf_counter() - t0) * 1000

        if isinstance(response, dict) and response.get("error"):
            result.status = "error"
            result.error = f"MCP error: {response['error']}"
            step = StepResult(
                label=f"{sdk_action} {task.entity} [error]",
                latency_ms=elapsed,
                payload_bytes=0,
                tokens=0,
                records=0,
            )
            result.steps.append(step)
            yield step, result
            return

        inner = _extract_inner(response)
        payload = json.dumps(inner, default=str)
        tokens = count_tokens(inner)
        records = _count_records(inner)

        step = StepResult(
            label=f"{sdk_action} {task.entity}",
            latency_ms=elapsed,
            payload_bytes=len(payload.encode()),
            tokens=tokens,
            records=records,
        )
        result.steps.append(step)
        result.total_records = records
        if task.metric_focus == "single_record_fetch":
            result.single_record_calls = len(result.steps)
            result.single_record_tokens = tokens

        yield step, result

    async def _run_replay(
        self, task: Task, scenario: Scenario
    ) -> AsyncIterator[tuple[StepResult, BenchmarkResult]]:
        """Read pre-recorded responses from disk."""
        result = BenchmarkResult(path_name=self.name)
        rec_path = self.recording_path(task, scenario)

        if not rec_path.exists():
            result.status = "skipped"
            result.error = f"No recording at {rec_path} — run `agent-bench record --paths agent-mcp` first."
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

        for idx, call in enumerate(recording):
            resp = call.get("response")
            inner = _extract_inner(resp)
            payload = json.dumps(inner, default=str)
            tokens = count_tokens(inner)
            records = _count_records(inner)
            wall_clock_ms = _recorded_wall_clock_ms(call, resp)
            step = StepResult(
                label=f"mcp execute (call {idx + 1}/{len(recording)})",
                latency_ms=wall_clock_ms,
                payload_bytes=len(payload.encode()),
                tokens=tokens,
                records=records,
            )
            result.steps.append(step)
            yield step, result

        result.total_records = sum(s.records for s in result.steps)
        if task.metric_focus == "single_record_fetch":
            result.single_record_calls = len(result.steps)
            result.single_record_tokens = sum(s.tokens for s in result.steps)

    async def close(self) -> None:
        if self._connector is not None and hasattr(self._connector, "close"):
            await self._connector.close()
            self._connector = None


def _extract_inner(resp: Any) -> Any:
    """Peel the Platform MCP envelopes off execute() responses.

    The full wrap is two nested layers:
      {"results": [{"result": {"status":"success", "result": <data>, ...}}]}
    where the innermost <data> is either a dict like {"data": [...], "meta": ...}
    (list/search) or the entity itself (get).
    """
    if isinstance(resp, dict) and "results" in resp and isinstance(resp["results"], list):
        items = resp["results"]
        if len(items) == 1:
            inner = items[0].get("result") if isinstance(items[0], dict) else None
            if isinstance(inner, dict) and "result" in inner and inner.get("status") == "success":
                return inner["result"]
            return inner
        return items
    return resp


def extract_execution_time_ms(resp: Any) -> float | None:
    """Find execution timing in current and older Platform MCP envelopes."""
    values: list[float] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("execution_metadata", "execute_metadata"):
                meta = value.get(key)
                if isinstance(meta, dict):
                    raw = meta.get("execution_time_ms")
                    if isinstance(raw, int | float):
                        values.append(float(raw))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(resp)
    if not values:
        return None
    return sum(values)


def _recorded_wall_clock_ms(call: dict[str, Any], resp: Any) -> float | None:
    """Return timing ms from a recording entry, or `None` if unmeasured."""
    raw = call.get("wall_clock_ms")
    if isinstance(raw, int | float) and raw > 0:
        return float(raw)
    extracted = extract_execution_time_ms(resp)
    if extracted is not None and extracted > 0:
        return float(extracted)
    return None
