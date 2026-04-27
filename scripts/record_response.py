"""Save a single Claude-Code MCP tool call response as a benchmark recording.

Usage:
    uv run python scripts/record_response.py \
        --path claude \
        --scenario slack \
        --action search \
        --tool mcp__claude_ai_Slack__slack_search_channels \
        --args '{"query": "agent", "limit": 20}' \
        --wall-ms 2150 \
        --response-file /tmp/response.json

Appends to assets/recordings/<path>/<scenario>/<action>.json as a list of
{tool, args, wall_clock_ms, response} objects (some paths fire multiple calls
per task — Slack list, for instance).

Pass --reset to start a fresh recording (drop any prior entries).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_bench.paths.agent_engine_mcp import extract_execution_time_ms


REPO_ROOT = Path(__file__).resolve().parent.parent
RECORDINGS_ROOT = REPO_ROOT / "assets" / "recordings"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True, choices=["claude", "ae-mcp"])
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--args", required=True, help="JSON string of tool args")
    parser.add_argument("--wall-ms", type=float, help="Wall-clock ms. For ae-mcp, omitted means use execution_metadata.execution_time_ms.")
    parser.add_argument("--response-file", required=True, help="Path to a file with the raw response JSON")
    parser.add_argument("--reset", action="store_true", help="Overwrite any existing recording for this task")
    opts = parser.parse_args()

    out_path = RECORDINGS_ROOT / opts.path / opts.scenario / f"{opts.action}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    args = json.loads(opts.args)
    with open(opts.response_file) as f:
        response = json.load(f)

    wall_ms = opts.wall_ms
    if wall_ms is None:
        if opts.path != "ae-mcp":
            parser.error("--wall-ms is required for non-ae-mcp recordings")
        wall_ms = extract_execution_time_ms(response)
        if wall_ms is None:
            parser.error("could not find execution_metadata.execution_time_ms in the ae-mcp response")

    existing: list = []
    if out_path.exists() and not opts.reset:
        with out_path.open() as f:
            existing = json.load(f)

    existing.append({
        "tool": opts.tool,
        "args": args,
        "wall_clock_ms": float(wall_ms),
        "response": response,
    })

    with out_path.open("w") as f:
        json.dump(existing, f, indent=2)

    print(f"saved → {out_path} ({len(existing)} call(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
