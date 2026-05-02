"""Record agent-mcp responses via the Sonar REST API (emulated MCP).

This is the legacy approach that calls the Sonar `execute` endpoint
directly and wraps responses in a synthesized MCP envelope. Use this
when the real MCP server is unavailable.

Requires `AIRBYTE_ORGANIZATION_ID`, `AIRBYTE_CLIENT_ID`, and
`AIRBYTE_CLIENT_SECRET` environment variables.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from agent_bench.recording.common import (
    check_response_error,
    count_response_records,
    default_date,
    load_scenarios,
    save_recording,
)


def get_airbyte_token(client_id: str, client_secret: str) -> str:
    """Get a bearer token from the Airbyte public API."""
    resp = httpx.post(
        "https://api.airbyte.com/v1/applications/token",
        json={"client_id": client_id, "client_secret": client_secret},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def execute_call(
    base_url: str,
    token: str,
    org_id: str,
    connector_id: str,
    entity: str,
    action: str,
    params: dict,
    select_fields: list[str],
) -> tuple[dict, float]:
    """Call the Sonar execute endpoint and return `(response, wall_clock_ms)`."""
    body: dict[str, Any] = {
        "entity": entity,
        "action": action,
        "params": params,
    }
    if select_fields:
        body["select_fields"] = select_fields

    t0 = time.perf_counter()
    resp = httpx.post(
        f"{base_url}/api/v1/integrations/connectors/{connector_id}/execute",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": org_id,
        },
        json=body,
        timeout=60,
    )
    wall_ms = (time.perf_counter() - t0) * 1000
    resp.raise_for_status()
    return resp.json(), wall_ms


def wrap_mcp_envelope(
    connector_id: str,
    entity: str,
    action: str,
    params: dict,
    select_fields: list[str],
    response: dict,
    wall_ms: float,
) -> dict:
    """Wrap a raw execute response in the MCP recording format."""
    return {
        "tool": "mcp__airbyte-agent__execute",
        "args": {
            "items": [{
                "connector_id": connector_id,
                "entity": entity,
                "action": action,
                "params": params,
                "select_fields": select_fields,
            }],
        },
        "wall_clock_ms": round(wall_ms, 1),
        "response": {
            "results": [{
                "connector_id": connector_id,
                "success": True,
                "result": response,
                "error": None,
            }],
        },
    }


def record_emulated_agent_mcp(
    connectors: str | None,
    date: str | None = None,
    base_url: str | None = None,
    dry_run: bool = False,
) -> int:
    """Orchestrate recording via the Sonar REST API (emulated MCP).

    Returns 0 on success, 1 if any scenario failed.
    """
    date = date or default_date()
    base_url = base_url or os.environ.get("SONAR_API_HOST", "https://api.airbyte.ai")

    org_id = os.environ.get("AIRBYTE_ORGANIZATION_ID")
    client_id = os.environ.get("AIRBYTE_CLIENT_ID")
    client_secret = os.environ.get("AIRBYTE_CLIENT_SECRET")
    if not all([org_id, client_id, client_secret]):
        print(
            "ERROR: AIRBYTE_ORGANIZATION_ID, AIRBYTE_CLIENT_ID, "
            "AIRBYTE_CLIENT_SECRET must be set",
            file=sys.stderr,
        )
        return 1

    target = set(connectors.split(",")) if connectors else None
    scenarios = load_scenarios()

    if dry_run:
        for scenario in scenarios:
            connector = scenario["connector"]
            if target and connector not in target:
                continue
            tool_calls = scenario.get("paths", {}).get("agent-mcp", {}).get("tool_calls", [])
            print(f"{scenario['name']}: {len(tool_calls)} call(s)")
        return 0

    print("Authenticating against Airbyte API ...")
    token = get_airbyte_token(client_id, client_secret)
    print("Authenticated.")

    results_summary: list[tuple[str, str, str]] = []

    for scenario in scenarios:
        connector = scenario["connector"]
        if target and connector not in target:
            continue

        scenario_name = scenario["name"]
        if scenario.get("skip_recording"):
            print(f"SKIP {scenario_name}: skip_recording is set")
            continue
        paths = scenario.get("paths", {})
        tool_calls = paths.get("agent-mcp", {}).get("tool_calls", [])
        if not tool_calls:
            print(f"SKIP {scenario_name}: no agent-mcp tool_calls defined")
            continue

        print(f"\nRecording {scenario_name} ({len(tool_calls)} call(s)) ...")
        recording: list[dict] = []
        scenario_ok = True

        for i, tc in enumerate(tool_calls):
            cid_env = tc.get("connector_id_env", scenario.get("connector_id_env", ""))
            connector_id = os.environ.get(cid_env, "")
            if not connector_id:
                print(f"  SKIP call [{i + 1}]: {cid_env} not set")
                scenario_ok = False
                break

            args = tc.get("args", {})
            entity = args.get("entity", "unknown")
            action = args.get("action", "unknown")
            params = args.get("params", {})
            select_fields = args.get("select_fields", [])

            print(
                f"  [{i + 1}] connector_id={connector_id[:8]}... "
                f"entity={entity} action={action}"
            )

            try:
                response, wall_ms = execute_call(
                    base_url, token, org_id,
                    connector_id, entity, action, params, select_fields,
                )
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:200]
                print(f"      HTTP {exc.response.status_code}: {body}", file=sys.stderr)
                results_summary.append((scenario_name, "FAILED", f"HTTP {exc.response.status_code}"))
                scenario_ok = False
                break

            exec_ms = response.get("execution_metadata", {}).get("execution_time_ms")
            effective_ms = float(exec_ms) if exec_ms is not None else wall_ms
            print(f"      wall_clock_ms: {effective_ms:.1f} (http: {wall_ms:.1f})")

            error = check_response_error(
                {"results": [{"connector_id": connector_id, "result": response}]}
            )
            if error:
                snippet = json.dumps(response, default=str)[:200]
                print(f"      ERROR: {error}", file=sys.stderr)
                print(f"      Response: {snippet}", file=sys.stderr)
                results_summary.append((scenario_name, "FAILED", error))
                scenario_ok = False
                break

            recording.append(wrap_mcp_envelope(
                connector_id, entity, action, params,
                select_fields, response, effective_ms,
            ))

            payload = json.dumps(response, default=str)
            print(f"      payload_bytes: {len(payload.encode())}")

        if scenario_ok and recording:
            total_records = sum(
                count_response_records(call["response"]) for call in recording
            )
            if total_records == 0:
                for call in recording:
                    snippet = json.dumps(call["response"], default=str)[:300]
                    print(f"      Response: {snippet}", file=sys.stderr)
                results_summary.append(
                    (scenario_name, "FAILED", "zero records across all calls")
                )
                continue
            save_recording(scenario_name, recording, date, "agent-mcp")
            results_summary.append(
                (scenario_name, "OK", f"{len(recording)} call(s), {total_records} record(s)")
            )

    print("\n=== Summary ===")
    failed = False
    for name, status, detail in results_summary:
        print(f"  {name}: {status} ({detail})")
        if status == "FAILED":
            failed = True
    return 1 if failed else 0
