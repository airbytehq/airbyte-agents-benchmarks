"""Re-record all agent-mcp benchmark recordings via the Sonar execute API.

Usage (requires SONAR credentials in env or MCP access):
    uv run python scripts/rerecord_agent_mcp.py --date 2026-04-28

Calls the Sonar integrations execute endpoint for each scenario,
wraps the response in the MCP envelope format, and writes to:
    artifacts/{date}/{scenario}-scenario/agent-mcp/recording.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = REPO_ROOT / "src" / "agent_bench" / "scenarios"
ARTIFACTS_ROOT = REPO_ROOT / "artifacts"

# select_fields per (connector, entity) — matches agent_mcp.py
SELECT_FIELDS: dict[tuple[str, str], list[str]] = {
    ("slack", "channels"): [
        "id", "name", "num_members", "is_archived",
        "is_private", "created", "updated", "topic", "purpose",
    ],
    ("linear", "issues"): [
        "id", "identifier", "title", "state", "priority",
        "createdAt", "updatedAt", "team", "labels",
    ],
    ("granola", "notes"): [
        "id", "title", "created_at", "updated_at",
        "attendees", "summary_text", "transcript",
    ],
}

# SDK-compatible translation (mirrors agent_sdk._DISPATCH + _translate)
DISPATCH: dict[str, dict[str, Any]] = {
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


def translate(action: str, entity: str, params: dict, dispatch: dict) -> tuple[str, dict]:
    if action == "search":
        field = dispatch["search_field"].get(entity)
        limit = int(params.get("limit", 10))
        return "context_store_search", {
            "query": {"filter": {"fuzzy": {field: params["keyword"]}}},
            "limit": limit,
        }
    if action == "get":
        key = dispatch["get_key"].get(entity)
        return "get", {key: params["id"]}
    if action == "list":
        limit_key = dispatch["list_limit_key"]
        return "list", {limit_key: int(params.get("limit", 50))}
    raise ValueError(f"Unknown action: {action}")


def load_scenarios() -> list[dict]:
    scenarios = []
    for yaml_path in sorted(SCENARIOS_DIR.glob("*.yaml")):
        with open(yaml_path) as f:
            scenarios.append(yaml.safe_load(f))
    return scenarios


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
    """Call the Sonar execute endpoint and return (response, wall_clock_ms)."""
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Artifact date folder (YYYY-MM-DD). Defaults to today UTC.",
    )
    parser.add_argument(
        "--connectors",
        default="linear,granola,slack",
        help="Comma-separated connectors to re-record.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SONAR_API_HOST", "https://api.airbyte.ai"),
        help="Sonar API base URL.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing.")
    opts = parser.parse_args()

    org_id = os.environ.get("AIRBYTE_ORGANIZATION_ID")
    client_id = os.environ.get("AIRBYTE_CLIENT_ID")
    client_secret = os.environ.get("AIRBYTE_CLIENT_SECRET")
    if not all([org_id, client_id, client_secret]):
        print("ERROR: AIRBYTE_ORGANIZATION_ID, AIRBYTE_CLIENT_ID, AIRBYTE_CLIENT_SECRET must be set", file=sys.stderr)
        return 1

    target_connectors = set(opts.connectors.split(","))
    scenarios = load_scenarios()

    # Authenticate
    if not opts.dry_run:
        print("Authenticating against Airbyte API ...")
        token = get_airbyte_token(client_id, client_secret)
        print("Authenticated.")

    results_summary = []

    for scenario in scenarios:
        connector = scenario["connector"]
        if connector not in target_connectors:
            continue

        scenario_name = scenario["name"]
        task = scenario["task"]
        dispatch = DISPATCH.get(connector)
        if dispatch is None:
            print(f"SKIP {scenario_name}: no dispatch table for {connector}")
            continue

        connector_id_env = scenario["connector_id_env"]
        connector_id = os.environ.get(connector_id_env)
        if not connector_id:
            print(f"SKIP {scenario_name}: {connector_id_env} not set")
            continue

        sdk_action, sdk_params = translate(
            task["action"], task["entity"], task["params"], dispatch
        )
        select_fields = SELECT_FIELDS.get((connector, task["entity"]), ["id"])

        out_path = ARTIFACTS_ROOT / opts.date / f"{scenario_name}-scenario" / "agent-mcp" / "recording.json"

        print(f"\n{'[DRY RUN] ' if opts.dry_run else ''}Recording {scenario_name} ...")
        print(f"  connector_id: {connector_id}")
        print(f"  action: {sdk_action}, entity: {task['entity']}")
        print(f"  params: {json.dumps(sdk_params)}")
        print(f"  select_fields: {select_fields}")
        print(f"  output: {out_path}")

        if opts.dry_run:
            continue

        try:
            response, wall_ms = execute_call(
                opts.base_url, token, org_id,
                connector_id, task["entity"], sdk_action, sdk_params, select_fields,
            )
            # Use server-side execution_time_ms as wall_clock_ms for consistency
            # with the MCP recording format (the harness validates they match).
            exec_ms = response.get("execution_metadata", {}).get("execution_time_ms")
            effective_ms = float(exec_ms) if exec_ms is not None else wall_ms
            print(f"  wall_clock_ms: {effective_ms:.1f} (http: {wall_ms:.1f})")

            recording = [wrap_mcp_envelope(
                connector_id, task["entity"], sdk_action, sdk_params,
                select_fields, response, effective_ms,
            )]

            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w") as f:
                json.dump(recording, f, indent=2)

            # Quick stats
            payload = json.dumps(response, default=str)
            print(f"  payload_bytes: {len(payload.encode())}")
            print(f"  saved to {out_path}")
            results_summary.append((scenario_name, "OK", f"{wall_ms:.0f}ms"))

        except Exception as exc:
            print(f"  ERROR: {exc}")
            results_summary.append((scenario_name, "FAILED", str(exc)))

    print("\n=== Summary ===")
    for name, status, detail in results_summary:
        print(f"  {name}: {status} ({detail})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
