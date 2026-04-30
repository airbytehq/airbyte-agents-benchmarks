"""Re-record all agent-mcp benchmark recordings via the Sonar execute API.

Usage (requires SONAR credentials in env or MCP access):
    uv run python scripts/rerecord_agent_mcp.py --date 2026-04-30

Reads the `paths.agent-mcp.tool_calls` from each scenario YAML and
executes them against the Sonar API. Writes recordings to:
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
        default=None,
        help="Comma-separated connectors to re-record. Defaults to all.",
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

    target_connectors = set(opts.connectors.split(",")) if opts.connectors else None
    scenarios = load_scenarios()

    # Authenticate
    token = ""
    if not opts.dry_run:
        print("Authenticating against Airbyte API ...")
        token = get_airbyte_token(client_id, client_secret)
        print("Authenticated.")

    results_summary: list[tuple[str, str, str]] = []

    for scenario in scenarios:
        connector = scenario["connector"]
        if target_connectors and connector not in target_connectors:
            continue

        scenario_name = scenario["name"]
        paths = scenario.get("paths", {})
        agent_mcp = paths.get("agent-mcp", {})
        tool_calls = agent_mcp.get("tool_calls", [])
        if not tool_calls:
            print(f"SKIP {scenario_name}: no agent-mcp tool_calls defined")
            continue

        out_path = ARTIFACTS_ROOT / opts.date / f"{scenario_name}-scenario" / "agent-mcp" / "recording.json"

        print(f"\n{'[DRY RUN] ' if opts.dry_run else ''}Recording {scenario_name} ({len(tool_calls)} call(s)) ...")

        if opts.dry_run:
            for i, tc in enumerate(tool_calls):
                cid_env = tc.get("connector_id_env", scenario.get("connector_id_env", ""))
                args = tc.get("args", {})
                print(f"  [{i+1}] connector_id_env={cid_env}")
                print(f"      entity={args.get('entity')}, action={args.get('action')}")
                print(f"      select_fields={args.get('select_fields', [])}")
            continue

        recording: list[dict] = []
        scenario_ok = True

        for i, tc in enumerate(tool_calls):
            cid_env = tc.get("connector_id_env", scenario.get("connector_id_env", ""))
            connector_id = os.environ.get(cid_env, "")
            if not connector_id:
                print(f"  SKIP call [{i+1}]: {cid_env} not set")
                scenario_ok = False
                break

            args = tc.get("args", {})
            entity = args.get("entity", "unknown")
            action = args.get("action", "unknown")
            params = args.get("params", {})
            select_fields = args.get("select_fields", [])

            print(f"  [{i+1}] connector_id={connector_id[:8]}... entity={entity} action={action}")

            try:
                response, wall_ms = execute_call(
                    opts.base_url, token, org_id,
                    connector_id, entity, action, params, select_fields,
                )
                exec_ms = response.get("execution_metadata", {}).get("execution_time_ms")
                effective_ms = float(exec_ms) if exec_ms is not None else wall_ms
                print(f"      wall_clock_ms: {effective_ms:.1f} (http: {wall_ms:.1f})")

                recording.append(wrap_mcp_envelope(
                    connector_id, entity, action, params,
                    select_fields, response, effective_ms,
                ))

                payload = json.dumps(response, default=str)
                print(f"      payload_bytes: {len(payload.encode())}")

            except Exception as exc:
                print(f"      ERROR: {exc}")
                scenario_ok = False
                results_summary.append((scenario_name, "FAILED", str(exc)))
                break

        if scenario_ok and recording:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w") as f:
                json.dump(recording, f, indent=2)
            print(f"  saved to {out_path}")
            results_summary.append((scenario_name, "OK", f"{len(recording)} call(s)"))

    print("\n=== Summary ===")
    for name, status, detail in results_summary:
        print(f"  {name}: {status} ({detail})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
