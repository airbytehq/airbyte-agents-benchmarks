"""Record a single MCP tool-call response as a benchmark recording."""

from __future__ import annotations

import json
from pathlib import Path

from agent_bench.paths.agent_mcp import extract_execution_time_ms
from agent_bench.recording.common import ARTIFACTS_ROOT


def record_one(
    path_slug: str,
    scenario: str,
    tool: str,
    args_json: str,
    response_file: Path,
    date: str,
    wall_ms: float | None = None,
    reset: bool = False,
    artifacts_root: Path = ARTIFACTS_ROOT,
) -> Path:
    """Save a single MCP tool-call response and return the output path.

    Appends to any existing recording unless `reset` is True.

    Raises `ValueError` if `wall_ms` is required but not provided or
    not extractable from the response.
    """
    out_path = artifacts_root / date / f"{scenario}-scenario" / path_slug / "recording.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    args = json.loads(args_json)
    response = json.loads(response_file.read_text())

    if wall_ms is None:
        if path_slug != "agent-mcp":
            raise ValueError("--wall-ms is required for non-agent-mcp recordings")
        wall_ms = extract_execution_time_ms(response)
        if wall_ms is None:
            raise ValueError(
                "could not find execution_metadata.execution_time_ms in the agent-mcp response"
            )

    existing: list[dict] = []
    if out_path.exists() and not reset:
        existing = json.loads(out_path.read_text())

    existing.append({
        "tool": tool,
        "args": args,
        "wall_clock_ms": float(wall_ms),
        "response": response,
    })

    out_path.write_text(json.dumps(existing, indent=2))
    return out_path
