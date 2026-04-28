"""Recording validation for the record-replay benchmark paths."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_bench.config import LiveConfig
from agent_bench.paths.agent_mcp import (
    AgentMCPPath,
    extract_execution_time_ms,
)
from agent_bench.scenarios.loader import Task, load_scenario


RECORD_REPLAY_PATHS = {"agent-mcp", "native-mcp"}


@dataclass
class RecordingIssue:
    """One validation problem in a recording file."""

    level: Literal["error", "warning"]
    path_slug: str
    scenario: str
    action: str
    message: str

    def format(self) -> str:
        return f"{self.level.upper()} {self.path_slug}/{self.scenario}/{self.action}: {self.message}"


def validate_recordings(
    scenario_names: list[str],
    path_slugs: list[str],
    recordings_dir: Path,
    config: LiveConfig | None = None,
) -> list[RecordingIssue]:
    """Validate all required record-replay files for a planned run."""
    issues: list[RecordingIssue] = []
    selected_replay_paths = [p for p in path_slugs if p in RECORD_REPLAY_PATHS]
    recordings_dir = Path(recordings_dir)

    for name in scenario_names:
        scenario = load_scenario(name)
        for task in scenario.tasks:
            for slug in selected_replay_paths:
                rec_path = recordings_dir / slug / scenario.connector / f"{task.action}.json"
                if not rec_path.exists():
                    issues.append(_issue("error", slug, scenario.name, task, f"missing recording at {rec_path}"))
                    continue
                try:
                    recording = json.loads(rec_path.read_text())
                except json.JSONDecodeError as exc:
                    issues.append(_issue("error", slug, scenario.name, task, f"invalid JSON: {exc}"))
                    continue
                if not isinstance(recording, list) or not recording:
                    issues.append(_issue("error", slug, scenario.name, task, "recording must be a non-empty list"))
                    continue

                if slug == "agent-mcp":
                    issues.extend(_validate_agent_mcp_recording(recording, scenario.name, task, recordings_dir, config))
                elif slug == "native-mcp":
                    issues.extend(_validate_native_mcp_recording(recording, scenario.name, task))

    return issues


def blocking_issues(issues: list[RecordingIssue]) -> list[RecordingIssue]:
    return [issue for issue in issues if issue.level == "error"]


def _validate_native_mcp_recording(
    recording: list[object],
    scenario_name: str,
    task: Task,
) -> list[RecordingIssue]:
    issues: list[RecordingIssue] = []
    for idx, call in enumerate(recording):
        if not isinstance(call, dict):
            issues.append(_issue("error", "native-mcp", scenario_name, task, f"call {idx + 1} must be an object"))
            continue
        issues.extend(_validate_common_call(call, "native-mcp", scenario_name, task, idx))
        if "wall_clock_ms" not in call:
            issues.append(_issue("warning", "native-mcp", scenario_name, task, f"call {idx + 1} has no wall_clock_ms; native MCP latency is treated as unmeasured"))
    return issues


def _validate_agent_mcp_recording(
    recording: list[object],
    scenario_name: str,
    task: Task,
    recordings_dir: Path,
    config: LiveConfig | None,
) -> list[RecordingIssue]:
    issues: list[RecordingIssue] = []
    scenario = load_scenario(scenario_name)
    expected_items = None
    if config is not None:
        expected_plan = AgentMCPPath(config, recordings_dir / "agent-mcp").plan(task, scenario)
        expected_items = expected_plan.calls[0].args["items"]

    for idx, call in enumerate(recording):
        if not isinstance(call, dict):
            issues.append(_issue("error", "agent-mcp", scenario_name, task, f"call {idx + 1} must be an object"))
            continue
        issues.extend(_validate_common_call(call, "agent-mcp", scenario_name, task, idx))

        if call.get("tool") != "mcp__airbyte-agent__execute":
            issues.append(_issue("error", "agent-mcp", scenario_name, task, f"call {idx + 1} tool must be mcp__airbyte-agent__execute"))

        args = call.get("args")
        items = args.get("items") if isinstance(args, dict) else None
        if not isinstance(items, list) or not items:
            issues.append(_issue("error", "agent-mcp", scenario_name, task, f"call {idx + 1} args.items must be a non-empty list"))
            continue

        for item_idx, item in enumerate(items):
            if not isinstance(item, dict):
                issues.append(_issue("error", "agent-mcp", scenario_name, task, f"call {idx + 1} item {item_idx + 1} must be an object"))
                continue
            if not item.get("select_fields"):
                issues.append(_issue("error", "agent-mcp", scenario_name, task, f"call {idx + 1} item {item_idx + 1} is stale: missing mandatory select_fields"))
            if expected_items is not None and item_idx < len(expected_items):
                expected = expected_items[item_idx]
                for key in ("connector_id", "entity", "action", "params", "select_fields"):
                    if item.get(key) != expected.get(key):
                        issues.append(_issue("error", "agent-mcp", scenario_name, task, f"call {idx + 1} item {item_idx + 1} {key} differs from planner"))

        extracted = extract_execution_time_ms(call.get("response"))
        wall_clock_ms = call.get("wall_clock_ms")
        if extracted is None:
            issues.append(_issue("error", "agent-mcp", scenario_name, task, f"call {idx + 1} response has no execution_metadata.execution_time_ms"))
        elif not isinstance(wall_clock_ms, int | float):
            issues.append(_issue("error", "agent-mcp", scenario_name, task, f"call {idx + 1} wall_clock_ms must be set from execution_metadata.execution_time_ms"))
        elif abs(float(wall_clock_ms) - extracted) > 1:
            issues.append(_issue("error", "agent-mcp", scenario_name, task, f"call {idx + 1} wall_clock_ms {wall_clock_ms} does not match execution metadata {extracted:.0f}"))

    return issues


def _validate_common_call(
    call: dict,
    slug: str,
    scenario_name: str,
    task: Task,
    idx: int,
) -> list[RecordingIssue]:
    issues: list[RecordingIssue] = []
    if not call.get("tool"):
        issues.append(_issue("error", slug, scenario_name, task, f"call {idx + 1} has no tool"))
    if not isinstance(call.get("args"), dict):
        issues.append(_issue("error", slug, scenario_name, task, f"call {idx + 1} has no args object"))
    if "response" not in call:
        issues.append(_issue("error", slug, scenario_name, task, f"call {idx + 1} has no response"))
    return issues


def _issue(
    level: Literal["error", "warning"],
    slug: str,
    scenario_name: str,
    task: Task,
    message: str,
) -> RecordingIssue:
    return RecordingIssue(
        level=level,
        path_slug=slug,
        scenario=scenario_name,
        action=task.action,
        message=message,
    )
