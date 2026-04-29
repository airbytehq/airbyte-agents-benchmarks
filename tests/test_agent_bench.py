from __future__ import annotations

import asyncio
import json

from agent_bench.config import LiveConfig
from agent_bench.export.scorecard import render_scorecard
from agent_bench.metrics import BenchmarkResult, StepResult
from agent_bench.paths.agent_mcp import AgentMCPPath
from agent_bench.paths.native_mcp import NativeMCPPath
from agent_bench.recordings import validate_recordings
from agent_bench.runner import Cell, RunReport
from agent_bench.scenarios.loader import load_scenario


def test_scenario_targets_match_launch_plan() -> None:
    slack_get = load_scenario("slack-get")
    assert slack_get.task.params["id"] == "C02TD5CB7PZ"
    assert slack_get.task.params["name_hint"] == "feedback_survey_results"

    granola_search = load_scenario("granola-search")
    granola_get = load_scenario("granola-get")
    granola_list = load_scenario("granola-list")
    assert granola_search.task.params["limit"] == 1
    assert granola_get.task.params["id"] == "not_ES3idLqBAmN9L1"
    assert granola_get.task.params["claude_mcp_id"] == "96457d50-5ed1-4d81-a2fc-f43c2b93530d"
    assert granola_list.task.params["limit"] == 25


def test_path_planning_uses_connector_specific_shapes(tmp_path) -> None:
    config = _config()

    scenario = load_scenario("granola-get")
    task = scenario.task
    mcp_plan = AgentMCPPath(config, tmp_path).plan(task, scenario)
    mcp_item = mcp_plan.calls[0].args["items"][0]
    assert mcp_item["params"] == {"note_id": "not_ES3idLqBAmN9L1"}
    assert mcp_item["select_fields"] == [
        "id",
        "title",
        "created_at",
        "updated_at",
        "attendees",
        "summary_text",
        "transcript",
    ]
    assert "describe_connector" in mcp_plan.notes[0]

    native_plan = NativeMCPPath(tmp_path).plan(task, scenario)
    assert native_plan.calls[0].args["meeting_id"] == "96457d50-5ed1-4d81-a2fc-f43c2b93530d"


def test_agent_mcp_recording_parses_execution_metadata_latency(tmp_path) -> None:
    scenario = load_scenario("linear-get")
    task = scenario.task
    rec_dir = tmp_path
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / "recording.json").write_text(json.dumps([{
        "tool": "mcp__airbyte-agent__execute",
        "args": {"items": [{
            "connector_id": "linear-id",
            "entity": "issues",
            "action": "get",
            "params": {"id": "issue-1"},
            "select_fields": ["id"],
        }]},
        "response": {"results": [{
            "result": {
                "status": "success",
                "result": {"id": "issue-1", "title": "One"},
                "execution_metadata": {"execution_time_ms": 123},
            },
        }]},
    }]))

    path = AgentMCPPath(_config(), rec_dir)
    result = _run_path(path, task, scenario)
    assert result.status == "ok"
    assert result.total_latency_ms == 123
    assert result.total_records == 1
    assert result.single_record_calls == 1
    assert result.single_record_tokens > 0


def test_validation_flags_stale_agent_mcp_recordings(tmp_path) -> None:
    rec_dir = tmp_path / "linear-get-scenario" / "agent-mcp"
    rec_dir.mkdir(parents=True)
    (rec_dir / "recording.json").write_text(json.dumps([{
        "tool": "mcp__airbyte-agent__execute",
        "args": {"items": [{
            "connector_id": "linear-id",
            "entity": "issues",
            "action": "get",
            "params": {"id": "ec6e00c7-dd96-4875-952c-69ecc33ce06d"},
        }]},
        "wall_clock_ms": 9,
        "response": {"results": [{
            "result": {
                "status": "success",
                "result": {"id": "issue-1"},
                "execution_metadata": {"execution_time_ms": 9},
            },
        }]},
    }]))

    issues = validate_recordings(["linear-get"], ["agent-mcp"], tmp_path, _config())
    messages = [issue.message for issue in issues]
    assert any("missing mandatory select_fields" in message for message in messages)


def test_scorecard_renders_interim_ratios(tmp_path) -> None:
    scenario = load_scenario("linear-search")
    report = RunReport(
        cells=[
            _cell(scenario, "REST Baseline (via SDK)", "agent-sdk", 400),
            _cell(scenario, "Agent MCP", "agent-mcp", 100),
            _cell(scenario, "Native MCP", "native-mcp", 300),
        ],
        requested_scenarios=["linear-search"],
        requested_paths=["agent-sdk", "agent-mcp", "native-mcp"],
    )

    out = tmp_path / "scorecard.md"
    render_scorecard(report, out)
    text = out.read_text()
    assert "Interim scorecard" in text
    assert "4.0× fewer tokens" in text
    assert "3.0× fewer tokens" in text


def _run_path(path: AgentMCPPath, task, scenario) -> BenchmarkResult:
    async def collect() -> BenchmarkResult:
        result = None
        async for _step, current in path.run_task(task, scenario):
            result = current
        assert result is not None
        return result

    return asyncio.run(collect())


def _config() -> LiveConfig:
    return LiveConfig(
        organization_id="org-id",
        client_id="client-id",
        client_secret="secret",
        connector_ids={
            "slack": "slack-id",
            "linear": "linear-id",
            "granola": "granola-id",
        },
    )


def _cell(scenario, path_name: str, path_short: str, tokens: int) -> Cell:
    result = BenchmarkResult(path_name=path_name)
    result.steps.append(StepResult(
        label="step",
        latency_ms=1,
        payload_bytes=tokens,
        tokens=tokens,
        records=1,
    ))
    result.total_records = 1
    return Cell(
        scenario=scenario,
        path_name=path_name,
        path_short=path_short,
        result=result,
    )
