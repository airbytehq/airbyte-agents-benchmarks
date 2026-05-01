"""Shared utilities for recording MCP responses."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCENARIOS_DIR = REPO_ROOT / "src" / "agent_bench" / "scenarios"
ARTIFACTS_ROOT = REPO_ROOT / "artifacts"
EXECUTE_TOOL_NAME = "execute"


def default_date() -> str:
    """Return today's date in `YYYY-MM-DD` format (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_scenarios(scenarios_dir: Path = SCENARIOS_DIR) -> list[dict]:
    """Load all scenario YAML files from `scenarios_dir`."""
    return [
        yaml.safe_load(p.read_text())
        for p in sorted(scenarios_dir.glob("*.yaml"))
    ]


def save_recording(
    scenario: str,
    calls: list[dict],
    date: str,
    path_slug: str,
    artifacts_root: Path = ARTIFACTS_ROOT,
) -> Path:
    """Write a recording JSON file and return its path.

    Output layout: `{artifacts_root}/{date}/{scenario}-scenario/{path_slug}/recording.json`
    """
    out_path = artifacts_root / date / f"{scenario}-scenario" / path_slug / "recording.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(calls, indent=2))
    return out_path


def build_arguments(tool_call_args: dict, connector_id: str) -> dict[str, Any]:
    """Translate a YAML `agent-mcp.tool_calls[].args` block into the inner
    item dict for the MCP `execute` tool. Callers must wrap the result in
    `{"items": [item]}` before passing to `call_tool()`.
    """
    return {
        "connector_id": connector_id,
        "entity": tool_call_args.get("entity"),
        "action": tool_call_args.get("action"),
        "params": tool_call_args.get("params", {}),
        "select_fields": tool_call_args.get("select_fields", []),
    }


def check_response_error(response: Any) -> str | None:
    """Return an error description if the MCP response indicates failure.

    Checks for:
    - Top-level `error` field
    - `results[].result.status == "failed"`
    - Pydantic validation error text in content
    """
    if not isinstance(response, dict):
        return None

    if response.get("error"):
        return f"MCP error: {response['error']}"

    for r in response.get("results", []):
        result_data = r.get("result", {})
        if isinstance(result_data, dict) and result_data.get("status") == "failed":
            return f"Result failed: {result_data.get('error', 'unknown')}"

    response_text = json.dumps(response)
    if "ValidationError" in response_text or "pydantic" in response_text.lower():
        return "Pydantic validation error detected in response"

    return None


def count_response_records(response: Any) -> int:
    """Count the total number of data records across all results in an MCP response."""
    if not isinstance(response, dict):
        return 0

    total = 0
    for r in response.get("results", []):
        result_data = r.get("result", {})
        if isinstance(result_data, dict):
            inner = result_data.get("result")
            if isinstance(inner, list):
                total += len(inner)
            elif inner is not None:
                total += 1
    return total


def load_secret(item: str, field: str, section: str | None = None) -> str:
    """Load a secret value from the 1Password `direct-connector-credentials` vault."""
    token = os.environ.get("DEVIN_1PASSWORD_SERVICE_TOKEN") or os.environ.get(
        "SONAR_CONNECTOR_CREDS_1PASS_TOKEN", ""
    )
    env = os.environ.copy()
    env["OP_SERVICE_ACCOUNT_TOKEN"] = token

    cmd = [
        "op", "item", "get", item,
        "--vault=direct-connector-credentials",
        "--format=json",
        "--reveal",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)  # noqa: S603
    data = json.loads(result.stdout)

    for f_entry in data.get("fields", []):
        f_section = f_entry.get("section", {}).get("label", "")
        f_label = f_entry.get("label", "")
        if f_label == field:
            if section is None or f_section == section:
                return f_entry.get("value", "")
    return ""
