"""Record agent-mcp responses via real JSON-RPC to `mcp.airbyte.ai`.

Requires a one-time browser auth via `agent-bench auth` to seed the local
token store. Token refresh is automatic until the FastMCP refresh token
expires (approximately 3 days of inactivity).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_bench.airbyte_mcp import (
    DEFAULT_MCP_URL,
    DEFAULT_TOKEN_PATH,
    AirbyteMCPClient,
    FileTokenStorage,
)
from agent_bench.recording.common import (
    EXECUTE_TOOL_NAME,
    build_arguments,
    check_response_error,
    count_response_records,
    default_date,
    load_scenarios,
    save_recording,
)


def _extract_next_cursor(response: dict) -> str:
    """Extract `next_cursor` from an agent-mcp paginated response.

    Searches through `results[].result.connector_metadata.next_cursor`.
    """
    for r in response.get("results", []):
        result_data = r.get("result", {})
        if isinstance(result_data, dict):
            meta = result_data.get("connector_metadata", {})
            if isinstance(meta, dict):
                cursor = meta.get("next_cursor", "")
                if cursor:
                    return cursor
    return ""


async def record_scenario(
    client: AirbyteMCPClient,
    scenario: dict,
    date: str,
) -> tuple[str, str, str]:
    """Record all agent-mcp tool calls for a single scenario.

    Returns `(scenario_name, status, detail)` where status is
    `"OK"`, `"SKIP"`, or `"FAILED"`.
    """
    name = scenario["name"]
    if scenario.get("skip_recording"):
        return (name, "SKIP", "skip_recording is set")
    paths = scenario.get("paths", {})
    tool_calls = paths.get("agent-mcp", {}).get("tool_calls", [])
    if not tool_calls:
        return (name, "SKIP", "no agent-mcp tool_calls in YAML")

    recording: list[dict] = []
    total_records = 0

    for i, tc in enumerate(tool_calls):
        cid_env = tc.get("connector_id_env") or scenario.get("connector_id_env", "")
        connector_id = os.environ.get(cid_env, "")
        if not connector_id:
            return (name, "FAILED", f"{cid_env} not set")

        paginate_to_end = tc.get("paginate_to_end", False)
        base_args = build_arguments(tc.get("args", {}), connector_id)
        print(
            f"  [{i + 1}/{len(tool_calls)}] {base_args['entity']} {base_args['action']} "
            f"(connector_id={connector_id[:8]}...)"
            f"{' (paginate_to_end)' if paginate_to_end else ''}"
        )

        page_num = 0
        current_args = dict(base_args)
        while True:
            page_num += 1
            execute_args = {"items": [current_args]}
            response, wall_ms = await client.call_tool(EXECUTE_TOOL_NAME, execute_args)

            error = check_response_error(response)
            if error:
                return (name, "FAILED", error)

            total_records += count_response_records(response)

            recording.append({
                "tool": "mcp__airbyte-agent__execute",
                "args": execute_args,
                "wall_clock_ms": round(wall_ms, 1),
                "response": response,
            })

            if not paginate_to_end:
                break
            next_cursor = _extract_next_cursor(response)
            if not next_cursor:
                print(f"      pagination complete after {page_num} page(s)")
                break
            current_args = {**base_args, "params": {**base_args.get("params", {}), "cursor": next_cursor}}

    if total_records == 0:
        return (name, "FAILED", "zero records across all calls")

    save_recording(name, recording, date, "agent-mcp")
    return (name, "OK", f"{len(recording)} call(s), {total_records} record(s)")


async def record_agent_mcp(
    connectors: str | None,
    date: str | None = None,
    server_url: str = DEFAULT_MCP_URL,
    token_path: Path = DEFAULT_TOKEN_PATH,
    dry_run: bool = False,
) -> int:
    """Orchestrate recording of all matching agent-mcp scenarios.

    Returns 0 on success, 1 if any scenario failed.
    """
    date = date or default_date()
    load_dotenv()

    # Allow .env override for per-profile token files (only when caller
    # didn't pass an explicit --token-path, i.e. still at default).
    env_token_path = os.environ.get("AIRBYTE_TOKEN_PATH")
    if env_token_path and token_path == DEFAULT_TOKEN_PATH:
        token_path = Path(env_token_path)

    target = set(connectors.split(",")) if connectors else None
    scenarios = [
        s for s in load_scenarios()
        if not target or s.get("connector") in target
    ]
    if not scenarios:
        print(f"No scenarios match --connectors={connectors}", file=sys.stderr)
        return 1

    if dry_run:
        for s in scenarios:
            tool_calls = s.get("paths", {}).get("agent-mcp", {}).get("tool_calls", [])
            print(f"{s['name']}: {len(tool_calls)} call(s)")
        return 0

    if not token_path.is_file():
        print(
            f"ERROR: no tokens at {token_path}.\n"
            "Run `agent-bench auth` first.",
            file=sys.stderr,
        )
        return 1

    org_id = os.environ.get("AIRBYTE_ORGANIZATION_ID")
    if not org_id:
        print("ERROR: AIRBYTE_ORGANIZATION_ID must be set", file=sys.stderr)
        return 1

    storage = FileTokenStorage(token_path)
    client = AirbyteMCPClient(
        server_url=server_url, organization_id=org_id, storage=storage
    )
    summary: list[tuple[str, str, str]] = []
    try:
        await client.initialize()
        for s in scenarios:
            print(f"\nRecording {s['name']} ({s['connector']}) ...")
            summary.append(await record_scenario(client, s, date))
    finally:
        await client.close()

    print("\n=== Summary ===")
    failed = False
    for name, status, detail in summary:
        print(f"  {name}: {status} ({detail})")
        if status == "FAILED":
            failed = True
    return 1 if failed else 0
