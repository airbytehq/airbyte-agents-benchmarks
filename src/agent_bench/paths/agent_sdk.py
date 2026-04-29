"""Path C: REST Baseline (via airbyte-agent-sdk).

Measures the token cost of consuming the third-party provider's full
REST API response. The Airbyte connector fetches records from the
provider (Linear, Granola, Slack) and passes them through unmodified.
The SDK adds auth management and Python deserialization but does not
transform, cache, or compress the response payload. Token counts are
equivalent to what an agent would see calling the provider directly.

Dispatches each task's canonical action to the connector's
`execute(entity, action, params)` method, translating connector-specific
param names where required.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

from airbyte_agent_sdk import connect

from agent_bench.config import LiveConfig
from agent_bench.metrics import BenchmarkResult, StepResult, count_tokens
from agent_bench.scenarios.loader import Scenario, Task


# Per-connector translation table: YAML's canonical `{action, entity, params}`
# maps to the SDK's connector-specific param names and fuzzy-search fields.
_DISPATCH: dict[str, dict[str, Any]] = {
    "slack": {
        "search_field": {"channels": "name", "users": "real_name"},
        "get_key": {"channels": "channel", "users": "user"},
        "list_limit_key": "limit",
    },
    "linear": {
        "search_field": {"issues": "title", "projects": "name", "users": "name"},
        "get_key": {"issues": "id", "projects": "id", "users": "id"},
        "list_limit_key": "first",
    },
    "granola": {
        "search_field": {"notes": "summary_text"},
        "get_key": {"notes": "note_id"},
        "list_limit_key": "page_size",
    },
}


class AgentSDKPath:
    """Path C — talks to Airbyte Agents from the Python process via the SDK."""

    name = "REST Baseline (via SDK)"
    short_name = "agent-sdk"

    def __init__(self, config: LiveConfig, connector_name: str) -> None:
        self._config = config
        self._connector_name = connector_name
        self._connector: Any | None = None

    async def _get_connector(self) -> Any:
        if self._connector is None:
            self._connector = connect(
                self._connector_name, **self._config.auth_kwargs(self._connector_name)
            )
        return self._connector

    async def run_task(
        self, task: Task, scenario: Scenario
    ) -> AsyncIterator[tuple[StepResult, BenchmarkResult]]:
        result = BenchmarkResult(path_name=self.name)
        connector = await self._get_connector()
        dispatch = _DISPATCH[self._connector_name]

        # Translate YAML's canonical task into the SDK call shape.
        sdk_action, sdk_params = _translate(task, dispatch)

        t0 = time.perf_counter()
        try:
            raw = await _maybe_await(connector.execute(
                entity=task.entity, action=sdk_action, params=sdk_params
            ))
        except Exception as exc:  # noqa: BLE001 — surface in result
            result.status = "error"
            result.error = f"{type(exc).__name__}: {exc}"
            elapsed = (time.perf_counter() - t0) * 1000
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

        records, meta = _normalize(raw)
        payload = json.dumps(records, default=str)
        took_ms = meta.get("took_ms") or elapsed
        tokens = count_tokens(records)

        step = StepResult(
            label=f"{sdk_action} {task.entity}",
            latency_ms=took_ms,
            payload_bytes=len(payload.encode()),
            tokens=tokens,
            records=len(records),
        )
        result.steps.append(step)
        result.total_records = len(records)

        if task.action == "get":
            result.single_record_calls = len(result.steps)
            result.single_record_tokens = tokens

        yield step, result

    async def close(self) -> None:
        if self._connector is not None and hasattr(self._connector, "close"):
            await _maybe_await(self._connector.close())
            self._connector = None


def _translate(task: Task, dispatch: dict[str, Any]) -> tuple[str, dict]:
    """Canonical `{action, entity, params}` → SDK `(action, params)`."""
    if task.action == "search":
        field = dispatch["search_field"].get(task.entity)
        if field is None:
            raise ValueError(
                f"No SDK search field mapping for entity {task.entity!r}"
            )
        limit = int(task.params.get("limit", 10))
        return "context_store_search", {
            "query": {"filter": {"fuzzy": {field: task.params["keyword"]}}},
            "limit": limit,
        }
    if task.action == "get":
        key = dispatch["get_key"].get(task.entity)
        if key is None:
            raise ValueError(f"No SDK get-key mapping for entity {task.entity!r}")
        return "get", {key: task.params["id"]}
    if task.action == "list":
        limit_key = dispatch["list_limit_key"]
        limit = int(task.params.get("limit", 50))
        return "list", {limit_key: limit}
    raise ValueError(f"Unsupported task action {task.action!r}")


def _normalize(raw: Any) -> tuple[list[dict], dict]:
    """Coerce SDK response shapes into (records, meta)."""
    # ExecutionResult-like objects expose .data / .meta
    data = getattr(raw, "data", None)
    meta = getattr(raw, "meta", None)
    if data is not None:
        records = [_to_dict(r) for r in data]
        meta_dict = _to_dict(meta) if meta else {}
        return records, meta_dict

    # Dict envelope: {"data": [...], "meta": {...}}
    if isinstance(raw, dict) and "data" in raw:
        records = [_to_dict(r) for r in raw["data"]]
        meta_dict = raw.get("meta") or {}
        return records, meta_dict

    # Bare list of records
    if isinstance(raw, list):
        return [_to_dict(r) for r in raw], {}

    # Single record (get)
    if raw is not None:
        return [_to_dict(raw)], {}

    return [], {}


def _to_dict(obj: Any) -> dict:
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return obj
    return {"value": obj}


async def _maybe_await(value: Any) -> Any:
    """Await a value if it's a coroutine, otherwise return as-is.

    The SDK's `execute()` may be sync or async depending on connector; support both.
    """
    import inspect

    if inspect.isawaitable(value):
        return await value
    return value
